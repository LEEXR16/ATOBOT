"""game.py - "Ankle Flyer": a Flappy-Bird style game played with the ankle (or toe) angle.

The bird's height IS the joint angle (no gravity), so every gap is a range-of-motion target.
  Hand mode : motors limp (IDLE), the player moves the joint and the bird follows it.
  Robot mode: motors enabled, the game sends POS moves so the robot flies through the gaps.
No firmware changes: it only reads the D stream and sends the normal POS command.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable, List, Optional

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from core import protocol as P
from core.link import Link
from core.model import Model
from ui import theme

FPS = 60
W, H = 1600.0, 900.0              # world size; the view scales it to fit
TOP, BOTTOM = 70.0, 820.0         # flying area (screen y of angle "max" and "min")
BIRD_X, BIRD_R = 420.0, 26.0
HIT_R = BIRD_R * 0.8              # a little forgiveness
PIPE_W = 130.0
CALIBRATE_S = 6.0
MIN_SPAN_DEG = 10.0
ROBOT_MARGIN_DEG = 3.0            # robot targets stay this far inside the ROM
ROBOT_LEAD_PX = 40.0              # robot arrives this far before the pipe
SPEEDUP_PER_POINT = 0.015         # +1.5 % speed per point ...
SPEEDUP_MAX_POINTS = 20           # ... up to +30 %

READY, CALIB, PLAYING, OVER = "ready", "calib", "playing", "over"


@dataclass
class Level:
    speed: float       # px/s at the start
    gap: float         # gap height, fraction of the flying area
    spacing: float     # px between pipes at the start speed (time between pipes stays constant)
    max_jump: float    # max change of the gap centre from one pipe to the next, fraction


LEVELS = {
    "Easy": Level(170, 0.42, 580, 0.45),
    "Normal": Level(230, 0.34, 540, 0.60),
    "Hard": Level(300, 0.27, 500, 0.75),
}


@dataclass
class Pipe:
    x: float
    centre: float      # gap centre, 0 = range min .. 1 = range max
    scored: bool = False
    targeted: bool = False


def _clamp(v: float, lo: float, hi: float) -> float:
    return min(max(v, lo), hi)


def _font(px: int, bold: bool = False, family: str = "Segoe UI") -> QFont:
    f = QFont(family)
    f.setPixelSize(px)
    f.setBold(bold)
    return f


class GameView(QWidget):
    """Game logic + drawing. Space starts / restarts."""

    stateChanged = Signal(str)
    rangeChanged = Signal(float, float)

    def __init__(self, model: Model, link: Link, live: Callable[[], bool], parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(480, 300)
        self.model, self.link, self._live = model, link, live
        self.joint = 0
        self.robot = False
        self.level = LEVELS["Normal"]
        self.lo, self.hi = P.ROM[0]
        self.state = READY
        self.pipes: List[Pipe] = []
        self.score = self.best = 0
        self.bird_n = 0.5            # bird height, 0..1 of the range
        self.bird_v = 0.0            # its speed, range/s (for the tilt)
        self.reason = ""             # why the last round ended early
        self._t_start = self._t_end = 0.0
        self._used = [0.0, 0.0]      # angle min/max reached in the round (or calibration)
        self._calib_t0 = 0.0
        self._last_centre = 0.5
        self._stars = [[random.uniform(0, W), random.uniform(0, BOTTOM), random.uniform(0.8, 2.4),
                        random.uniform(0.1, 0.6)] for _ in range(90)]
        self._last = time.monotonic()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(int(1000 / FPS))

    # ================= Settings =================

    def set_joint(self, j: int) -> None:
        self.halt()
        self.joint = j
        self.set_range(*P.ROM[j])

    def set_robot(self, robot: bool) -> None:
        self.halt()
        self.robot = robot

    def set_level(self, name: str) -> None:
        self.halt()
        self.level = LEVELS[name]

    def set_range(self, lo: float, hi: float) -> None:
        self.lo, self.hi = lo, hi
        self.rangeChanged.emit(lo, hi)

    # ================= State =================

    def angle(self) -> Optional[float]:
        s = self.model.latest
        if s is None or not self._live():
            return None
        return s.joints[self.joint].pos

    def problem(self, robot: Optional[bool] = None) -> Optional[str]:
        """Why a round can't run right now (None = good to go)."""
        robot = self.robot if robot is None else robot
        name = P.JOINTS[self.joint]
        s = self.model.latest
        if s is None or not self._live():
            return "Connect (or pick the Simulator port) to play."
        d = s.joints[self.joint]
        if not d.ready:
            return f"{name} motor is not READY."
        if not d.zeroed:
            return f"Zero the {name.lower()} first (Motors card)."
        if s.faults:
            return "Clear the faults first."
        if robot and s.mode == P.MODE_IDLE:
            return "Robot mode: press Enable first."
        if not robot and s.mode != P.MODE_IDLE:
            return "Hand mode: press Disable so the joint is limp."
        return None

    def _set_state(self, st: str) -> None:
        self.state = st
        self.stateChanged.emit(st)

    def start(self) -> None:
        if self.state in (PLAYING, CALIB) or self.problem():
            return
        self.pipes, self.score, self.reason = [], 0, ""
        self._last_centre = 0.5
        x = W + 150
        while x < W + 2 * self.level.spacing:
            self._add_pipe(x)
            x += self.level.spacing
        a = self.angle()
        self._used = [a, a] if a is not None else [self.lo, self.lo]
        self._t_start = time.monotonic()
        self._set_state(PLAYING)
        self.setFocus()

    def calibrate(self) -> None:
        if self.state in (PLAYING, CALIB) or self.problem(robot=False):
            return
        a = self.angle()
        self._used = [a, a]
        self._calib_t0 = time.monotonic()
        self._set_state(CALIB)

    def halt(self, reason: str = "Stopped") -> None:
        if self.state == PLAYING:
            self._game_over(reason)
        elif self.state == CALIB:
            self._set_state(READY)

    def _game_over(self, reason: str = "") -> None:
        self.reason = reason
        self._t_end = time.monotonic()
        self.best = max(self.best, self.score)
        self._set_state(OVER)

    # ================= Loop =================

    def _speed(self) -> float:
        return self.level.speed * (1 + SPEEDUP_PER_POINT * min(self.score, SPEEDUP_MAX_POINTS))

    def _add_pipe(self, x: float) -> None:
        lim = self.level.gap / 2 + 0.05
        c = self._last_centre + random.uniform(-self.level.max_jump, self.level.max_jump)
        c = _clamp(c, lim, 1 - lim)
        self._last_centre = c
        self.pipes.append(Pipe(x, c))

    def _tick(self) -> None:
        now = time.monotonic()
        dt = min(now - self._last, 0.05)
        self._last = now
        playing = self.state == PLAYING
        speed = self._speed()
        drift = speed if playing else 40.0
        for st in self._stars:
            st[0] -= drift * st[3] * dt
            if st[0] < 0:
                st[0] += W

        a = self.angle()
        if a is not None:
            n = (a - self.lo) / (self.hi - self.lo)
            new = self.bird_n + (_clamp(n, -0.05, 1.05) - self.bird_n) * min(1.0, dt * 25)
            self.bird_v = (new - self.bird_n) / dt if dt > 0 else 0.0
            self.bird_n = new
            if self.state in (PLAYING, CALIB):
                self._used = [min(self._used[0], a), max(self._used[1], a)]

        if self.state == CALIB and now - self._calib_t0 >= CALIBRATE_S:
            lo, hi = self._used
            if hi - lo >= MIN_SPAN_DEG:
                self.set_range(lo, hi)
            self._set_state(READY)
        elif playing:
            self._step(dt, speed)
        if self.isVisible():
            self.update()

    def _step(self, dt: float, speed: float) -> None:
        problem = self.problem()
        if problem:
            return self._game_over(problem)
        for p in self.pipes:
            p.x -= speed * dt
        self.pipes = [p for p in self.pipes if p.x + PIPE_W > -20]
        spacing = self.level.spacing * speed / self.level.speed
        while self.pipes[-1].x < W + spacing:
            self._add_pipe(self.pipes[-1].x + spacing)

        by = self._y(self.bird_n)
        for p in self.pipes:
            if not p.scored and p.x + PIPE_W < BIRD_X - BIRD_R:
                p.scored = True
                self.score += 1
            if p.x < BIRD_X + HIT_R and p.x + PIPE_W > BIRD_X - HIT_R:
                top, bot = self._gap(p)
                if by - HIT_R < top or by + HIT_R > bot:
                    return self._game_over()
        if self.robot:
            self._robot_steer(speed)

    def _robot_steer(self, speed: float) -> None:
        """Send one POS move per pipe: start once the last pipe is cleared, arrive just before the next."""
        nxt = next((p for p in self.pipes if p.x + PIPE_W > BIRD_X - BIRD_R), None)
        if nxt is None or nxt.targeted:
            return
        nxt.targeted = True
        lo, hi = P.ROM[self.joint]
        target = _clamp(self.lo + nxt.centre * (self.hi - self.lo), lo + ROBOT_MARGIN_DEG, hi - ROBOT_MARGIN_DEG)
        t = _clamp((nxt.x - BIRD_X - BIRD_R - ROBOT_LEAD_PX) / speed, P.MIN_MOVE_TIME_S, P.MAX_MOVE_TIME_S)
        self.link.send(P.cmd_pos(target if self.joint == 0 else None, target if self.joint == 1 else None, t))

    # ================= Geometry =================

    @staticmethod
    def _y(n: float) -> float:
        return BOTTOM - n * (BOTTOM - TOP)

    def _gap(self, p: Pipe):
        half = self.level.gap * (BOTTOM - TOP) / 2
        cy = self._y(p.centre)
        return cy - half, cy + half

    # ================= Input =================

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Space and not e.isAutoRepeat():
            self.start()
        else:
            super().keyPressEvent(e)

    def mousePressEvent(self, e) -> None:
        self.setFocus()
        super().mousePressEvent(e)

    def hideEvent(self, e) -> None:
        self.halt()
        super().hideEvent(e)

    # ================= Drawing =================

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(theme.BG))
        s = min(self.width() / W, self.height() / H)
        p.translate((self.width() - W * s) / 2, (self.height() - H * s) / 2)
        p.scale(s, s)
        world = QRectF(0, 0, W, H)
        p.setClipRect(world)

        sky = QLinearGradient(0, 0, 0, H)
        sky.setColorAt(0, QColor("#04060C"))
        sky.setColorAt(1, QColor("#0C1424"))
        p.fillRect(world, sky)
        p.setPen(Qt.NoPen)
        for x, y, r, depth in self._stars:
            p.setBrush(QColor(255, 255, 255, int(50 + 200 * depth)))
            p.drawEllipse(QPointF(x, y), r, r)

        self._draw_pipes(p)
        p.fillRect(QRectF(0, BOTTOM + BIRD_R, W, H), QColor(theme.CARD))
        p.setPen(QPen(QColor(theme.BORDER_HI), 2))
        p.drawLine(QPointF(0, BOTTOM + BIRD_R), QPointF(W, BOTTOM + BIRD_R))
        self._draw_gauge(p)
        self._draw_bird(p)
        self._draw_hud(p)
        if self.state != PLAYING:
            self._draw_overlay(p)
        p.end()

    def _draw_pipes(self, p: QPainter) -> None:
        accent = QColor(theme.ACCENT)
        fill = QColor(accent)
        fill.setAlpha(55)
        p.setPen(QPen(accent, 3))
        p.setBrush(fill)
        for pipe in self.pipes:
            top, bot = self._gap(pipe)
            p.drawRoundedRect(QRectF(pipe.x, -20, PIPE_W, top + 20), 12, 12)
            p.drawRoundedRect(QRectF(pipe.x, bot, PIPE_W, H), 12, 12)
            p.drawRoundedRect(QRectF(pipe.x - 10, top - 30, PIPE_W + 20, 30), 8, 8)   # lips
            p.drawRoundedRect(QRectF(pipe.x - 10, bot, PIPE_W + 20, 30), 8, 8)

    def _draw_gauge(self, p: QPainter) -> None:
        x, w = 40.0, 14.0
        p.setPen(QPen(QColor(theme.BORDER_HI), 2))
        p.setBrush(QColor(theme.CARD))
        p.drawRoundedRect(QRectF(x, TOP, w, BOTTOM - TOP), 7, 7)
        y = self._y(_clamp(self.bird_n, 0, 1))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self._color()))
        p.drawRoundedRect(QRectF(x, y, w, BOTTOM - y), 7, 7)
        p.setPen(QColor(theme.TEXT_MUTED))
        p.setFont(_font(20))
        p.drawText(QRectF(x + w + 10, TOP - 14, 120, 28), Qt.AlignLeft | Qt.AlignVCenter, f"{self.hi:.0f}°")
        p.drawText(QRectF(x + w + 10, BOTTOM - 14, 120, 28), Qt.AlignLeft | Qt.AlignVCenter, f"{self.lo:.0f}°")

    def _color(self) -> str:
        return theme.ANKLE if self.joint == 0 else theme.TOE

    def _draw_bird(self, p: QPainter) -> None:
        y = self._y(self.bird_n)
        col = QColor(self._color())
        p.save()
        p.translate(BIRD_X, y)
        p.rotate(-_clamp(self.bird_v * 60, -35, 35))
        glow = QColor(col)
        glow.setAlpha(45)
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QPointF(0, 0), BIRD_R * 1.7, BIRD_R * 1.7)
        p.setBrush(col)
        p.drawEllipse(QPointF(0, 0), BIRD_R, BIRD_R)
        p.setBrush(col.darker(140))
        p.drawEllipse(QPointF(-8, 6), 14, 9)                               # wing
        beak = QPainterPath()
        beak.moveTo(BIRD_R - 4, -2)
        beak.lineTo(BIRD_R + 16, 5)
        beak.lineTo(BIRD_R - 4, 12)
        beak.closeSubpath()
        p.setBrush(QColor(theme.WARN))
        p.drawPath(beak)
        p.setBrush(QColor("white"))
        p.drawEllipse(QPointF(10, -8), 8, 8)
        p.setBrush(QColor("black"))
        p.drawEllipse(QPointF(12, -8), 4, 4)
        p.restore()

    def _draw_hud(self, p: QPainter) -> None:
        p.setPen(QColor(theme.TEXT))
        p.setFont(_font(84, True, "Bahnschrift"))
        if self.state == PLAYING:
            p.drawText(QRectF(0, 10, W, 110), Qt.AlignCenter, str(self.score))
        a = self.angle()
        p.setFont(_font(24, True))
        p.setPen(QColor(self._color()))
        text = f"{P.JOINTS[self.joint].upper()}  " + (f"{a:+.1f}°" if a is not None else "--")
        p.drawText(QRectF(110, 16, 400, 40), Qt.AlignLeft | Qt.AlignVCenter, text)
        p.setPen(QColor(theme.TEXT_MUTED))
        mode = "ROBOT" if self.robot else "HAND"
        p.drawText(QRectF(W - 520, 16, 490, 40), Qt.AlignRight | Qt.AlignVCenter, f"{mode}   ·   BEST {self.best}")

    def _draw_overlay(self, p: QPainter) -> None:
        p.fillRect(QRectF(0, 0, W, H), QColor(0, 0, 0, 150))
        box = QRectF(W / 2 - 440, H / 2 - 170, 880, 340)
        p.setPen(QPen(QColor(theme.BORDER_HI), 2))
        p.setBrush(QColor(theme.CARD))
        p.drawRoundedRect(box, 24, 24)

        name = P.JOINTS[self.joint].lower()
        problem = self.problem(robot=False if self.state == CALIB else None)
        lines: List[tuple] = []
        if self.state == CALIB:
            left = max(0.0, CALIBRATE_S - (time.monotonic() - self._calib_t0))
            title = f"CALIBRATING  {left:.0f}"
            lines.append((f"Move the {name} slowly through its full range.", theme.TEXT_MUTED))
            lines.append((f"Reached {self._used[0]:.0f}° … {self._used[1]:.0f}°", self._color()))
        elif self.state == OVER:
            title = "GAME OVER" if not self.reason else "ROUND ENDED"
            dur = self._t_end - self._t_start
            lines.append((f"Score {self.score}   ·   Best {self.best}   ·   {dur:.0f} s", theme.TEXT))
            lines.append((f"Range used {self._used[0]:.0f}–{self._used[1]:.0f}°   "
                          f"(target {self.lo:.0f}–{self.hi:.0f}°)", self._color()))
            lines.append((self.reason or problem or "Press Space to play again", theme.WARN if (self.reason or problem) else theme.TEXT_MUTED))
        else:
            title = "ANKLE FLYER" if self.joint == 0 else "TOE FLYER"
            how = ("The robot flies the bird with smooth position moves." if self.robot
                   else f"Move the {name} by hand: the bird follows the joint angle.")
            lines.append((how, theme.TEXT_MUTED))
            lines.append((f"Fly through the gaps · range {self.lo:.0f}–{self.hi:.0f}°", theme.TEXT_MUTED))
            lines.append((problem or "Press Space to start", theme.WARN if problem else theme.OK))

        p.setPen(QColor(theme.TEXT))
        p.setFont(_font(54, True, "Bahnschrift"))
        p.drawText(QRectF(box.x(), box.y() + 30, box.width(), 80), Qt.AlignCenter, title)
        p.setFont(_font(26))
        y = box.y() + 135
        for text, color in lines:
            p.setPen(QColor(color))
            p.drawText(QRectF(box.x() + 30, y, box.width() - 60, 50), Qt.AlignCenter, text)
            y += 54


