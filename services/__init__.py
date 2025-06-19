"""
Services package for PPE Detection Application
"""

from .video_service import VideoService
from .detection_service import DetectionService
from .event_service import EventService
from .email_service import EmailService

__all__ = ["VideoService", "DetectionService", "EventService", "EmailService"]
