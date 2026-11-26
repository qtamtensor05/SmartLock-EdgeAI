"""Send one live-camera command over USB UART and optionally save a JPEG."""
import argparse
import base64
from pathlib import Path
import time

import serial


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("capture", "enroll", "identify", "list", "delete"))
    parser.add_argument("--port", default="COM5")
    parser.add_argument("--id", type=int, choices=range(1, 33), metavar="1..32")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "output/live/latest.jpg")
    args = parser.parse_args()
    if (args.action in ("enroll", "delete")) != (args.id is not None):
        parser.error("--id is required only for enroll and delete")

    port = serial.Serial(baudrate=115200, timeout=0.25, write_timeout=2)
    port.port = args.port
    port.dtr = False
    port.rts = False
    size = None
    jpeg = bytearray()
    command = args.action if args.id is None else f"{args.action} {args.id}"
    with port:
        time.sleep(1)
        port.reset_input_buffer()
        port.write((command + "\n").encode("ascii"))
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            line = port.readline().strip()
            if not line:
                continue
            if line.startswith(b"ERR "):
                raise RuntimeError(line.decode(errors="replace"))
            if line.startswith(b"JPEG_BEGIN "):
                size = int(line.split()[1])
                if not 0 < size <= 512 * 1024:
                    raise ValueError("Invalid JPEG length")
            elif line == b"JPEG_END" and size is not None:
                if len(jpeg) != size or not jpeg.startswith(b"\xff\xd8") or not jpeg.endswith(b"\xff\xd9"):
                    raise ValueError("Incomplete or invalid JPEG")
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_bytes(jpeg)
                print(args.output.resolve())
                return
            elif size is not None:
                jpeg.extend(base64.b64decode(line, validate=True))
                if len(jpeg) > size:
                    raise ValueError("JPEG exceeds declared length")
            else:
                print(line.decode(errors="replace"))
                if line.startswith(b"REJECT ") or line.startswith((b"ENROLL ", b"DELETE ")):
                    raise SystemExit(0 if line.endswith(b"status=ESP_OK") else 1)
                if line == b"LIST_END" or line.startswith(b"TIME "):
                    return
    raise TimeoutError("No complete reply from the camera firmware")


if __name__ == "__main__":
    main()