class GamePanel(QWidget):
    """GAME tab: settings bar on top, the game below."""

    def __init__(self, model: Model, link: Link, live: Callable[[], bool], parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 14, 12, 14)
        lay.setSpacing(10)
        self.view = GameView(model, link, live)

        self.joint_box = QComboBox()
        self.joint_box.addItems(P.JOINTS)
        self.player_box = QComboBox()
        self.player_box.addItem("Hand  (motors limp)", False)
        self.player_box.addItem("Robot  (autopilot)", True)
        self.level_box = QComboBox()
        self.level_box.addItems(list(LEVELS))
        self.level_box.setCurrentText("Normal")
        self.calib_btn = QPushButton("Calibrate range")
        self.range_lbl = QLabel()
        self.range_lbl.setObjectName("Muted")
        self.start_btn = QPushButton("Start")
        self.start_btn.setObjectName("Primary")
        self.start_btn.setMinimumWidth(120)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        for label, box, width in (("Joint", self.joint_box, 90), ("Player", self.player_box, 170),
                                  ("Level", self.level_box, 90)):
            l = QLabel(label)
            l.setObjectName("Faint")
            box.setStyleSheet(f"min-width: {width}px;")
            bar.addWidget(l)
            bar.addWidget(box)
            bar.addSpacing(8)
        bar.addWidget(self.calib_btn)
        bar.addWidget(self.range_lbl)
        bar.addStretch()
        bar.addWidget(self.start_btn)
        for w in (self.joint_box, self.player_box, self.level_box, self.calib_btn, self.start_btn):
            w.setFocusPolicy(Qt.NoFocus)          # keep Space for the game
        lay.addLayout(bar)
        lay.addWidget(self.view, 1)
        hint = QLabel("Hand: Disable the motors, then move the joint. Robot: Enable, the GUI sends POS moves. "
                      "Space = start · Esc = STOP (also ends the round).")
        hint.setObjectName("Hint")
        lay.addWidget(hint)

        self.joint_box.currentIndexChanged.connect(self.view.set_joint)
        self.player_box.currentIndexChanged.connect(self._player_changed)
        self.level_box.currentTextChanged.connect(self.view.set_level)
        self.calib_btn.clicked.connect(self.view.calibrate)
        self.start_btn.clicked.connect(self._start_clicked)
        self.view.stateChanged.connect(self._on_state)
        self.view.rangeChanged.connect(lambda lo, hi: self.range_lbl.setText(f"{lo:.0f}–{hi:.0f}°"))
        self.view.set_range(*P.ROM[0])
        self._on_state(READY)

    def _player_changed(self) -> None:
        self.view.set_robot(self.player_box.currentData())
        self._on_state(self.view.state)

    def _start_clicked(self) -> None:
        if self.view.state in (PLAYING, CALIB):
            self.view.halt()
        else:
            self.view.start()

    def _on_state(self, st: str) -> None:
        busy = st in (PLAYING, CALIB)
        self.start_btn.setText("End round" if busy else "Start")
        self.calib_btn.setEnabled(not busy and not self.view.robot)
        for b in (self.joint_box, self.player_box, self.level_box):
            b.setEnabled(not busy)
        if not busy:
            self.view.setFocus()

    def halt(self) -> None:
        self.view.halt()
