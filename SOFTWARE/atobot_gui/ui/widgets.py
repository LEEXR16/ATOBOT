"""widgets.py - small building blocks (from the Dynabo GUI): cards, status pills, slider rows, value rows."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ui import theme


class Card(QFrame):
    """Rounded panel with an optional small uppercase title and a right-aligned header widget.

    set_online(): a green dot before the title while the component sends data; without data the
    dot goes and the whole card fades."""

    FADED_OPACITY = 0.32

    def __init__(self, title: str = "", header_widget: Optional[QWidget] = None, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(14, 12, 14, 14)
        self.body.setSpacing(10)
        self._online: Optional[bool] = None
        self._fade: Optional[QGraphicsOpacityEffect] = None
        self._dot = QLabel("\u25cf")
        self._dot.setStyleSheet(f"color: {theme.OK}; font-size: 10px; background: transparent;")
        self._dot.setToolTip("Online: data is arriving")
        self._dot.hide()
        if title or header_widget:
            row = QHBoxLayout()
            row.setSpacing(6)
            row.addWidget(self._dot)
            if title:
                t = QLabel(title.upper())
                t.setObjectName("CardTitle")
                row.addWidget(t)
            row.addStretch()
            if header_widget is not None:
                row.addWidget(header_widget)
            self.body.addLayout(row)

    def add(self, w: QWidget, stretch: int = 0) -> QWidget:
        self.body.addWidget(w, stretch)
        return w

    def set_online(self, online: bool) -> None:
        if online == self._online:
            return
        self._online = online
        self._dot.setVisible(online)
        if self._fade is None:
            self._fade = QGraphicsOpacityEffect(self)
            self._fade.setOpacity(self.FADED_OPACITY)
            self.setGraphicsEffect(self._fade)
        self._fade.setEnabled(not online)


class StatusPill(QLabel):
    """Rounded label with a coloured dot: connection, mode, errors..."""

    def __init__(self, text: str = "", level: str = "idle", parent=None):
        super().__init__(parent)
        self._text = self._level = None
        self.setFixedHeight(26)
        self.set(text, level)

    def set(self, text: str, level: str = "idle") -> None:
        # Restyling is expensive, so only touch the widget when something changed
        if text == self._text and level == self._level:
            return
        c = theme.LEVEL_COLORS.get(level, theme.IDLE)
        self.setText(f'<span style="color:{c}">●</span>&nbsp;&nbsp;{text}')
        if level != self._level:
            self.setStyleSheet(
                f"QLabel {{ background: {theme.rgba(c, 0.10)}; border: 1px solid {theme.rgba(c, 0.35)};"
                f" border-radius: 12px; padding: 3px 10px; font-size: 12px; color: {theme.TEXT}; }}"
            )
        self._text, self._level = text, level


class SliderRow(QWidget):
    """Label + editable value on one line, slider underneath, optional hint (e.g. board degrees)."""

    valueChanged = Signal(float)

    def __init__(self, label: str, minimum: float, maximum: float, value: float,
                 decimals: int = 1, suffix: str = "", step: Optional[float] = None, parent=None):
        super().__init__(parent)
        self._scale = 10 ** decimals
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        row = QHBoxLayout()
        name = QLabel(label)
        name.setObjectName("Muted")
        row.addWidget(name)
        row.addStretch()
        self.hint = QLabel("")
        self.hint.setObjectName("Hint")
        row.addWidget(self.hint)
        self.spin = QDoubleSpinBox()
        self.spin.setRange(minimum, maximum)
        self.spin.setDecimals(decimals)
        self.spin.setSingleStep(step if step is not None else 1 / self._scale)
        self.spin.setSuffix(suffix)
        self.spin.setAlignment(Qt.AlignRight)
        self.spin.setFixedWidth(92)
        self.spin.setKeyboardTracking(False)
        row.addWidget(self.spin)
        lay.addLayout(row)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(round(minimum * self._scale), round(maximum * self._scale))
        lay.addWidget(self.slider)

        self.slider.valueChanged.connect(lambda i: self._set(i / self._scale, from_slider=True))
        self.spin.valueChanged.connect(lambda v: self._set(v, from_slider=False))
        self._set(value, from_slider=False)

    def _set(self, v: float, from_slider: bool) -> None:
        self.spin.blockSignals(True)
        self.slider.blockSignals(True)
        if from_slider:
            self.spin.setValue(v)
        else:
            self.spin.setValue(v)             # clamps to the range
            self.slider.setValue(round(self.spin.value() * self._scale))
        self.spin.blockSignals(False)
        self.slider.blockSignals(False)
        self.valueChanged.emit(self.value())

    def value(self) -> float:
        return self.spin.value()

    def set_value(self, v: float) -> None:
        self._set(v, from_slider=False)


class ValueRow(QWidget):
    """'Label ............ value unit' in a monospace value column."""

    def __init__(self, label: str, unit: str = "", color: Optional[str] = None, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        if color:
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {color}; font-size: 9px; background: transparent;")
            lay.addWidget(dot)
        name = QLabel(label)
        name.setObjectName("Muted")
        lay.addWidget(name)
        lay.addStretch()
        self.value = QLabel("--")
        self.value.setObjectName("Value")
        self._color: Optional[str] = None
        self.value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(self.value)
        if unit:
            u = QLabel(unit)
            u.setObjectName("Faint")
            u.setFixedWidth(22)
            lay.addWidget(u)

    def set(self, v: Optional[float], fmt: str = "{:+.2f}", color: Optional[str] = None) -> None:
        text = "--" if v is None else fmt.format(v)
        if text != self.value.text():
            self.value.setText(text)
        if color != self._color:                 # restyling is expensive: only on change
            self._color = color
            self.value.setStyleSheet(f"color: {color};" if color else "")


def dot_icon(color: str, size: int = 10) -> QIcon:
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(QRectF(2, 2, size * 2 - 4, size * 2 - 4))
    p.end()
    return QIcon(pm)


def hline() -> QFrame:
    f = QFrame()
    f.setFixedHeight(1)
    f.setStyleSheet(f"background: {theme.BORDER}; border: none;")
    return f


def expanding(w: QWidget) -> QWidget:
    w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    return w


ICON_SIZE = QSize(10, 10)
