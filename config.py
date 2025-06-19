"""
Configuration management for PPE Detection Application
"""

import os
from typing import List, Dict, Any


class Config:
    """Base configuration class"""

    # Flask settings
    SECRET_KEY = os.environ.get("SECRET_KEY") or "ppe_violation_detection"

    # Video settings
    VIDEO_UPLOADS = os.environ.get("VIDEO_UPLOADS", "static/video")
    ALLOWED_VIDEO_EXTENSIONS = ["MP4", "MOV", "AVI", "WMV", "WEBM"]

    # Detection settings
    DEFAULT_CONFIDENCE = float(os.environ.get("DEFAULT_CONFIDENCE", "0.5"))
    DETECTION_CLASSES = ["NO-Hardhat", "NO-Mask", "NO-Safety Vest"]

    # Frame processing
    MAX_FRAME_BUFFER_SIZE = int(
        os.environ.get("MAX_FRAME_BUFFER_SIZE", "30")
    )  # Reduced from 60
    FRAME_SKIP_THRESHOLD = int(
        os.environ.get("FRAME_SKIP_THRESHOLD", "15")
    )  # Skip frames if behind
    DETECTION_FRAME_SKIP = int(
        os.environ.get("DETECTION_FRAME_SKIP", "3")
    )  # Process every Nth frame

    # Performance settings
    DETECTION_THREAD_SLEEP = float(
        os.environ.get("DETECTION_THREAD_SLEEP", "0.033")
    )  # ~30 FPS
    MAX_DETECTION_EVENTS = int(os.environ.get("MAX_DETECTION_EVENTS", "1000"))
    EVENT_RETENTION_HOURS = int(os.environ.get("EVENT_RETENTION_HOURS", "1"))

    # Email settings
    EMAIL_COOLDOWN_SEC = int(os.environ.get("EMAIL_COOLDOWN_SEC", "60"))
    EMAIL_SENDER = os.environ.get("EMAIL_SENDER", "support.ai@giindia.com")
    EMAIL_BATCH_SIZE = int(
        os.environ.get("EMAIL_BATCH_SIZE", "5")
    )  # Batch email alerts

    # Caching settings
    DETECTION_CACHE_SIZE = int(os.environ.get("DETECTION_CACHE_SIZE", "100"))
    CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "5"))

    # Threading settings
    MAX_WORKER_THREADS = int(os.environ.get("MAX_WORKER_THREADS", "4"))
    QUEUE_MAX_SIZE = int(os.environ.get("QUEUE_MAX_SIZE", "1000"))

    # UI settings
    DASHBOARD_UPDATE_INTERVAL_MS = int(
        os.environ.get("DASHBOARD_UPDATE_INTERVAL_MS", "1000")
    )

    @classmethod
    def init_app(cls, app):
        """Initialize application with configuration"""
        # Ensure directories exist
        os.makedirs(cls.VIDEO_UPLOADS, exist_ok=True)

        # Set Flask config
        app.config.from_object(cls)


class DevelopmentConfig(Config):
    """Development configuration"""

    DEBUG = True
    DETECTION_THREAD_SLEEP = 0.1  # Slower for development


class ProductionConfig(Config):
    """Production configuration"""

    DEBUG = False
    MAX_FRAME_BUFFER_SIZE = 20  # Smaller buffer for production
    DETECTION_FRAME_SKIP = 2  # Process more frames in production


class TestingConfig(Config):
    """Testing configuration"""

    TESTING = True
    MAX_FRAME_BUFFER_SIZE = 10
    EVENT_RETENTION_HOURS = 0  # Don't retain events in tests


# Configuration dictionary
config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}


def get_config(config_name: str = None) -> Config:
    """Get configuration object by name"""
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "default")
    return config[config_name]
