import pytest

from app.jpeg_decoder import InvalidJPEGError, JPEGDecoder


@pytest.mark.parametrize("size", [(320, 240), (160, 120)])
def test_valid_jpeg_dimensions(jpeg_factory, size):
    frame = JPEGDecoder().decode(jpeg_factory(size))
    assert (frame.width, frame.height) == size
    assert frame.rgb.shape == (size[1], size[0], 3)
    assert frame.rgb.dtype.name == "uint8"


@pytest.mark.parametrize("payload", [b"", b"not a jpeg"])
def test_invalid_jpeg(payload):
    with pytest.raises(InvalidJPEGError):
        JPEGDecoder().decode(payload)


def test_payload_limit():
    with pytest.raises(InvalidJPEGError, match="exceeds"):
        JPEGDecoder(max_bytes=3).decode(b"1234")


def test_pixel_bomb_limit(jpeg_factory):
    with pytest.raises(InvalidJPEGError, match="dimensions"):
        JPEGDecoder(max_pixels=100).decode(jpeg_factory((20, 20)))
