"""protocol.py - the ATOBOT_fw USB serial protocol: D data line, command strings and limits.

The limits must match FRIMWARE/ATOBOT_fw/config.h; the firmware checks them again anyway.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

# ---- Joints (index 0 = ankle, 1 = toe) and limits from config.h ----
JOINTS = ("Ankle", "Toe")
ROM = ((0.0, 80.0), (0.0, 60.0))           # deg
DEFAULT_KP = (10.0, 10.0)                   # Nm/rad
DEFAULT_KD = (0.5, 0.5)                     # Nm*s/rad
KP_LIMIT = 150.0
KD_LIMIT = 3.0
MAX_SPEED = 90.0                            # deg/s
MIN_MOVE_TIME_S = 0.3
MAX_MOVE_TIME_S = 30.0
SINE_MAX_HZ = 2.0

# ---- Enumerations ----
MODE_IDLE, MODE_HOLD, MODE_POSITION, MODE_SINE = range(4)
MODE_NAMES = {MODE_IDLE: "IDLE", MODE_HOLD: "HOLD", MODE_POSITION: "POSITION", MODE_SINE: "SINE"}

STATE_WAIT, STATE_READY, STATE_LOST = range(3)
STATE_NAMES = {STATE_WAIT: "WAIT", STATE_READY: "READY", STATE_LOST: "LOST"}

FAULT_BITS = ((0x1, "feedback lost"), (0x2, "motor error"), (0x4, "over-travel"), (0x8, "over-current"))

MOTOR_ERRORS = {
    0: "none", 1: "motor over-temp", 2: "over-current", 3: "over-voltage",
    4: "under-voltage", 5: "encoder fault", 6: "MOSFET over-temp", 7: "motor lock-up",
}


def fault_texts(faults: int) -> List[str]:
    out = []
    for j, name in enumerate(JOINTS):
        for bit, text in FAULT_BITS:
            if faults & (bit << (4 * j)):
                out.append(f"{name}: {text}")
    return out


# ---- D line ----
JOINT_FIELDS = ("state", "zeroed", "cmd", "pos", "vel", "cur", "torque", "temp", "err", "kp", "kd")
D_FIELD_COUNT = 1 + 3 + 2 * len(JOINT_FIELDS) + 1


@dataclass(slots=True)
class JointData:
    state: int
    zeroed: bool
    cmd: float      # deg
    pos: float      # deg
    vel: float      # deg/s
    cur: float      # A
    torque: float   # Nm
    temp: int       # C
    err: int
    kp: float
    kd: float

    @property
    def ready(self) -> bool:
        return self.state == STATE_READY

    @property
    def usable(self) -> bool:
        return self.state == STATE_READY and self.zeroed


@dataclass(slots=True)
class Sample:
    device_ms: int
    mode: int
    faults: int
    joints: Tuple[JointData, JointData]
    vbus: float


def parse_d(line: str) -> Optional[Sample]:
    """'D,ms,mode,faults,<11 ankle>,<11 toe>,vbus' -> Sample, or None if malformed."""
    p = line.split(",")
    if len(p) != D_FIELD_COUNT or p[0] != "D":
        return None
    try:
        joints = []
        for j in range(2):
            f = p[4 + j * 11: 4 + (j + 1) * 11]
            joints.append(JointData(int(f[0]), f[1] == "1", float(f[2]), float(f[3]), float(f[4]),
                                    float(f[5]), float(f[6]), int(f[7]), int(f[8]), float(f[9]), float(f[10])))
        return Sample(int(p[1]), int(p[2]), int(p[3]), (joints[0], joints[1]), float(p[-1]))
    except ValueError:
        return None


CSV_HEADER = (["pc_time_s", "device_ms", "mode", "faults"]
              + [f"{n.lower()}_{f}" for n in JOINTS for f in JOINT_FIELDS] + ["vbus"])


def csv_row(pc_time: float, s: Sample) -> list:
    row = [f"{pc_time:.3f}", s.device_ms, s.mode, s.faults]
    for j in s.joints:
        row += [j.state, int(j.zeroed), j.cmd, j.pos, j.vel, j.cur, j.torque, j.temp, j.err, j.kp, j.kd]
    return row + [s.vbus]


# ---- Commands ----
def _num(v: Optional[float]) -> str:
    return "-" if v is None else f"{v:.2f}"


def cmd_pos(ankle: Optional[float], toe: Optional[float], time_s: float) -> str:
    return f"POS,{_num(ankle)},{_num(toe)},{time_s:.2f}"


def cmd_sine(c1: Optional[float], a1: float, c2: Optional[float], a2: float, freq: float) -> str:
    return f"SIN,{_num(c1)},{a1:.2f},{_num(c2)},{a2:.2f},{freq:.3f}"


def cmd_gain(joint: int, kp: float, kd: float) -> str:
    return f"GAIN,{joint + 1},{kp:.3f},{kd:.3f}"


def cmd_zero(joint: int) -> str:
    return f"ZERO,{joint + 1}"


def sine_problem(joint: int, center: float, amp: float, freq: float) -> Optional[str]:
    """Same checks as the firmware; None when the sine is allowed."""
    lo, hi = ROM[joint]
    if center - amp < lo or center + amp > hi:
        return f"{JOINTS[joint]}: centre ± amplitude leaves {lo:.0f}–{hi:.0f}°"
    if 2 * math.pi * freq * amp > MAX_SPEED:
        return f"{JOINTS[joint]}: peak {2 * math.pi * freq * amp:.0f}°/s > {MAX_SPEED:.0f}°/s"
    return None
