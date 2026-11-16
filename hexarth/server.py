"""Control-app server: serves the web UI and relays commands to the robot.

Run on a laptop or Raspberry Pi that is on the robot's network (or plugged
into it over USB), then open http://<this-machine>:8080 on your phone.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources

from .client import HexArth


def make_handler(bot: HexArth):
    index_html = resources.files("hexarth").joinpath("web/index.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # quieter: joystick posts ~10x/s
            pass

        def _json(self, code: int, obj) -> None:
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(index_html)))
                self.end_headers()
                self.wfile.write(index_html)
            elif self.path == "/api/status":
                x, y, yaw = bot.velocity
                self._json(200, {
                    "velocity": {"x": x, "y": y, "yaw": yaw},
                    "max_speed": bot.max_speed, "max_yaw": bot.max_yaw,
                    "error": bot.last_error,
                })
            elif self.path == "/api/imu":
                try:
                    self._json(200, {"imu": bot.imu()})
                except Exception as e:
                    self._json(502, {"error": str(e)})
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self):
            try:
                data = self._body()
                if self.path == "/api/move":
                    # x, y, yaw are fractions in [-1, 1] scaled by max limits
                    bot.move(
                        float(data.get("x", 0)) * bot.max_speed,
                        float(data.get("y", 0)) * bot.max_speed,
                        float(data.get("yaw", 0)) * bot.max_yaw,
                    )
                    self._json(200, {"ok": True})
                elif self.path == "/api/stop":
                    bot.stop()
                    self._json(200, {"ok": True})
                elif self.path == "/api/raw":
                    cmd = data.get("cmd")
                    if not isinstance(cmd, dict) or "T" not in cmd:
                        return self._json(400, {"error": 'cmd must be an object with a "T" field'})
                    self._json(200, {"reply": bot.send(cmd)})
                else:
                    self._json(404, {"error": "not found"})
            except (ValueError, json.JSONDecodeError) as e:
                self._json(400, {"error": str(e)})
            except Exception as e:
                self._json(502, {"error": f"robot: {e}"})

    return Handler


def serve(bot: HexArth, host: str = "0.0.0.0", port: int = 8080) -> None:
    bot.start()
    httpd = ThreadingHTTPServer((host, port), make_handler(bot))
    print(f"HexArth control app on http://{host}:{port}  (Ctrl+C to quit)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        bot.close()
