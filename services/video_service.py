"""
Video service for managing video sources and frame processing
"""

import os
import threading
import time
from typing import Dict, Optional, List
import cv2
import logging

from config import Config
from models import VideoSource, FrameBuffer
from utils import (
    PerformanceTimer,
    create_placeholder_frame,
    validate_video_file,
    logger,
)


class VideoService:
    """Service for managing video sources and frame processing"""

    def __init__(self, config: Config):
        self.config = config
        self.sources: Dict[str, VideoSource] = {}
        self.source_lock = threading.RLock()
        self._shutdown = False

    def add_source(
        self, name: str, source_type: str, path: str
    ) -> Optional[VideoSource]:
        """Add a new video source"""
        try:
            # Validate path
            if source_type == "file":
                full_path = os.path.join(self.config.VIDEO_UPLOADS, path)
                if not validate_video_file(full_path):
                    logger.error(f"Invalid video file: {full_path}")
                    return None
                path = full_path

            # Create source
            source = VideoSource(None, name, source_type, path)

            # Initialize capture
            if not source.init_capture():
                logger.error(f"Failed to initialize capture for {name}")
                return None

            # Start processing
            with self.source_lock:
                self.sources[source.id] = source
                source.status = "active"

            # Start frame capture thread
            capture_thread = threading.Thread(
                target=self._capture_frames,
                args=(source.id,),
                name=f"capture-{source.id}",
            )
            capture_thread.daemon = True
            capture_thread.start()
            source.threads["capture"] = capture_thread

            logger.info(f"Added source: {name} ({source.id})")
            return source

        except Exception as e:
            logger.error(f"Error adding source: {e}")
            return None

    def remove_source(self, source_id: str) -> bool:
        """Remove a video source"""
        with self.source_lock:
            if source_id not in self.sources:
                return False

            source = self.sources[source_id]
            source.status = "inactive"

            # Wait for threads to finish
            for thread in source.threads.values():
                if thread.is_alive():
                    thread.join(timeout=1.0)

            # Release resources
            source.release_capture()

            # Remove from sources
            del self.sources[source_id]

        logger.info(f"Removed source: {source_id}")
        return True

    def get_source(self, source_id: str) -> Optional[VideoSource]:
        """Get a video source by ID"""
        with self.source_lock:
            return self.sources.get(source_id)

    def get_all_sources(self) -> List[VideoSource]:
        """Get all video sources"""
        with self.source_lock:
            return list(self.sources.values())

    def _capture_frames(self, source_id: str):
        """Capture frames from a video source"""
        source = self.get_source(source_id)
        if not source:
            return

        frame_delay = 1.0 / source.fps
        last_frame_time = time.time()
        frame_index = 0

        logger.info(f"Starting frame capture for {source.name}")

        while source.status == "active" and not self._shutdown:
            try:
                # Read frame
                success, frame = source.read_frame()

                if not success:
                    if source.type == "file":
                        # Loop video
                        source.restart_video()
                        continue
                    else:
                        # Stream error
                        logger.error(f"Stream error for {source.name}")
                        source.status = "error"
                        break

                # Frame rate control
                current_time = time.time()
                elapsed = current_time - last_frame_time
                if elapsed < frame_delay:
                    time.sleep(frame_delay - elapsed)
                last_frame_time = time.time()

                # Add to buffer
                source.frames.append(frame)
                frame_index += 1

                # Update FPS metrics
                source.fps_frame_count += 1
                source.update_fps()

            except Exception as e:
                logger.error(f"Error in frame capture for {source.name}: {e}")
                source.status = "error"
                break

        logger.info(f"Stopped frame capture for {source.name}")

    def generate_frames(
        self,
        source_id: str,
        processed: bool = False,
        detector_func: Optional[callable] = None,
    ) -> bytes:
        """Generate video frames for streaming"""
        source = self.get_source(source_id)

        # Placeholder if source not found
        if not source:
            placeholder = create_placeholder_frame(text="Source Not Found")
            _, buf = cv2.imencode(".jpg", placeholder)
            while True:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
                )
                time.sleep(0.1)

        processed_index = 0

        while source and source.status == "active" and not self._shutdown:
            try:
                # Get frame from buffer
                if len(source.frames) == 0:
                    time.sleep(0.01)
                    continue

                # Handle buffer overrun
                buffer_len = len(source.frames)
                if processed_index >= buffer_len:
                    # Skip ahead if too far behind
                    if processed_index > buffer_len + self.config.FRAME_SKIP_THRESHOLD:
                        processed_index = buffer_len - 5
                    else:
                        time.sleep(0.01)
                        continue

                # Get frame
                frame = source.frames.get(processed_index)
                if frame is None:
                    processed_index = max(0, buffer_len - 1)
                    continue

                processed_index += 1

                # Apply detections if requested
                if processed and detector_func:
                    frame = detector_func(frame)

                # Encode and yield
                _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
                )

            except Exception as e:
                logger.error(f"Error generating frames: {e}")
                time.sleep(0.1)

    def shutdown(self):
        """Shutdown the service"""
        self._shutdown = True

        # Stop all sources
        with self.source_lock:
            for source_id in list(self.sources.keys()):
                self.remove_source(source_id)

        logger.info("Video service shutdown complete")
