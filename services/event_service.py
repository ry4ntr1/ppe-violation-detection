"""
Event service for managing Server-Sent Events (SSE)
"""

import queue
import threading
import time
import json
from typing import Dict, List, Optional, Generator
from datetime import datetime
import logging

from config import Config
from models import VideoSource
from utils import logger


class EventService:
    """Service for managing Server-Sent Events with performance optimizations"""

    def __init__(self, config: Config, video_service=None, detection_service=None):
        self.config = config
        self.video_service = video_service
        self.detection_service = detection_service

        # Event queue with size limit
        self.event_queue = queue.Queue(maxsize=config.QUEUE_MAX_SIZE)

        # Client connections
        self.clients: Dict[str, queue.Queue] = {}
        self.clients_lock = threading.RLock()

        # Stats update thread
        self.stats_thread = None
        self._shutdown = False

    def start(self):
        """Start the event service"""
        # Start stats update thread
        self.stats_thread = threading.Thread(
            target=self._update_stats_periodically, name="stats-updater"
        )
        self.stats_thread.daemon = True
        self.stats_thread.start()

        logger.info("Event service started")

    def add_client(self, client_id: str) -> queue.Queue:
        """Add a new SSE client"""
        with self.clients_lock:
            client_queue = queue.Queue(maxsize=100)
            self.clients[client_id] = client_queue
            logger.info(f"Added SSE client: {client_id}")
            return client_queue

    def remove_client(self, client_id: str):
        """Remove an SSE client"""
        with self.clients_lock:
            if client_id in self.clients:
                del self.clients[client_id]
                logger.info(f"Removed SSE client: {client_id}")

    def broadcast_event(self, event_type: str, data: Dict):
        """Broadcast an event to all connected clients"""
        event_data = json.dumps(data)
        event = f"event: {event_type}\ndata: {event_data}\n\n"

        with self.clients_lock:
            disconnected = []
            for client_id, client_queue in self.clients.items():
                try:
                    # Non-blocking put with timeout
                    client_queue.put(event, block=False)
                except queue.Full:
                    logger.warning(f"Client {client_id} queue full, dropping event")
                except Exception as e:
                    logger.error(f"Error sending to client {client_id}: {e}")
                    disconnected.append(client_id)

            # Remove disconnected clients
            for client_id in disconnected:
                self.remove_client(client_id)

    def generate_events(
        self, client_id: str, source_id: Optional[str] = None
    ) -> Generator[str, None, None]:
        """Generate SSE stream for a client"""
        client_queue = self.add_client(client_id)

        try:
            # Send initial stats
            stats = self._get_dashboard_stats()
            yield f"event: stats\ndata: {json.dumps(stats)}\n\n"

            # Send initial source updates
            if self.video_service:
                for source in self.video_service.get_all_sources():
                    if source_id is None or source.id == source_id:
                        yield f"event: source_update\ndata: {json.dumps(self._get_source_status(source))}\n\n"

            # Stream events
            while not self._shutdown:
                try:
                    # Get event with timeout
                    event = client_queue.get(timeout=30)

                    # Filter by source if specified
                    if source_id and "source_id" in event:
                        event_data = json.loads(event.split("data: ")[1].split("\n")[0])
                        if event_data.get("source_id") != source_id:
                            continue

                    yield event

                except queue.Empty:
                    # Send keepalive
                    yield ":keepalive\n\n"

        except GeneratorExit:
            logger.info(f"Client {client_id} disconnected")
        finally:
            self.remove_client(client_id)

    def _update_stats_periodically(self):
        """Update dashboard statistics periodically"""
        last_update = time.time()
        update_interval = self.config.DASHBOARD_UPDATE_INTERVAL_MS / 1000.0

        while not self._shutdown:
            try:
                current_time = time.time()

                # Process events from queue
                while not self.event_queue.empty():
                    try:
                        event_type, event_data = self.event_queue.get_nowait()
                        self.broadcast_event(event_type, event_data)
                    except queue.Empty:
                        break

                # Send periodic stats update
                if current_time - last_update >= update_interval:
                    stats = self._get_dashboard_stats()
                    self.broadcast_event("stats", stats)
                    last_update = current_time

                    # Send source updates
                    if self.video_service:
                        for source in self.video_service.get_all_sources():
                            self.broadcast_event(
                                "source_update", self._get_source_status(source)
                            )

                time.sleep(0.1)

            except Exception as e:
                logger.error(f"Error in stats updater: {e}")
                time.sleep(1)

    def _get_dashboard_stats(self) -> Dict:
        """Get current dashboard statistics"""
        stats = {
            "active_sources": 0,
            "total_violations": 0,
            "compliance_rate": 100.0,
            "last_detection": None,
            "timestamp": datetime.now().isoformat(),
        }

        if self.video_service:
            sources = self.video_service.get_all_sources()
            active_sources = [s for s in sources if s.status == "active"]
            stats["active_sources"] = len(active_sources)

            # Calculate overall compliance rate
            total_frames = sum(s.frames_processed for s in sources)
            total_violations = sum(s.frames_with_violations for s in sources)

            if total_frames > 0:
                stats["compliance_rate"] = round(
                    (1 - total_violations / total_frames) * 100, 1
                )

            # Find last detection
            last_detections = [s.last_detection for s in sources if s.last_detection]
            if last_detections:
                stats["last_detection"] = max(last_detections).isoformat()

        if self.detection_service:
            detection_stats = self.detection_service.get_statistics()
            stats["total_violations"] = detection_stats["total_events"]

        return stats

    def _get_source_status(self, source: VideoSource) -> Dict:
        """Get source status for updates"""
        return {
            "source_id": source.id,
            "status": source.status,
            "fps": round(source.processing_fps, 1),
            "violations": sum(v.count for v in source.violation_stats.values()),
            "compliance_rate": round(source.compliance_rate, 1),
            "timestamp": datetime.now().isoformat(),
        }

    def shutdown(self):
        """Shutdown the event service"""
        self._shutdown = True

        # Close all client connections
        with self.clients_lock:
            for client_id in list(self.clients.keys()):
                self.remove_client(client_id)

        # Wait for stats thread
        if self.stats_thread and self.stats_thread.is_alive():
            self.stats_thread.join(timeout=2)

        logger.info("Event service shutdown complete")
