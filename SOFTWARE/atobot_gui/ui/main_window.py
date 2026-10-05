"""main_window.py - ATOBOT GUI: live values (left), plots (centre), controls and STOP (right)."""
from __future__ import annotations

import os
from typing import List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core import protocol as P
from core.link import Link, LinkState, list_ports
from core.model import Model
from core.recorder import recordings_folder
from ui import theme
from ui.plots import Series, TimePlot
from ui.widgets import Card, SliderRow, StatusPill, ValueRow, hline

PLOT_HZ = 20
VALUES_EVERY = 2                 # value labels at 10 Hz
LEFT_W, RIGHT_W = 290, 330
LOG_LINES = 300


def _side_panel(width: int):
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFixedWidth(width)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    inner = QWidget()
    lay = QVBoxLayout(inner)
    lay.setContentsMargins(14, 14, 14, 14)
    lay.setSpacing(12)
    scroll.setWidget(inner)
    return scroll, lay


def _row(*widgets) -> QHBoxLayout:
    r = QHBoxLayout()
    r.setSpacing(8)
    for w in widgets:
        r.addWidget(w, 1)
    return r


def _hint(text: str = "") -> QLabel:
    h = QLabel(text)
    h.setObjectName("Hint")
    h.setWordWrap(True)
    return h


