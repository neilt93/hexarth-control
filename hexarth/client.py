"""Client for talking to a Waveshare HexArth over Wi-Fi (HTTP) or USB serial."""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
from typing import Any, Protocol

from .commands import CMD_GET_IMU_DATA, CMD_SPEED_CTRL

DEFAULT_HOST = "192.168.4.1"


class Transport(Protocol):
    def send(self, cmd: dict[str, Any]) -> str: ...
    def close(self) -> None: ...


class HttpTransport:
    """Sends commands as GET http://<host>/js?json=<url-encoded JSON>."""

    def __init__(self, host: str = DEFAULT_HOST, timeout: float = 2.0):
        self.host = host
        self.timeout = timeout

    def send(self, cmd: dict[str, Any]) -> str:
        payload = json.dumps(cmd, separators=(",", ":"))
        url = f"http://{self.host}/js?json={urllib.parse.quote(payload)}"
        with urllib.request.urlopen(url, timeout=self.timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")

    def close(self) -> None:
        pass


class SerialTransport:
    """Sends newline-terminated JSON over the ESP32's USB serial port."""

    def __init__(self, port: str, baud: int = 115200, timeout: float = 0.5):
        try:
            import serial  # pyserial
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("Serial needs pyserial: pip install pyserial") from e
        self._ser = serial.Serial(port, baud, timeout=timeout)
        self._lock = threading.Lock()

    def send(self, cmd: dict[str, Any]) -> str:
        line = json.dumps(cmd, separators=(",", ":")) + "\n"
        with self._lock:
            self._ser.reset_input_buffer()
            self._ser.write(line.encode())
            return self._ser.readline().decode("utf-8", errors="replace").strip()

    def close(self) -> None:
        self._ser.close()


def _clamp(v: float, limit: float) -> float:
    return max(-limit, min(limit, float(v)))


class HexArth:
    """High-level control.

    A background heartbeat resends the current velocity so the firmware's
    3-second watchdog never stops a robot you are still driving. If the
    velocity isn't refreshed within ``deadman_s`` (e.g. the app disconnected),
    the heartbeat sends zero instead, so a lost controller always stops it.
    """

    def __init__(
        self,
        transport: Transport | None = None,
        *,
        max_speed: float = 0.05,
        max_yaw: float = 0.5,
        heartbeat_s: float = 0.5,
        deadman_s: float = 1.0,
    ):
        self.transport = transport or HttpTransport()
        self.max_speed = max_speed
        self.max_yaw = max_yaw
        self.heartbeat_s = heartbeat_s
        self.deadman_s = deadman_s
        self._vel = (0.0, 0.0, 0.0)
        self._vel_time = 0.0
        self._lock = threading.Lock()
        self._stop_evt = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_error: str | None = None

    # -- raw ---------------------------------------------------------------
    def send(self, cmd: dict[str, Any]) -> Any:
        """Send any JSON command; returns parsed JSON reply when possible."""
        try:
            raw = self.transport.send(cmd)
            self.last_error = None
        except Exception as e:
            self.last_error = str(e)
            raise
        try:
            return json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return raw

    # -- motion ------------------------------------------------------------
    def move(self, x: float = 0.0, y: float = 0.0, yaw: float = 0.0) -> None:
        """Set velocity. Values are clamped to max_speed / max_yaw."""
        vel = (_clamp(x, self.max_speed), _clamp(y, self.max_speed), _clamp(yaw, self.max_yaw))
        with self._lock:
            changed = vel != self._vel
            self._vel = vel
            self._vel_time = time.monotonic()
        if changed or self._thread is None:
            self._send_vel(vel)

    def stop(self) -> None:
        with self._lock:
            self._vel = (0.0, 0.0, 0.0)
            self._vel_time = time.monotonic()
        self._send_vel(self._vel)

    def _send_vel(self, vel: tuple[float, float, float]) -> None:
        x, y, yaw = vel
        self.send({"T": CMD_SPEED_CTRL, "X": round(x, 4), "Y": round(y, 4), "Yaw": round(yaw, 4)})

    @property
    def velocity(self) -> tuple[float, float, float]:
        return self._vel

    # -- sensors -----------------------------------------------------------
    def imu(self) -> Any:
        return self.send({"T": CMD_GET_IMU_DATA})

    # -- heartbeat ---------------------------------------------------------
    def start(self) -> "HexArth":
        if self._thread is None:
            self._stop_evt.clear()
            self._thread = threading.Thread(target=self._heartbeat, daemon=True)
            self._thread.start()
        return self

    def _heartbeat(self) -> None:
        while not self._stop_evt.wait(self.heartbeat_s):
            with self._lock:
                vel = self._vel
                stale = time.monotonic() - self._vel_time > self.deadman_s
                if stale and vel != (0.0, 0.0, 0.0):
                    vel = self._vel = (0.0, 0.0, 0.0)
            try:
                self._send_vel(vel)
            except Exception:
                pass  # recorded in last_error; keep trying

    def close(self) -> None:
        self._stop_evt.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        try:
            self.stop()
        except Exception:
            pass
        self.transport.close()

    def __enter__(self) -> "HexArth":
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.close()
