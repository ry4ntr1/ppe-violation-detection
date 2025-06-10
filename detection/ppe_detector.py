import numpy as np
from pathlib import Path


class Detector:
    """YOLOv5 detector using the ppe.pt weights."""

    CLASSES = [
        'Hardhat', 'Mask', 'NO-Hardhat', 'NO-Mask', 'NO-Safety Vest',
        'Person', 'Safety Cone', 'Safety Vest', 'machinery', 'vehicle'
    ]

    def __init__(self, conf: float = 0.25, weights: str | None = None):
        self.conf = conf
        # Resolve default weights relative to this file
        if weights is None:
            self.weights = str(Path(__file__).resolve().parent / "ppe.pt")
        else:
            self.weights = weights
        self.model = None

    def load_model(self) -> None:
        """Load the YOLO model (v8 or v5 depending on weight)."""
        if self.model is not None:
            return

        try:
            # Prefer Ultralytics YOLO loader (v8) as newer weights often use this format.
            from ultralytics import YOLO  # type: ignore

            self.model = YOLO(self.weights)
            if hasattr(self.model, "predict"):
                # v8 style – set confidence via args on predict, so we store conf here only.
                pass
        except (ModuleNotFoundError, ValueError, AssertionError):
            # Fall back to YOLOv5 via torch.hub
            import torch

            self.model = torch.hub.load(
                "ultralytics/yolov5",
                "custom",
                path=self.weights,
                force_reload=False,
            )
            self.model.conf = self.conf

    def detect(self, frame):
        """Run detection on a single frame."""
        if self.model is None:
            raise RuntimeError('Model not loaded')

        # Handle both v8 (YOLO object) and v5 (torch hub model) outputs
        if hasattr(self.model, "predict"):
            # YOLOv8
            result = self.model.predict(frame, conf=self.conf, verbose=False)[0]
            boxes = result.boxes
            detections = []
            for box in boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                cls_idx = int(box.cls[0])
                label = self.model.names[cls_idx]
                detections.append(((x1, y1, x2, y2), label))
            return detections

        else:
            # YOLOv5
            results = self.model(frame)
            preds = results.xyxy[0].cpu().numpy()
            detections = []
            for x1, y1, x2, y2, conf, cls in preds:
                label = self.model.names[int(cls)]
                detections.append(((int(x1), int(y1), int(x2), int(y2)), label))
            return detections
