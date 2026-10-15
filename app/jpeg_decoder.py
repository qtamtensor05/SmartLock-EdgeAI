from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

import numpy as np
from PIL import Image, UnidentifiedImageError


class InvalidJPEGError(ValueError):
    pass


@dataclass(frozen=True)
class DecodedFrame:
    rgb: np.ndarray
    width: int
    height: int


class JPEGDecoder:
    def __init__(self, max_bytes: int = 1_048_576, max_pixels: int = 1_000_000):
        self.max_bytes = max_bytes
        self.max_pixels = max_pixels

    def decode(self, payload: bytes) -> DecodedFrame:
        if not payload:
            raise InvalidJPEGError("JPEG payload is empty")
        if len(payload) > self.max_bytes:
            raise InvalidJPEGError(f"JPEG payload exceeds {self.max_bytes} bytes")
        try:
            with Image.open(BytesIO(payload)) as image:
                if image.format != "JPEG":
                    raise InvalidJPEGError("Payload is not a JPEG image")
                width, height = image.size
                if width <= 0 or height <= 0 or width * height > self.max_pixels:
                    raise InvalidJPEGError("Decoded image dimensions exceed the safety limit")
                image.load()
                rgb = np.asarray(image.convert("RGB"), dtype=np.uint8).copy()
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            if isinstance(exc, InvalidJPEGError):
                raise
            raise InvalidJPEGError("JPEG decoding failed") from exc
        return DecodedFrame(rgb=rgb, width=width, height=height)
