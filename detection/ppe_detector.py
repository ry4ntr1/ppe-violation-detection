import numpy as np


class Detector:
    """YOLOv5 detector using the ppe.pt weights."""

    CLASSES = [
        'Hardhat', 'Mask', 'NO-Hardhat', 'NO-Mask', 'NO-Safety Vest',
        'Person', 'Safety Cone', 'Safety Vest', 'machinery', 'vehicle'
    ]

    def __init__(self, conf: float = 0.25, weights: str = 'ppe.pt'):
        self.conf = conf
        self.weights = weights
        self.model = None

    def load_model(self) -> None:
        """Load the YOLOv5 model."""
        if self.model is None:
            import torch
            self.model = torch.hub.load(
                'ultralytics/yolov5', 'custom', path=self.weights, force_reload=False
            )
            self.model.conf = self.conf

    def detect(self, frame):
        """Run detection on a single frame."""
        if self.model is None:
            raise RuntimeError('Model not loaded')
        results = self.model(frame)
        preds = results.xyxy[0].cpu().numpy()
        detections = []
        for x1, y1, x2, y2, conf, cls in preds:
            label = self.model.names[int(cls)]
            detections.append(((int(x1), int(y1), int(x2), int(y2)), label))
        return detections
