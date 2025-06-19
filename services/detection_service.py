"""
Detection service for PPE violation detection with performance optimizations
"""

import threading
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import deque
import cv2
import numpy as np
import logging
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from models import VideoSource, DetectionEvent
from detection import get_detector
from utils import (
    PerformanceTimer,
    LRUCache,
    FrameSkipper,
    optimize_frame_for_detection,
    deduplicate_detections,
    format_violation_name,
    logger,
)


class DetectionService:
    """Service for managing PPE violation detection"""

    def __init__(self, config: Config, event_queue=None):
        self.config = config
        self.event_queue = event_queue
        self.detectors = {}  # Cache detector instances
        self.detection_cache = LRUCache(
            max_size=config.DETECTION_CACHE_SIZE, ttl_seconds=config.CACHE_TTL_SECONDS
        )
        self.detection_events = deque(maxlen=config.MAX_DETECTION_EVENTS)
        self.processing_threads = {}
        self._shutdown = False

    def get_detector(self, detector_name: str = "ppe", confidence: float = None):
        """Get or create a detector instance (cached)"""
        if confidence is None:
            confidence = self.config.DEFAULT_CONFIDENCE

        key = f"{detector_name}_{confidence}"
        if key not in self.detectors:
            self.detectors[key] = get_detector(detector_name)(conf=confidence)
        return self.detectors[key]

    def start_detection(self, source: VideoSource):
        """Start detection processing for a video source"""
        if source.id in self.processing_threads:
            logger.warning(f"Detection already running for {source.name}")
            return

        thread = threading.Thread(
            target=self._process_detections,
            args=(source,),
            name=f"detection-{source.id}",
        )
        thread.daemon = True
        thread.start()
        self.processing_threads[source.id] = thread
        source.threads["detection"] = thread

        logger.info(f"Started detection for {source.name}")

    def stop_detection(self, source_id: str):
        """Stop detection processing for a video source"""
        if source_id in self.processing_threads:
            # Thread will stop when source becomes inactive
            del self.processing_threads[source_id]

    def _process_detections(self, source: VideoSource):
        """Process detections for a video source with optimizations"""
        detector = self.get_detector()
        frame_skipper = FrameSkipper(
            target_fps=source.fps,
            min_skip=self.config.DETECTION_FRAME_SKIP,
            max_skip=self.config.DETECTION_FRAME_SKIP * 3,
        )

        processed_index = 0
        last_detection_time = time.time()

        logger.info(f"Starting detection processing for {source.name}")

        while source.status == "active" and not self._shutdown:
            try:
                # Get latest frame index
                buffer_len = len(source.frames)
                if buffer_len == 0:
                    time.sleep(0.1)
                    continue

                # Skip if too far behind
                if processed_index < buffer_len - self.config.FRAME_SKIP_THRESHOLD:
                    processed_index = buffer_len - 10
                    logger.warning(
                        f"Skipping frames for {source.name}, was at {processed_index}, now at {buffer_len}"
                    )

                # Wait for new frames
                if processed_index >= buffer_len:
                    time.sleep(self.config.DETECTION_THREAD_SLEEP)
                    continue

                # Check if we should process this frame
                if not frame_skipper.should_process(processed_index):
                    processed_index += 1
                    continue

                # Get frame
                frame = source.frames.get(processed_index)
                if frame is None:
                    processed_index += 1
                    continue

                # Performance timing
                with PerformanceTimer("Detection") as timer:
                    # Process frame
                    detections = self._detect_violations(
                        frame, detector, source.id, processed_index
                    )

                    # Update metrics
                    source.frames_processed += 1

                    # Process detections
                    if detections:
                        source.frames_with_violations += 1
                        self._process_detection_results(
                            source, detections, processed_index
                        )

                # Update frame skipper based on performance
                frame_skipper.update_performance(timer.elapsed)

                processed_index += 1

                # Periodic cleanup
                if time.time() - last_detection_time > 60:
                    self._cleanup_old_events()
                    last_detection_time = time.time()

            except Exception as e:
                logger.error(f"Error in detection processing for {source.name}: {e}")
                time.sleep(0.5)

        logger.info(f"Stopped detection processing for {source.name}")

    def _detect_violations(
        self, frame: np.ndarray, detector, source_id: str, frame_index: int
    ) -> List[Tuple]:
        """Detect violations in a frame with caching"""
        # Check cache first
        cache_key = f"{source_id}_{frame_index}"
        cached_result = self.detection_cache.get(cache_key)
        if cached_result is not None:
            return cached_result

        # Optimize frame for detection
        optimized_frame = optimize_frame_for_detection(frame)

        # Run detection
        detections = detector.detect(optimized_frame)

        # Filter for violations only
        violations = []
        for box, label in detections:
            if any(v in label for v in self.config.DETECTION_CLASSES):
                # Scale box back to original frame size if needed
                if optimized_frame.shape != frame.shape:
                    scale_x = frame.shape[1] / optimized_frame.shape[1]
                    scale_y = frame.shape[0] / optimized_frame.shape[0]
                    x1, y1, x2, y2 = box
                    box = (
                        int(x1 * scale_x),
                        int(y1 * scale_y),
                        int(x2 * scale_x),
                        int(y2 * scale_y),
                    )
                violations.append((box, label))

        # Deduplicate overlapping detections
        violations = deduplicate_detections(violations)

        # Cache result
        self.detection_cache.put(cache_key, violations)

        return violations

    def _process_detection_results(
        self, source: VideoSource, detections: List[Tuple], frame_index: int
    ):
        """Process detection results and generate events"""
        timestamp = datetime.now()

        for box, label in detections:
            # Parse violation info
            violation_type = self._parse_violation_type(label)
            confidence = self._parse_confidence(label)

            # Create event
            event = DetectionEvent(
                source_id=source.id,
                timestamp=timestamp,
                violation_type=violation_type,
                confidence=confidence,
                event_id=f"{violation_type}_{timestamp.strftime('%Y%m%d_%H%M%S')}_{frame_index}",
                frame_number=frame_index,
            )

            # Store event
            self.detection_events.append(event)

            # Update source stats
            source.add_violation(violation_type, timestamp)

            # Send to event queue if available
            if self.event_queue:
                self.event_queue.put(("detection", event.to_dict()))

    def _parse_violation_type(self, label: str) -> str:
        """Parse violation type from detection label"""
        # Handle special cases
        if "NO-Safety Vest" in label:
            return "NO-Safety Vest"
        return label.split()[0]

    def _parse_confidence(self, label: str) -> float:
        """Parse confidence from detection label"""
        try:
            return float(label.split()[-1])
        except:
            return 0.0

    def _cleanup_old_events(self):
        """Remove old detection events"""
        cutoff_time = datetime.now() - timedelta(
            hours=self.config.EVENT_RETENTION_HOURS
        )

        # Filter events
        current_events = list(self.detection_events)
        self.detection_events.clear()

        for event in current_events:
            if event.timestamp > cutoff_time:
                self.detection_events.append(event)

        logger.info(
            f"Cleaned up detection events, kept {len(self.detection_events)} events"
        )

    def get_recent_events(
        self, source_id: Optional[str] = None, minutes: int = 60
    ) -> List[DetectionEvent]:
        """Get recent detection events"""
        cutoff_time = datetime.now() - timedelta(minutes=minutes)

        events = []
        for event in self.detection_events:
            if event.timestamp > cutoff_time:
                if source_id is None or event.source_id == source_id:
                    events.append(event)

        return sorted(events, key=lambda e: e.timestamp, reverse=True)

    def get_statistics(self) -> Dict:
        """Get detection statistics"""
        total_events = len(self.detection_events)

        # Count by type
        violations_by_type = {}
        for event in self.detection_events:
            vtype = event.violation_type
            violations_by_type[vtype] = violations_by_type.get(vtype, 0) + 1

        return {
            "total_events": total_events,
            "violations_by_type": violations_by_type,
            "cache_size": len(self.detection_cache.cache),
            "active_detectors": len(self.detectors),
        }

    def apply_detections_to_frame(
        self,
        frame: np.ndarray,
        source_id: str,
        frame_index: int,
        color: Tuple[int, int, int] = (255, 0, 0),
    ) -> np.ndarray:
        """Apply detection overlays to a frame for visualization"""
        detector = self.get_detector()

        # Get detections
        detections = self._detect_violations(frame, detector, source_id, frame_index)

        # Draw on frame
        for box, label in detections:
            x1, y1, x2, y2 = box
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

            # Add label
            label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
            cv2.rectangle(
                frame, (x1, y1 - label_size[1] - 4), (x1 + label_size[0], y1), color, -1
            )
            cv2.putText(
                frame,
                label,
                (x1, y1 - 2),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                2,
            )

        return frame

    def shutdown(self):
        """Shutdown the service"""
        self._shutdown = True

        # Clear caches
        self.detection_cache.clear()
        self.detectors.clear()

        logger.info("Detection service shutdown complete")
