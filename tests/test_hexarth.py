"""Tests against a fake robot that mimics the HexArth's /js?json= endpoint."""

import json
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from hexarth import HexArth, HttpTransport
from hexarth.server import make_handler


class FakeRobot:
    def __init__(self):
        self.received = []
        robot = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                q = urllib.parse.urlparse(self.path)
                assert q.path == "/js"
                cmd = json.loads(urllib.parse.parse_qs(q.query)["json"][0])
                robot.received.append(cmd)
                reply = {"T": 1126, "q0": 1, "q1": 0, "q2": 0, "q3": 0} if cmd["T"] == 126 else {}
                body = json.dumps(reply).encode()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(body)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.host = f"127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def speeds(self):
        return [c for c in self.received if c["T"] == 1]

    def close(self):
        self.httpd.shutdown()


@pytest.fixture
def robot():
    r = FakeRobot()
    yield r
    r.close()


def test_move_sends_speed_cmd_and_clamps(robot):
    bot = HexArth(HttpTransport(robot.host), max_speed=0.05, max_yaw=0.5)
    bot.move(1.0, -0.02, 9)
    assert robot.speeds()[-1] == {"T": 1, "X": 0.05, "Y": -0.02, "Yaw": 0.5}


def test_imu(robot):
    bot = HexArth(HttpTransport(robot.host))
    assert bot.imu()["q0"] == 1
    assert robot.received[-1] == {"T": 126}


def test_heartbeat_resends_and_deadman_stops(robot):
    bot = HexArth(HttpTransport(robot.host), heartbeat_s=0.05, deadman_s=0.2).start()
    try:
        bot.move(0.03, 0, 0)
        time.sleep(0.12)
        assert sum(1 for c in robot.speeds() if c["X"] == 0.03) >= 2  # kept alive
        time.sleep(0.3)  # no refresh -> deadman
        assert robot.speeds()[-1]["X"] == 0
        assert bot.velocity == (0.0, 0.0, 0.0)
    finally:
        bot.close()


def test_app_server_endpoints(robot):
    bot = HexArth(HttpTransport(robot.host), max_speed=0.04, max_yaw=0.4)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(bot))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"

    def post(path, obj):
        req = urllib.request.Request(base + path, json.dumps(obj).encode(),
                                     {"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req).read())

    try:
        assert b"HexArth" in urllib.request.urlopen(base + "/").read()
        post("/api/move", {"x": 0.5, "y": 0, "yaw": -1})
        assert robot.speeds()[-1] == {"T": 1, "X": 0.02, "Y": 0.0, "Yaw": -0.4}
        post("/api/stop", {})
        assert robot.speeds()[-1]["X"] == 0
        assert post("/api/raw", {"cmd": {"T": 126}})["reply"]["q0"] == 1
        st = json.loads(urllib.request.urlopen(base + "/api/status").read())
        assert st["error"] is None
    finally:
        httpd.shutdown()
