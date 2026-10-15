import numpy as np

from app.face_detector import FaceDetection


class FakeDetector:
    def __init__(self, count, landmarks):
        self.count, self.landmarks = count, landmarks

    def detect(self, _image):
        return [FaceDetection((1, 2, 30, 40), 0.9, self.landmarks) for _ in range(self.count)]


def test_detector_contract_zero_one_many(landmarks):
    image = np.zeros((120, 160, 3), dtype=np.uint8)
    assert FakeDetector(0, landmarks).detect(image) == []
    one = FakeDetector(1, landmarks).detect(image)
    assert len(one) == 1 and one[0].landmarks.shape == (5, 2)
    assert len(FakeDetector(2, landmarks).detect(image)) == 2
