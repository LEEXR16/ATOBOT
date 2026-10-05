"""simulator.py - stands in for the Teensy + 2 motors so the GUI can be tried without hardware.

Speaks the same protocol as ATOBOT_fw (same modes, checks and replies) with simple joint physics:
the motor PD (Kp, Kd) drives an inertia. Choose "Simulator" as the port.
"""
from __future__ import annotations

import math
import random
import time

from PySide6.QtCore import QObject, QTimer, Signal

from core import protocol as P

DT = 0.002                      # physics step, s
INERTIA = 0.01                  # kg*m^2 at the joint
FRICTION = 0.05                 # Nm*s/rad
NM_PER_AMP = 0.12 * 39


def _min_jerk(s: float) -> float:
    s = min(max(s, 0.0), 1.0)
    return s ** 3 * (10 - 15 * s + 6 * s * s)


class _Joint:
    def __init__(self, j: int):
        self.raw = random.uniform(-15, 15)    # motor position before zeroing, deg
        self.vel = 0.0
        self.offset = 0.0
        self.zeroed = False
        self.cmd = 0.0
        self.kp, self.kd = P.DEFAULT_KP[j], P.DEFAULT_KD[j]
        self.torque = 0.0
        self.move_start = self.move_goal = 0.0
        self.center = self.amp = 0.0

    @property
    def pos(self) -> float:
        return self.raw - self.offset


