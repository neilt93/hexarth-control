"""Command-line entry point: `hexarth app`, `hexarth send`, `hexarth drive`, ..."""

from __future__ import annotations

import argparse
import json
import sys
import time

from .client import DEFAULT_HOST, HexArth, HttpTransport, SerialTransport


def _bot(args) -> HexArth:
    transport = (
        SerialTransport(args.serial, args.baud) if args.serial else HttpTransport(args.host)
    )
    return HexArth(transport, max_speed=args.max_speed, max_yaw=args.max_yaw)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="hexarth", description="Control a Waveshare HexArth")
    p.add_argument("--host", default=DEFAULT_HOST, help="robot IP (default %(default)s)")
    p.add_argument("--serial", metavar="PORT", help="use USB serial instead, e.g. /dev/ttyUSB0 or COM3")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--max-speed", type=float, default=0.05, help="X/Y speed limit (default %(default)s)")
    p.add_argument("--max-yaw", type=float, default=0.5, help="turn speed limit (default %(default)s)")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("app", help="run the phone/browser control app")
    a.add_argument("--port", type=int, default=8080)
    a.add_argument("--bind", default="0.0.0.0")

    s = sub.add_parser("send", help="send one raw JSON command")
    s.add_argument("json", help='e.g. \'{"T":126}\'')

    sub.add_parser("imu", help="print IMU data")
    sub.add_parser("stop", help="stop moving")

    d = sub.add_parser("drive", help="move for a fixed time then stop")
    d.add_argument("--x", type=float, default=0.0)
    d.add_argument("--y", type=float, default=0.0)
    d.add_argument("--yaw", type=float, default=0.0)
    d.add_argument("--seconds", type=float, default=2.0)

    sub.add_parser("keys", help="drive with the keyboard (WASD / QE, space=stop)")

    args = p.parse_args(argv)
    bot = _bot(args)

    if args.cmd == "app":
        from .server import serve
        serve(bot, args.bind, args.port)
    elif args.cmd == "send":
        print(json.dumps(bot.send(json.loads(args.json)), indent=2))
    elif args.cmd == "imu":
        print(json.dumps(bot.imu(), indent=2))
    elif args.cmd == "stop":
        bot.stop()
    elif args.cmd == "drive":
        with bot:
            end = time.monotonic() + args.seconds
            while time.monotonic() < end:
                bot.move(args.x, args.y, args.yaw)
                time.sleep(0.2)
    elif args.cmd == "keys":
        _keyboard(bot)
    return 0


def _keyboard(bot: HexArth) -> None:
    import termios
    import tty

    keymap = {
        "w": (1, 0, 0), "s": (-1, 0, 0), "a": (0, 1, 0), "d": (0, -1, 0),
        "q": (0, 0, 1), "e": (0, 0, -1), " ": (0, 0, 0),
    }
    print("W/S fwd/back  A/D strafe  Q/E turn  SPACE stop  X quit")
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        with bot:
            while True:
                ch = sys.stdin.read(1).lower()
                if ch == "x":
                    break
                if ch in keymap:
                    fx, fy, fyaw = keymap[ch]
                    bot.move(fx * bot.max_speed, fy * bot.max_speed, fyaw * bot.max_yaw)
                    # keyboard has no "key held" signal, so keep the deadman alive
                    bot.deadman_s = float("inf")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


if __name__ == "__main__":
    sys.exit(main())
