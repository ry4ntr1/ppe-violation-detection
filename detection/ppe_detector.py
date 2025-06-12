import numpy as np
from pathlib import Path
from ultralytics import YOLO  # v8 predictor


class Detector:
    """YOLOv8 detector using the ppe.pt weights."""

    CLASSES = [
        "Hardhat",
        "Mask",
        "NO-Hardhat",
        "NO-Mask",
        "NO-Safety Vest",
        "Person",
        "Safety Cone",
        "Safety Vest",
        "machinery",
        "vehicle",
    ]

    def __init__(self, conf: float = 0.25, weights: str | None = None):
        self.conf = conf
        self.weights = (
            str(Path(__file__).resolve().parent / "ppe.pt")
            if weights is None
            else weights
        )
        self.model = YOLO(self.weights)

    def detect(self, frame):
        """Run detection on a single frame with YOLOv8."""
        results = self.model.predict(source=frame, conf=self.conf, verbose=False)[0]
        detections = []
        for box in results.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            cls_idx = int(box.cls[0])
            conf = float(box.conf[0])
            label = f"{self.model.names[cls_idx]} {conf:.2f}"
            detections.append(((x1, y1, x2, y2), label))
        return detections
