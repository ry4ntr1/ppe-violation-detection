"""
Utility functions and classes for PPE Detection Application
"""

import time
import functools
import threading
from typing import Dict, Any, Optional, Callable, Tuple
from datetime import datetime, timedelta
import cv2
import numpy as np
import logging


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PerformanceTimer:
    """Context manager for timing operations"""

    def __init__(self, name: str = "Operation", log_output: bool = False):
        self.name = name
        self.log_output = log_output
        self.start_time = None
        self.end_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time
        if self.log_output:
            logger.info(f"{self.name} took {self.duration:.3f} seconds")

    @property
    def elapsed(self) -> float:
        if self.end_time:
            return self.duration
        return time.time() - self.start_time


class LRUCache:
    """Simple LRU cache implementation for detection results"""

    def __init__(self, max_size: int = 100, ttl_seconds: int = 5):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.cache: Dict[str, Tuple[Any, datetime]] = {}
        self.access_order = []
        self.lock = threading.RLock()

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired"""
        with self.lock:
            if key in self.cache:
                value, timestamp = self.cache[key]
                if datetime.now() - timestamp < timedelta(seconds=self.ttl_seconds):
                    # Move to end (most recently used)
                    self.access_order.remove(key)
                    self.access_order.append(key)
                    return value
                else:
                    # Expired
                    del self.cache[key]
                    self.access_order.remove(key)
            return None

    def put(self, key: str, value: Any):
        """Put value in cache"""
        with self.lock:
            if key in self.cache:
                self.access_order.remove(key)
            elif len(self.cache) >= self.max_size:
                # Evict least recently used
                lru_key = self.access_order.pop(0)
                del self.cache[lru_key]

            self.cache[key] = (value, datetime.now())
            self.access_order.append(key)

    def clear(self):
        """Clear the cache"""
        with self.lock:
            self.cache.clear()
            self.access_order.clear()


def frame_hash(frame: np.ndarray) -> str:
    """Generate a hash for a frame for caching purposes"""
    # Use a downsampled version for faster hashing
    small = cv2.resize(frame, (64, 64))
    return str(hash(small.tobytes()))


def optimize_frame_for_detection(
    frame: np.ndarray, target_size: Tuple[int, int] = (640, 480)
) -> np.ndarray:
    """Optimize frame size for detection while maintaining aspect ratio"""
    h, w = frame.shape[:2]

    # Skip if already optimal size
    if (w, h) == target_size:
        return frame

    # Calculate scaling factor
    scale = min(target_size[0] / w, target_size[1] / h)

    # Only downscale, don't upscale
    if scale < 1:
        new_w = int(w * scale)
        new_h = int(h * scale)
        return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

    return frame


def batch_process_frames(
    frames: list, process_func: Callable, batch_size: int = 5
) -> list:
    """Process frames in batches for better performance"""
    results = []
    for i in range(0, len(frames), batch_size):
        batch = frames[i : i + batch_size]
        batch_results = [process_func(frame) for frame in batch]
        results.extend(batch_results)
    return results


class RateLimiter:
    """Rate limiter for controlling processing frequency"""

    def __init__(self, max_calls: int, period_seconds: float):
        self.max_calls = max_calls
        self.period_seconds = period_seconds
        self.calls = []
        self.lock = threading.Lock()

    def __call__(self, func):
        """Decorator for rate limiting"""

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with self.lock:
                now = time.time()
                # Remove old calls
                self.calls = [t for t in self.calls if now - t < self.period_seconds]

                if len(self.calls) < self.max_calls:
                    self.calls.append(now)
                    return func(*args, **kwargs)
                else:
                    # Rate limit exceeded
                    wait_time = self.period_seconds - (now - self.calls[0])
                    logger.warning(f"Rate limit exceeded, waiting {wait_time:.2f}s")
                    return None

        return wrapper


class FrameSkipper:
    """Intelligent frame skipping based on processing speed"""

    def __init__(self, target_fps: float = 30.0, min_skip: int = 1, max_skip: int = 5):
        self.target_fps = target_fps
        self.min_skip = min_skip
        self.max_skip = max_skip
        self.frame_time = 1.0 / target_fps
        self.last_process_time = 0
        self.skip_count = min_skip
        self.performance_history = []

    def should_process(self, frame_index: int) -> bool:
        """Determine if frame should be processed"""
        if frame_index % self.skip_count == 0:
            return True
        return False

    def update_performance(self, process_time: float):
        """Update skip count based on processing performance"""
        self.performance_history.append(process_time)
        if len(self.performance_history) > 10:
            self.performance_history.pop(0)

        avg_time = sum(self.performance_history) / len(self.performance_history)

        if avg_time > self.frame_time * 1.5:
            # Processing too slow, increase skip
            self.skip_count = min(self.skip_count + 1, self.max_skip)
        elif avg_time < self.frame_time * 0.5 and self.skip_count > self.min_skip:
            # Processing fast enough, decrease skip
            self.skip_count = max(self.skip_count - 1, self.min_skip)


def create_placeholder_frame(
    width: int = 640, height: int = 480, text: str = "No Signal"
) -> np.ndarray:
    """Create a placeholder frame for when video is unavailable"""
    frame = np.zeros((height, width, 3), dtype=np.uint8)

    # Add text
    font = cv2.FONT_HERSHEY_SIMPLEX
    text_size = cv2.getTextSize(text, font, 1.2, 2)[0]
    text_x = (width - text_size[0]) // 2
    text_y = (height + text_size[1]) // 2

    cv2.putText(frame, text, (text_x, text_y), font, 1.2, (255, 255, 255), 2)

    return frame


def validate_video_file(filepath: str) -> bool:
    """Validate if a file is a valid video"""
    try:
        cap = cv2.VideoCapture(filepath)
        if cap.isOpened():
            ret, _ = cap.read()
            cap.release()
            return ret
    except:
        pass
    return False


def format_violation_name(violation: str) -> str:
    """Format violation name for consistent display"""
    # Ensure consistent formatting
    if violation == "NO-Safety Vest":
        return "NO-Safety Vest"
    return violation


def calculate_iou(
    box1: Tuple[int, int, int, int], box2: Tuple[int, int, int, int]
) -> float:
    """Calculate Intersection over Union for two bounding boxes"""
    x1, y1, x2, y2 = box1
    x1p, y1p, x2p, y2p = box2

    # Calculate intersection
    xi1 = max(x1, x1p)
    yi1 = max(y1, y1p)
    xi2 = min(x2, x2p)
    yi2 = min(y2, y2p)

    if xi2 < xi1 or yi2 < yi1:
        return 0.0

    intersection_area = (xi2 - xi1) * (yi2 - yi1)
    box1_area = (x2 - x1) * (y2 - y1)
    box2_area = (x2p - x1p) * (y2p - y1p)
    union_area = box1_area + box2_area - intersection_area

    return intersection_area / union_area if union_area > 0 else 0.0


def deduplicate_detections(detections: list, iou_threshold: float = 0.5) -> list:
    """Remove duplicate detections based on IOU threshold"""
    if len(detections) <= 1:
        return detections

    # Sort by confidence
    detections = sorted(detections, key=lambda x: float(x[1].split()[-1]), reverse=True)

    keep = []
    for i, (box1, label1) in enumerate(detections):
        duplicate = False
        for box2, label2 in keep:
            if calculate_iou(box1, box2) > iou_threshold:
                duplicate = True
                break
        if not duplicate:
            keep.append((box1, label1))

    return keep
