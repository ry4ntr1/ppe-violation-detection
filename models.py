"""
Data models for PPE Detection Application
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
from collections import deque
import uuid
import threading
import cv2


@dataclass
class DetectionEvent:
    """Represents a single PPE violation detection event"""

    source_id: str
    timestamp: datetime
    violation_type: str
    confidence: float
    event_id: str
    frame_number: int

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "source_id": self.source_id,
            "timestamp": self.timestamp.isoformat(),
            "violation_type": self.violation_type,
            "confidence": self.confidence,
            "event_id": self.event_id,
            "frame_number": self.frame_number,
        }


@dataclass
class ViolationStats:
    """Statistics for a specific violation type"""

    count: int = 0
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None

    def increment(self, timestamp: datetime = None):
        """Increment violation count and update timestamps"""
        self.count += 1
        if timestamp:
            if self.first_seen is None:
                self.first_seen = timestamp
            self.last_seen = timestamp


class FrameBuffer:
    """Thread-safe circular buffer for video frames with performance optimizations"""

    def __init__(self, max_size: int = 30):
        self.buffer = deque(maxlen=max_size)
        self.lock = threading.RLock()
        self.frame_count = 0

    def append(self, frame):
        """Add frame to buffer"""
        with self.lock:
            self.buffer.append(frame)
            self.frame_count += 1

    def get(self, index: int):
        """Get frame at index with bounds checking"""
        with self.lock:
            if 0 <= index < len(self.buffer):
                return self.buffer[index].copy()
            return None

    def get_latest(self, n: int = 1):
        """Get n most recent frames"""
        with self.lock:
            if n == 1 and self.buffer:
                return self.buffer[-1].copy()
            return (
                list(self.buffer)[-n:] if n <= len(self.buffer) else list(self.buffer)
            )

    def clear(self):
        """Clear the buffer"""
        with self.lock:
            self.buffer.clear()
            self.frame_count = 0

    def __len__(self):
        return len(self.buffer)

    @property
    def is_full(self):
        """Check if buffer is at capacity"""
        return len(self.buffer) == self.buffer.maxlen


class VideoSource:
    """Represents a video source with all associated data and methods"""

    def __init__(self, source_id: str, name: str, source_type: str, path: str):
        # Basic info
        self.id = source_id or str(uuid.uuid4())
        self.name = name
        self.type = source_type  # 'file' or 'stream'
        self.path = path

        # Status
        self.status = "inactive"  # inactive, active, error
        self.fps = 30.0
        self.total_frames = 0

        # Video capture
        self.video_capture: Optional[cv2.VideoCapture] = None
        self.capture_lock = threading.Lock()

        # Frame buffer with optimized size
        self.frames = FrameBuffer(max_size=20)

        # Detection tracking
        self.violation_stats: Dict[str, ViolationStats] = {}
        self.last_detection: Optional[datetime] = None
        self.alerts_sent: Set[Tuple[str, str]] = (
            set()
        )  # (violation_type, timestamp_minute)

        # Performance metrics
        self.frames_processed = 0
        self.frames_with_violations = 0
        self.processing_fps = 0.0
        self.last_fps_update = datetime.now()
        self.fps_frame_count = 0

        # Thread management
        self.threads: Dict[str, threading.Thread] = {}

    def init_capture(self) -> bool:
        """Initialize video capture"""
        try:
            with self.capture_lock:
                if self.type == "file":
                    self.video_capture = cv2.VideoCapture(self.path)
                else:
                    self.video_capture = cv2.VideoCapture(self.path)

                if self.video_capture and self.video_capture.isOpened():
                    self.fps = self.video_capture.get(cv2.CAP_PROP_FPS) or 30.0
                    self.total_frames = int(
                        self.video_capture.get(cv2.CAP_PROP_FRAME_COUNT)
                    )
                    return True
        except Exception as e:
            print(f"Error initializing capture for {self.name}: {e}")
        return False

    def release_capture(self):
        """Release video capture resources"""
        with self.capture_lock:
            if self.video_capture:
                self.video_capture.release()
                self.video_capture = None

    def read_frame(self) -> Tuple[bool, Optional[any]]:
        """Read a frame from the video source"""
        with self.capture_lock:
            if self.video_capture and self.video_capture.isOpened():
                return self.video_capture.read()
        return False, None

    def restart_video(self):
        """Restart video from beginning (for file sources)"""
        if self.type == "file":
            with self.capture_lock:
                if self.video_capture:
                    self.video_capture.set(cv2.CAP_PROP_POS_FRAMES, 0)

    def update_fps(self):
        """Update processing FPS calculation"""
        now = datetime.now()
        time_diff = (now - self.last_fps_update).total_seconds()
        if time_diff >= 1.0:  # Update every second
            self.processing_fps = self.fps_frame_count / time_diff
            self.fps_frame_count = 0
            self.last_fps_update = now

    def add_violation(self, violation_type: str, timestamp: datetime = None):
        """Record a violation detection"""
        if violation_type not in self.violation_stats:
            self.violation_stats[violation_type] = ViolationStats()
        self.violation_stats[violation_type].increment(timestamp or datetime.now())
        self.last_detection = timestamp or datetime.now()

    @property
    def compliance_rate(self) -> float:
        """Calculate compliance rate as percentage"""
        if self.frames_processed == 0:
            return 100.0
        return (1 - self.frames_with_violations / self.frames_processed) * 100

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "path": self.path,
            "status": self.status,
            "fps": self.fps,
            "processing_fps": round(self.processing_fps, 1),
            "compliance_rate": round(self.compliance_rate, 1),
            "violations": {k: v.count for k, v in self.violation_stats.items()},
            "last_detection": self.last_detection.isoformat()
            if self.last_detection
            else None,
        }


@dataclass
class ScreeningResult:
    """Result from PPE screening detection"""

    timestamp: datetime = field(default_factory=datetime.now)
    site_id: str = ""
    detections: List[Dict] = field(default_factory=list)
    image_data: Optional[str] = None  # Base64 encoded image
    compliance_status: bool = True
    missing_ppe: List[str] = field(default_factory=list)
