"""Local browser interface for ESP32 camera preview and enrollment."""
import argparse
import base64
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit
import serial


HERE = Path(__file__).resolve().parent
CAPTURE = HERE.parent / "output/live/latest.jpg"
ENROLL_CAPTURE = CAPTURE.with_name("enrollment.jpg")
PAGE = HERE / "live_camera_web.html"


def serve(port, http_port, baud):
    serial_lock = threading.Lock()
    uart = serial.Serial(baudrate=baud, timeout=0.25, write_timeout=2)
    uart.port = port
    uart.dtr = False
    uart.rts = False

    def exchange(action, person=None):
        if not uart.is_open:
            uart.open()
            time.sleep(1)
            uart.reset_input_buffer()
        command = action if person is None else f"enroll-frame {person}"
        deadline = time.monotonic() + 20
        size = None
        jpeg = bytearray()
        reply = []
        try:
            uart.write((command + "\n").encode("ascii"))
            while time.monotonic() < deadline:
                line = uart.readline().strip()
                if not line:
                    continue
                if line.startswith(b"ERR "):
                    return False, line.decode(errors="replace")
                if action in ("capture", "enroll"):
                    if line.startswith(b"JPEG_BEGIN "):
                        size = int(line.split()[1])
                        if not 0 < size <= 512 * 1024:
                            raise ValueError("Invalid JPEG length")
                    elif size is not None and line == b"JPEG_END":
                        if len(jpeg) != size or not jpeg.startswith(b"\xff\xd8") or not jpeg.endswith(b"\xff\xd9"):
                            raise ValueError("Invalid JPEG received")
                        if action == "capture":
                            return True, bytes(jpeg)
                        ENROLL_CAPTURE.parent.mkdir(parents=True, exist_ok=True)
                        ENROLL_CAPTURE.write_bytes(jpeg)
                        size = None
                        continue
                    elif size is not None:
                        jpeg.extend(base64.b64decode(line, validate=True))
                        if len(jpeg) > size:
                            raise ValueError("JPEG exceeds declared length")
                if action != "capture" and line.startswith((b"ENROLL ", b"REJECT ")):
                    return line.endswith(b"status=ESP_OK"), line.decode(errors="replace")
                elif line.startswith(b"TIME "):
                    return True, "\n".join(reply + [line.decode(errors="replace")])
                elif line.startswith(b"MATCH ") or line == b"UNKNOWN":
                    reply.append(line.decode(errors="replace"))
            raise TimeoutError("ESP32 did not return a complete reply")
        except (OSError, ValueError):
            uart.close()
            raise

    class Handler(BaseHTTPRequestHandler):
        def send_data(self, status, content_type, body):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def send_json(self, status, **payload):
            self.send_data(status, "application/json", json.dumps(payload).encode())

        def do_GET(self):
            if urlsplit(self.path).path == "/":
                self.send_data(200, "text/html; charset=utf-8", PAGE.read_bytes())
            elif urlsplit(self.path).path == "/enrollment.jpg" and ENROLL_CAPTURE.is_file():
                self.send_data(200, "image/jpeg", ENROLL_CAPTURE.read_bytes())
            elif self.path == "/frame.jpg":
                try:
                    with serial_lock:
                        ok, frame = exchange("capture")
                        if not ok:
                            self.send_json(502, message=frame)
                            return
                        CAPTURE.parent.mkdir(parents=True, exist_ok=True)
                        CAPTURE.write_bytes(frame)
                    self.send_data(200, "image/jpeg", frame)
                except (OSError, ValueError) as exc:
                    self.send_json(502, message=str(exc))
            else:
                self.send_error(404)

        def do_POST(self):
            if self.path not in ("/enroll", "/identify"):
                self.send_error(404)
                return
            # Only the page on this loopback server may submit camera mutations.
            if (self.headers.get("Origin") != f"http://127.0.0.1:{http_port}"
                    or self.headers.get_content_type() != "application/json"):
                self.send_error(403)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 1 <= length <= 128:
                    raise ValueError
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError
                person = payload.get("id")
                if self.path == "/enroll" and (type(person) is not int or not 1 <= person <= 32):
                    raise ValueError
            except ValueError:
                self.send_json(400, message="ID đăng ký phải là số nguyên từ 1 đến 32.")
                return
            try:
                with serial_lock:
                    if self.path == "/enroll":
                        ENROLL_CAPTURE.unlink(missing_ok=True)
                    ok, message = exchange(self.path[1:], person if self.path == "/enroll" else None)
                    has_frame = self.path == "/enroll" and ENROLL_CAPTURE.is_file()
                self.send_json(200 if ok else 422, message=message, has_frame=has_frame)
            except (OSError, ValueError) as exc:
                self.send_json(502, message=str(exc))

    with ThreadingHTTPServer(("127.0.0.1", http_port), Handler) as server:
        print(f"http://127.0.0.1:{http_port}", flush=True)
        try:
            server.serve_forever()
        finally:
            uart.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="COM5")
    parser.add_argument("--http-port", type=int, default=8092)
    parser.add_argument("--baud", type=int, choices=(115200, 460800), default=460800)
    args = parser.parse_args()
    serve(args.port, args.http_port, args.baud)
