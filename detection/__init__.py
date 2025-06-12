from .ppe_detector import Detector as PPEDetector

DETECTOR_REGISTRY = {
    "ppe": PPEDetector,
}


def get_detector(name: str):
    """Retrieve a detector class by name."""
    if name not in DETECTOR_REGISTRY:
        raise KeyError(f"Unknown detector: {name}")
    return DETECTOR_REGISTRY[name]

__all__ = ["get_detector", "DETECTOR_REGISTRY"]
