import os
import sys
import numpy as np
import cv2
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from detection import get_detector, DETECTOR_REGISTRY


def test_registry_contains_ppe():
    assert 'ppe' in DETECTOR_REGISTRY


def test_ppe_detector_load_and_detect():
    torch = pytest.importorskip('torch')
    DetClass = get_detector('ppe')
    det = DetClass(conf=0.25)
    det.load_model()
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    detections = det.detect(img)
    assert isinstance(detections, list)
