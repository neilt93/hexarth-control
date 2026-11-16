# hexarth-control

A Python library, CLI, and phone/browser control app for the
[Waveshare HexArth](https://www.waveshare.com/wiki/HexArth), an 18-DOF hexapod robot.

The ESP32 inside the robot already handles inverse kinematics, gaits (tripod
and self-balancing), and Wi-Fi, so **the stock firmware stays on the robot**.
This repo is the "upper computer" side: it sends the robot JSON commands.

```
 phone / browser ──HTTP──▶  hexarth app (laptop or Raspberry Pi) ──Wi-Fi or USB──▶  HexArth ESP32
                            • serves the control UI                                   {"T":1,"X":..,"Y":..,"Yaw":..}
                            • 2 Hz heartbeat + dead-man stop
```

## 1. Get the robot running

1. Charge and insert the 3S2P 18650 battery pack (sold separately), then power on.
2. The robot creates a Wi-Fi hotspot. Connect to **`HexArth`**, password **`12345678`**.
3. Optional: open <http://192.168.4.1> in Chrome to check Waveshare's built-in web UI.
   It also lists every JSON command your firmware version supports.

## 2. Install

Requires Python 3.9 or newer.

```bash
git clone <this repo> && cd hexarth-control
pip install -e .            # add [serial] for USB control: pip install -e ".[serial]"
```

## 3. Run the control app

On the computer that's connected to the `HexArth` Wi-Fi:

```bash
hexarth app
```

Open <http://localhost:8080>. To use your phone as the controller, connect the
phone to the same `HexArth` hotspot and open `http://<computer's IP>:8080`.

- **Left pad:** forward, back, and strafe. **Right pad:** turn. **Slider:** speed.
- **Keyboard:** W/S, A/D, Q/E, and space to stop.
- **IMU panel:** live orientation data. **Raw JSON:** send any command.
- **Safety:** the robot stops if you let go, the page goes to the background,
  or the app stops sending updates for 1 s.

Over USB instead of Wi-Fi: `hexarth --serial /dev/ttyUSB0 app` (on Windows, `COM3`).

## CLI

```bash
hexarth imu                                     # read IMU
hexarth drive --x 0.03 --seconds 2              # walk forward 2 s
hexarth drive --yaw 0.3 --seconds 3             # turn in place
hexarth keys                                    # drive with WASD in the terminal
hexarth send '{"T":126}'                        # any raw JSON command
hexarth --max-speed 0.08 --max-yaw 0.8 app      # raise the speed limits
```

## Python

```python
from hexarth import HexArth, HttpTransport

with HexArth(HttpTransport("192.168.4.1")) as bot:   # starts the heartbeat
    bot.move(x=0.03)          # forward
    ...                       # call move() again at least every 1 s to keep going
    print(bot.imu())
    bot.send({"T": 126})      # raw command
# leaving the block stops the robot
```

## Protocol notes

| Command | JSON | Notes |
|---|---|---|
| Speed control | `{"T":1,"X":0.02,"Y":0.02,"Yaw":0.3}` | X = forward, Y = sideways, Yaw = turn. The robot stops if no new command arrives within 3 s. |
| IMU data | `{"T":126}` | Returns the quaternion and raw per-axis readings. |

- Wi-Fi: `GET http://192.168.4.1/js?json=<url-encoded JSON>`
- USB serial: newline-terminated JSON at 115200 baud

The full command list (OLED, LEDs, Wi-Fi config, posture, servos, and more) is
defined in the firmware's `json_cmd.h` and shown on the robot's web page. Send
any of them with `hexarth send` or the Raw JSON box. Add the ones you use to
`hexarth/commands.py`.

The default limits (`max_speed 0.05`, `max_yaw 0.5`) are deliberately cautious.
Waveshare's example values are 0.02 and 0.3. Raise the limits once you've seen how the robot moves.

## Development

```bash
pip install -e ".[dev]" && pytest
```

The tests run against a fake robot, so no hardware is needed.
