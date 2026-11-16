"""JSON command type codes for the Waveshare HexArth.

Every command is a JSON object with a "T" field giving its type. The firmware
defines the full list in ``json_cmd.h``. Only the codes below are confirmed
from Waveshare's documentation; anything else can be sent with
``HexArth.send({...})`` once you have looked it up in the web UI at
http://192.168.4.1 (the command list is printed under the input box).
"""

# {"T":1,"X":0.02,"Y":0.02,"Yaw":0.3}
# X/Y = translation speed, Yaw = rotation speed. The firmware stops the robot
# if no new speed command arrives within 3 seconds.
CMD_SPEED_CTRL = 1

# {"T":126} -> returns IMU quaternion and raw per-axis data.
CMD_GET_IMU_DATA = 126

# Firmware watchdog: robot halts after this long without a movement command.
FIRMWARE_TIMEOUT_S = 3.0