class JointCard(Card):
    """Live values of one joint, with a READY / WAIT / LOST pill in the header."""

    def __init__(self, j: int, color: str):
        self.pill = StatusPill("--", "idle")
        super().__init__(P.JOINTS[j], self.pill)
        self.j = j
        self.angle = self.add(ValueRow("Angle", "°", color))
        self.target = self.add(ValueRow("Target", "°"))
        self.speed = self.add(ValueRow("Speed", "°/s"))
        self.current = self.add(ValueRow("Current", "A"))
        self.torque = self.add(ValueRow("Torque", "Nm"))
        self.temp = self.add(ValueRow("Temperature", "°C"))
        self.voltage = self.add(ValueRow("Voltage", "V"))
        self.error = self.add(ValueRow("Motor error"))
        self.zero = self.add(ValueRow("Zero"))
        self.gains = self.add(ValueRow("Kp / Kd"))

    def show(self, d: Optional[P.JointData], vbus: float) -> None:
        if d is None:
            for r in (self.angle, self.target, self.speed, self.current, self.torque, self.temp, self.voltage):
                r.set(None)
            self.pill.set("--", "idle")
            return
        self.pill.set(P.STATE_NAMES.get(d.state, "?"),
                      {P.STATE_READY: "ok", P.STATE_WAIT: "warn"}.get(d.state, "error"))
        self.angle.set(d.pos, "{:+.1f}")
        self.target.set(d.cmd, "{:+.1f}")
        self.speed.set(d.vel, "{:+.1f}")
        self.current.set(d.cur, "{:+.2f}")
        self.torque.set(d.torque, "{:+.2f}")
        self.temp.set(d.temp, "{:d}", color=theme.WARN if d.temp >= 70 else None)
        self.voltage.set(vbus, "{:.1f}")
        self.error.value.setText(P.MOTOR_ERRORS.get(d.err, f"code {d.err}"))
        self.error.value.setStyleSheet(f"color: {theme.ERR};" if d.err else "")
        self.zero.value.setText("set" if d.zeroed else "NOT set")
        self.zero.value.setStyleSheet("" if d.zeroed else f"color: {theme.WARN};")
        self.gains.value.setText(f"{d.kp:.1f} / {d.kd:.2f}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ATOBOT")
        self.resize(1440, 900)
        self.link = Link(self)
        self.model = Model()
        self._tick = 0
        self._gains_loaded = False

        page = QWidget()
        page.setObjectName("Page")
        self.setCentralWidget(page)
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())
        root.addWidget(hline())
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_values())
        body.addWidget(self._build_plots(), 1)
        body.addWidget(self._build_controls())
        root.addLayout(body, 1)

        self.link.lineReceived.connect(self._on_line)
        self.link.stateChanged.connect(self._on_link_state)
        self.link.errorText.connect(lambda t: self._log(t, theme.ERR))
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self.emergency_stop)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(int(1000 / PLOT_HZ))
        self._on_link_state(self.link.state)

    # ================= Layout =================

    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setObjectName("SidePanel")
        w.setAutoFillBackground(True)
        lay = QHBoxLayout(w)
        lay.setContentsMargins(4, 12, 22, 12)
        lay.setSpacing(12)
        brand = QLabel("ATOBOT")
        brand.setObjectName("Brand")
        lay.addWidget(brand)
        self.subtitle = QLabel("Ankle & Toe rehab")
        self.subtitle.setObjectName("Muted")
        lay.addWidget(self.subtitle)
        lay.addSpacing(12)
        self.stream_pill = StatusPill("No data", "idle")
        self.mode_pill = StatusPill("Mode --", "idle")
        self.fault_pill = StatusPill("", "error")
        self.fault_pill.hide()
        for p in (self.stream_pill, self.mode_pill, self.fault_pill):
            lay.addWidget(p, 0, Qt.AlignVCenter)
        lay.addStretch()

        self.port_box = QComboBox()
        self.refresh_btn = QPushButton("⟳")
        self.refresh_btn.setObjectName("Ghost")
        self.refresh_btn.setToolTip("Refresh the port list")
        self.refresh_btn.clicked.connect(self._refresh_ports)
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setObjectName("Primary")
        self.connect_btn.setMinimumWidth(120)
        self.connect_btn.clicked.connect(self._on_connect_clicked)
        lay.addWidget(self.port_box)
        lay.addWidget(self.refresh_btn)
        lay.addWidget(self.connect_btn)
        self._refresh_ports()
        return w

    def _build_values(self) -> QWidget:
        scroll, lay = _side_panel(LEFT_W)
        self.joint_cards = [JointCard(0, theme.ANKLE), JointCard(1, theme.TOE)]
        for c in self.joint_cards:
            lay.addWidget(c)

        link = Card("Link")
        self._rate = link.add(ValueRow("Packets / s"))
        self._rx = link.add(ValueRow("Received"))
        self._lost = link.add(ValueRow("Lost"))
        self._runtime = link.add(ValueRow("Device time", "s"))
        lay.addWidget(link)
        self._link_card = link

        log = Card("Messages")
        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setMaximumBlockCount(LOG_LINES)
        self._log_view.setMinimumHeight(180)
        log.add(self._log_view)
        lay.addWidget(log)
        lay.addStretch()
        return scroll

    def _build_plots(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 14, 12, 14)
        lay.setSpacing(12)
        self.window_box = QComboBox()
        for s in (5, 10, 30):
            self.window_box.addItem(f"{s} s", s)
        self.window_box.setCurrentIndex(1)
        self.window_box.setStyleSheet("min-width: 60px; padding: 2px 8px;")
        self.window_box.currentIndexChanged.connect(
            lambda: [p.set_window(self.window_box.currentData()) for p in self._plots])

        self._plots: List[TimePlot] = []
        for j, color in ((0, theme.ANKLE), (1, theme.TOE)):
            lo, hi = P.ROM[j]
            p = TimePlot(f"{P.JOINTS[j]} angle", [
                Series(f"cmd{j}", "Target", theme.CMD, dashed=True),
                Series(f"pos{j}", "Actual", color),
            ], y_range=(lo - 8, hi + 8), ref_lines=(lo, hi),
                header_widget=self.window_box if j == 0 else None)
            lay.addWidget(p, 3)
            self._plots.append(p)
        tq = TimePlot("Torque", [Series("tq0", "Ankle", theme.ANKLE), Series("tq1", "Toe", theme.TOE)],
                      unit=" Nm", min_span=2.0)
        lay.addWidget(tq, 2)
        self._plots.append(tq)
        return w

    def _build_controls(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("SidePanel")
        panel.setFixedWidth(RIGHT_W)
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll, lay = _side_panel(RIGHT_W)
        outer.addWidget(scroll, 1)

        # ---- Motors ----
        motors = Card("Motors")
        self.enable_btn = QPushButton("Enable")
        self.enable_btn.setObjectName("Primary")
        self.enable_btn.clicked.connect(lambda: self.link.send("EN"))
        self.disable_btn = QPushButton("Disable")
        self.disable_btn.clicked.connect(lambda: self.link.send("DIS"))
        motors.body.addLayout(_row(self.enable_btn, self.disable_btn))
        self.zero_btns = []
        for j in range(2):
            b = QPushButton(f"Zero {P.JOINTS[j].lower()}")
            b.clicked.connect(lambda _=False, j=j: self.link.send(P.cmd_zero(j)))
            self.zero_btns.append(b)
        motors.body.addLayout(_row(*self.zero_btns))
        self.clear_btn = QPushButton("Clear faults")
        motors.add(self.clear_btn)
        self.clear_btn.clicked.connect(lambda: self.link.send("CLR"))
        motors.add(_hint("Enable holds where the joint is. Disable = limp. "
                         "Zero: disable, put the joint at 0°, then press Zero."))
        lay.addWidget(motors)

        # ---- Position ----
        pos = Card("Position")
        self.pos_sliders = []
        for j in range(2):
            lo, hi = P.ROM[j]
            self.pos_sliders.append(pos.add(SliderRow(P.JOINTS[j], lo, hi, lo, 1, "°")))
        self.time_slider = pos.add(SliderRow("Time", P.MIN_MOVE_TIME_S, P.MAX_MOVE_TIME_S, 2.0, 1, " s"))
        self.move_btn = QPushButton("Move")
        self.move_btn.setObjectName("Primary")
        self.move_btn.clicked.connect(self._move)
        self.home_btn = QPushButton("Go to 0, 0")
        self.home_btn.clicked.connect(lambda: self._move(home=True))
        pos.body.addLayout(_row(self.move_btn, self.home_btn))
        pos.add(_hint(f"Smooth move; the firmware lengthens the time if it would exceed {P.MAX_SPEED:.0f}°/s."))
        lay.addWidget(pos)

        # ---- Sine ----
        sine = Card("Sine")
        self.sine_on, self.sine_center, self.sine_amp = [], [], []
        defaults = ((40.0, 20.0), (30.0, 10.0))
        for j in range(2):
            lo, hi = P.ROM[j]
            cb = QCheckBox(P.JOINTS[j])
            cb.setChecked(j == 0)
            sine.add(cb)
            self.sine_on.append(cb)
            self.sine_center.append(sine.add(SliderRow("Centre", lo, hi, defaults[j][0], 1, "°")))
            self.sine_amp.append(sine.add(SliderRow("Amplitude", 0.0, (hi - lo) / 2, defaults[j][1], 1, "°")))
            if j == 0:
                sine.add(hline())
        self.freq_slider = sine.add(SliderRow("Frequency", 0.05, P.SINE_MAX_HZ, 0.25, 2, " Hz"))
        self.sine_problem = _hint()
        sine.add(self.sine_problem)
        self.sine_btn = QPushButton("Start sine")
        self.sine_btn.setObjectName("Primary")
        self.sine_btn.clicked.connect(self._start_sine)
        sine.add(self.sine_btn)
        sine.add(_hint("Goes to the centre first, then the amplitude ramps in over 2 s. STOP holds."))
        lay.addWidget(sine)

        # ---- Gains ----
        gains = Card("Gains")
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        for c, text in enumerate(("", "Kp  Nm/rad", "Kd  Nm·s/rad")):
            h = QLabel(text)
            h.setObjectName("Faint")
            grid.addWidget(h, 0, c)
        self.kp_spin, self.kd_spin = [], []
        for j in range(2):
            n = QLabel(P.JOINTS[j])
            n.setObjectName("Muted")
            grid.addWidget(n, j + 1, 0)
            kp = QDoubleSpinBox()
            kp.setRange(0, P.KP_LIMIT)
            kp.setDecimals(1)
            kp.setValue(P.DEFAULT_KP[j])
            kd = QDoubleSpinBox()
            kd.setRange(0, P.KD_LIMIT)
            kd.setDecimals(2)
            kd.setSingleStep(0.05)
            kd.setValue(P.DEFAULT_KD[j])
            grid.addWidget(kp, j + 1, 1)
            grid.addWidget(kd, j + 1, 2)
            self.kp_spin.append(kp)
            self.kd_spin.append(kd)
        gains.body.addLayout(grid)
        self.gain_btn = QPushButton("Apply gains")
        self.gain_btn.clicked.connect(self._apply_gains)
        gains.add(self.gain_btn)
        gains.add(_hint("Tuning: raise Kp until it tracks, then add Kd until the overshoot goes."))
        lay.addWidget(gains)

        # ---- Recording ----
        rec = Card("Recording")
        self.rec_btn = QPushButton("●  Record")
        self.rec_btn.setObjectName("Record")
        self.rec_btn.setCheckable(True)
        self.rec_btn.toggled.connect(self._on_record)
        rec.add(self.rec_btn)
        self.rec_info = _hint("Saves every data line (100 /s) to a CSV file.")
        rec.add(self.rec_info)
        folder = QPushButton("Open recordings folder")
        folder.setObjectName("Small")
        folder.clicked.connect(lambda: os.startfile(recordings_folder()))
        rec.add(folder)
        lay.addWidget(rec)
        lay.addStretch()

        # ---- STOP, always visible ----
        stop_box = QWidget()
        sl = QVBoxLayout(stop_box)
        sl.setContentsMargins(14, 10, 14, 14)
        sl.setSpacing(4)
        self.stop_btn = QPushButton("STOP")
        self.stop_btn.setObjectName("Stop")
        self.stop_btn.clicked.connect(self.emergency_stop)
        sl.addWidget(self.stop_btn)
        k = _hint("Esc = STOP. Motion stops, motors hold where they are.")
        k.setAlignment(Qt.AlignCenter)
        sl.addWidget(k)
        outer.addWidget(hline())
        outer.addWidget(stop_box)
        return panel

    # ================= Actions =================

    def _refresh_ports(self) -> None:
        current = self.port_box.currentData()
        self.port_box.clear()
        for name, desc in list_ports():
            self.port_box.addItem(desc, name)
        i = self.port_box.findData(current)
        self.port_box.setCurrentIndex(max(i, 0))

    def _on_connect_clicked(self) -> None:
        if self.link.is_connected:
            self.link.close()
        else:
            self.link.open(self.port_box.currentData())

    def _usable(self) -> List[bool]:
        s = self.model.latest
        return [s is not None and s.joints[j].usable for j in range(2)]

    def _move(self, home: bool = False) -> None:
        use = self._usable()
        t = [(0.0 if home else self.pos_sliders[j].value()) if use[j] else None for j in range(2)]
        self.link.send(P.cmd_pos(t[0], t[1], self.time_slider.value()))

    def _sine_args(self):
        use = self._usable()
        c, a = [None, None], [0.0, 0.0]
        for j in range(2):
            if self.sine_on[j].isChecked() and use[j]:
                c[j], a[j] = self.sine_center[j].value(), self.sine_amp[j].value()
        return c, a

    def _start_sine(self) -> None:
        c, a = self._sine_args()
        self.link.send(P.cmd_sine(c[0], a[0], c[1], a[1], self.freq_slider.value()))

    def _apply_gains(self) -> None:
        for j in range(2):
            self.link.send(P.cmd_gain(j, self.kp_spin[j].value(), self.kd_spin[j].value()))

    def emergency_stop(self) -> None:
        if self.link.is_connected:
            self.link.send("STOP")

    def _on_record(self, on: bool) -> None:
        if on:
            r = self.model.start_recording()
            self.rec_btn.setText("■  Stop recording")
            self.rec_info.setText(r.path.name)
        else:
            path = self.model.recorder.path if self.model.recorder else None
            self.model.stop_recording()
            self.rec_btn.setText("●  Record")
            if path:
                self.rec_info.setText(f"Saved {path.name}")

    # ================= Incoming =================

    def _on_line(self, line: str) -> None:
        kind = line[:2]
        if kind == "D,":
            s = P.parse_d(line)
            if s is not None:
                self.model.add(s)
                if not self._gains_loaded:             # show the firmware's gains once per connection
                    self._gains_loaded = True
                    for j in range(2):
                        self.kp_spin[j].setValue(s.joints[j].kp)
                        self.kd_spin[j].setValue(s.joints[j].kd)
            return
        if kind == "V,":
            parts = line.split(",")
            self.subtitle.setText(f"Ankle & Toe rehab · {parts[1]} {parts[2] if len(parts) > 2 else ''}")
            return
        if kind == "E,":
            self._log(line[2:], theme.ERR)
        elif kind == "OK":
            self._log(line, theme.TEXT_FAINT)
        elif kind == "I,":
            self._log(line[2:])
        else:
            self._log(line, theme.TEXT_FAINT)

    def _log(self, text: str, color: Optional[str] = None) -> None:
        text = text.replace("&", "&amp;").replace("<", "&lt;")
        self._log_view.appendHtml(f'<span style="color:{color}">{text}</span>' if color else text)

    def _on_link_state(self, state: LinkState) -> None:
        connected = state == LinkState.CONNECTED
        if connected:
            self.model.reset()
            self._gains_loaded = False
            self._log(f"Connected to {self.link.port_name}", theme.OK)
        elif self.rec_btn.isChecked():
            self.rec_btn.setChecked(False)
        if state == LinkState.DISCONNECTED:
            self.subtitle.setText("Ankle & Toe rehab")
        self.connect_btn.setText("Disconnect" if connected else "Connect")
        self.connect_btn.setObjectName("Ghost" if connected else "Primary")
        self.connect_btn.style().unpolish(self.connect_btn)
        self.connect_btn.style().polish(self.connect_btn)
        self.port_box.setEnabled(not connected)
        self.refresh_btn.setEnabled(not connected)
        self._update_controls()

    # ================= Refresh =================

    def _refresh(self) -> None:
        self._tick += 1
        t, data = self.model.history(self._plots[0].window_s)
        for p in self._plots:
            p.set_data(t, data)
        if self._tick % VALUES_EVERY == 0:
            self._update_values()
            self._update_status()
            self._update_controls()

    def _live(self) -> bool:
        return self.link.is_connected and self.model.stream_ok and self.model.latest is not None

    def _update_values(self) -> None:
        s = self.model.latest
        live = self._live()
        for j, card in enumerate(self.joint_cards):
            card.show(s.joints[j] if s else None, s.vbus if s else 0.0)
            card.set_online(live and s.joints[j].ready)
        m = self.model
        self._link_card.set_online(live)
        self._rate.set(m.rate, "{:.0f}")
        self._rx.set(m.received, "{:d}")
        self._lost.set(m.lost, "{:d}", color=theme.WARN if m.lost else None)
        self._runtime.set(s.device_ms / 1000.0 if s else None, "{:.1f}")
        r = m.recorder
        if r is not None:
            e = int(r.elapsed)
            self.rec_info.setText(f"{e // 60:02d}:{e % 60:02d} · {r.rows} rows · {r.path.name}")

    def _update_status(self) -> None:
        m, s = self.model, self.model.latest
        if not self.link.is_connected:
            self.stream_pill.set("No data", "idle")
        elif s is None:
            self.stream_pill.set("Waiting for data…", "warn")
        elif not m.stream_ok:
            self.stream_pill.set(f"Stream stalled {m.stream_age:.0f} s", "error")
        else:
            self.stream_pill.set(f"{m.rate:.0f} pk/s · {m.loss_percent:.1f} % lost",
                                 "ok" if m.loss_percent < 1 else "warn")
        if s is None or not self.link.is_connected:
            self.mode_pill.set("Mode --", "idle")
            self.fault_pill.hide()
            return
        self.mode_pill.set(P.MODE_NAMES.get(s.mode, f"Mode {s.mode}"),
                           "idle" if s.mode == P.MODE_IDLE else "info")
        faults = P.fault_texts(s.faults)
        self.fault_pill.setVisible(bool(faults))
        if faults:
            self.fault_pill.set(" · ".join(faults), "error")

    def _update_controls(self) -> None:
        s = self.model.latest
        live = self._live()
        idle = live and s.mode == P.MODE_IDLE
        active = live and s.mode != P.MODE_IDLE
        ok = live and s.faults == 0
        use = self._usable()

        self.enable_btn.setEnabled(idle and ok)
        self.disable_btn.setEnabled(active)
        for j, b in enumerate(self.zero_btns):
            b.setEnabled(idle and s.joints[j].ready)
        self.clear_btn.setEnabled(idle and s.faults != 0)

        can_move = active and ok and any(use)
        for j in range(2):
            self.pos_sliders[j].setEnabled(can_move and use[j])
            for w in (self.sine_on[j], self.sine_center[j], self.sine_amp[j]):
                w.setEnabled(can_move and use[j])
        self.time_slider.setEnabled(can_move)
        self.move_btn.setEnabled(can_move)
        self.home_btn.setEnabled(can_move)
        self.freq_slider.setEnabled(can_move)

        problem = None
        c, a = self._sine_args()
        if live and c == [None, None]:
            problem = "Tick a zeroed joint."
        for j in range(2):
            if c[j] is not None and problem is None:
                problem = P.sine_problem(j, c[j], a[j], self.freq_slider.value())
        self.sine_problem.setText(problem or "")
        self.sine_problem.setStyleSheet(f"color: {theme.WARN};" if problem else "")
        self.sine_btn.setEnabled(can_move and problem is None)

        self.gain_btn.setEnabled(live)
        self.stop_btn.setEnabled(self.link.is_connected)
        self.rec_btn.setEnabled(self.link.is_connected or self.rec_btn.isChecked())

    def closeEvent(self, e) -> None:
        self._timer.stop()
        self.model.stop_recording()
        self.link.close()
        super().closeEvent(e)