class Simulator(QObject):
    lineOut = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.j = [_Joint(0), _Joint(1)]
        self.mode = P.MODE_IDLE
        self.faults = 0
        self.streaming = False
        self.t0 = time.monotonic()
        self.move_t0 = 0.0
        self.move_dur = 1.0
        self.sine_f = 0.0
        self.sine_t0 = 0.0
        self.sine_approach = False
        self._last_tel = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(10)
        self._last = time.monotonic()
        QTimer.singleShot(50, self._boot)

    def _boot(self) -> None:
        self._out("V,ATOBOT_sim,0.1")
        for i, name in enumerate(("ANKLE", "TOE")):
            self._out(f"I,{name} first feedback: pos {self.j[i].pos:+.1f} deg. READY (limp, not zeroed)")

    def stop(self) -> None:
        self._timer.stop()

    def _out(self, line: str) -> None:
        self.lineOut.emit(line)

    def _now(self) -> float:
        return time.monotonic() - self.t0

    # ---- commands ----
    def handle_line(self, line: str) -> None:
        p = [x.strip() for x in line.split(",")]
        c = p[0].upper()
        if c == "PING":
            return
        if c == "VER":
            return self._out("V,ATOBOT_sim,0.1")
        if c == "STREAM":
            self.streaming = len(p) > 1 and p[1] != "0"
            return self._ok(c)
        try:
            err = getattr(self, f"_cmd_{c.lower()}", None)
            if err is None:
                return self._out(f"E,{c}: unknown command (H for help)")
            reason = err(p[1:])
        except (ValueError, IndexError):
            reason = "bad arguments"
        if reason:
            self._out(f"E,{c}: {reason}")
        else:
            self._ok(c)

    def _ok(self, c: str) -> None:
        self._out(f"OK,{c}")

    def _set_mode(self, m: int, why: str) -> None:
        if m == self.mode:
            return
        if self.mode == P.MODE_IDLE:
            for jt in self.j:
                jt.cmd = jt.pos
        self._out(f"I,mode {P.MODE_NAMES[self.mode]} -> {P.MODE_NAMES[m]} ({why})")
        self.mode = m

    @staticmethod
    def _f(s: str):
        return None if s == "-" else float(s)

    def _cmd_en(self, a):
        if self.faults:
            return "fault active, CLR first"
        if self.mode == P.MODE_IDLE:
            self._set_mode(P.MODE_HOLD, "EN")

    def _cmd_dis(self, a):
        self._set_mode(P.MODE_IDLE, "DIS")

    def _cmd_stop(self, a):
        if self.mode in (P.MODE_POSITION, P.MODE_SINE):
            self._set_mode(P.MODE_HOLD, "STOP")

    def _cmd_clr(self, a):
        if self.mode != P.MODE_IDLE:
            return "only in IDLE"
        self.faults = 0

    def _cmd_zero(self, a):
        if self.mode != P.MODE_IDLE:
            return "disable (DIS) before ZERO"
        jt = self.j[int(a[0]) - 1]
        jt.offset = jt.raw
        jt.zeroed = True
        self._out(f"I,{P.JOINTS[int(a[0]) - 1].upper()} zeroed (pos +0.0 deg)")

    def _cmd_gain(self, a):
        jt = self.j[int(a[0]) - 1]
        kp, kd = float(a[1]), float(a[2])
        if not 0 <= kp <= P.KP_LIMIT:
            return "Kp out of range"
        if not 0 <= kd <= P.KD_LIMIT:
            return "Kd out of range"
        jt.kp, jt.kd = kp, kd

    def _move_time(self, dist: float, requested: float) -> float:
        return max(requested, 1.875 * dist / P.MAX_SPEED, P.MIN_MOVE_TIME_S)

    def _cmd_pos(self, a):
        if self.mode == P.MODE_IDLE:
            return "not enabled (EN)"
        targets, t = [self._f(a[0]), self._f(a[1])], float(a[2])
        if not 0 <= t <= P.MAX_MOVE_TIME_S:
            return "time out of range"
        dist, any_ = 0.0, False
        for i, (jt, tg) in enumerate(zip(self.j, targets)):
            jt.move_start = jt.move_goal = jt.cmd
            if tg is None:
                continue
            if not jt.zeroed:
                return "joint not zeroed"
            lo, hi = P.ROM[i]
            if not lo <= tg <= hi:
                return "target outside ROM"
            jt.move_goal = tg
            dist = max(dist, abs(tg - jt.move_start))
            any_ = True
        if not any_:
            return "no joint to move"
        self.move_dur = self._move_time(dist, t)
        if self.move_dur > t + 0.01:
            self._out(f"I,move time raised to {self.move_dur:.2f} s (max {P.MAX_SPEED:.0f} deg/s)")
        self.move_t0 = self._now()
        self.sine_approach = False
        self._set_mode(P.MODE_POSITION, "POS")

    def _cmd_sin(self, a):
        if self.mode == P.MODE_IDLE:
            return "not enabled (EN)"
        cen, amp, f = [self._f(a[0]), self._f(a[2])], [float(a[1]), float(a[3])], float(a[4])
        if not 0 < f <= P.SINE_MAX_HZ:
            return "frequency out of range"
        dist, any_ = 0.0, False
        for i, jt in enumerate(self.j):
            jt.move_start = jt.move_goal = jt.center = jt.cmd
            jt.amp = 0.0
            if cen[i] is None:
                continue
            if not jt.zeroed:
                return "joint not zeroed"
            problem = P.sine_problem(i, cen[i], amp[i], f)
            if problem:
                return problem
            jt.move_goal = jt.center = cen[i]
            jt.amp = amp[i]
            dist = max(dist, abs(cen[i] - jt.move_start))
            any_ = True
        if not any_:
            return "no joint in the sine"
        self.sine_f = f
        self.move_dur = self._move_time(dist, 1.0)
        self.move_t0 = self._now()
        self.sine_approach = True
        self._set_mode(P.MODE_SINE, "SIN")

    # ---- physics + control ----
    def _tick(self) -> None:
        now_m = time.monotonic()
        steps = min(int((now_m - self._last) / DT), 50)
        self._last += steps * DT
        for _ in range(steps):
            self._step()
        now = self._now()
        if not self.streaming:
            self._last_tel = now
            return
        while now - self._last_tel >= 0.01:          # exact 10 ms device clock, like the firmware
            self._last_tel += 0.01
            self._telemetry(self._last_tel)

    def _step(self) -> None:
        now = self._now()
        s = (now - self.move_t0) / self.move_dur
        ts = now - self.sine_t0
        env = min(ts / 2.0, 1.0)
        for i, jt in enumerate(self.j):
            if self.mode == P.MODE_IDLE:
                jt.cmd = jt.pos
                tau = 0.0
            else:
                if jt.zeroed:
                    if self.mode == P.MODE_POSITION or (self.mode == P.MODE_SINE and self.sine_approach):
                        jt.cmd = jt.move_start + (jt.move_goal - jt.move_start) * _min_jerk(s)
                    elif self.mode == P.MODE_SINE:
                        jt.cmd = jt.center + env * jt.amp * math.sin(2 * math.pi * self.sine_f * ts)
                    lo, hi = P.ROM[i]
                    jt.cmd = min(max(jt.cmd, lo), hi)
                tau = jt.kp * math.radians(jt.cmd - jt.pos) - jt.kd * math.radians(jt.vel)
            acc = (tau - FRICTION * math.radians(jt.vel)) / INERTIA
            jt.vel += math.degrees(acc) * DT
            jt.raw += jt.vel * DT
            jt.torque = tau
        if s >= 1.0:
            if self.mode == P.MODE_POSITION:
                self._set_mode(P.MODE_HOLD, "move done")
            elif self.mode == P.MODE_SINE and self.sine_approach:
                self.sine_approach = False
                self.sine_t0 = now
                self._out("I,sine started")

    def _telemetry(self, now: float) -> None:
        parts = [f"D,{int(now * 1000)},{self.mode},{self.faults}"]
        for jt in self.j:
            cur = jt.torque / NM_PER_AMP + random.gauss(0, 0.01)
            parts.append(f"1,{int(jt.zeroed)},{jt.cmd:.2f},{round(jt.pos, 1):.2f},{jt.vel:.1f},"
                         f"{cur:.2f},{cur * NM_PER_AMP:.2f},{31 + random.randint(0, 1)},0,{jt.kp:.2f},{jt.kd:.3f}")
        parts.append("0.0")
        self._out(",".join(parts))
