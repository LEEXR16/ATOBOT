"""plots.py - rolling time plots (pyqtgraph) in the dark theme. TimePlot is from the Dynabo GUI,
plus optional fixed Y range and dashed reference lines (range of motion)."""
from __future__ import annotations

from typing import Dict, Optional, Sequence, Tuple

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from ui import theme
from ui.widgets import Card

pg.setConfigOptions(antialias=True, background=theme.PLOT_BG, foreground=theme.TEXT_MUTED)


def _style_plot(pw: pg.PlotWidget) -> None:
    pi = pw.getPlotItem()
    pi.showGrid(x=False, y=True, alpha=0.12)      # horizontal only: grid lines are costly to repaint
    for name in ("left", "bottom"):
        ax = pi.getAxis(name)
        ax.setPen(pg.mkPen(theme.PLOT_AXIS))
        ax.setTextPen(pg.mkPen(theme.TEXT_FAINT))
    pi.getViewBox().setBorder(None)
    pw.setMenuEnabled(False)
    pw.setMouseEnabled(x=False, y=False)
    pi.hideButtons()


class Series:
    def __init__(self, key: str, label: str, color: str, dashed: bool = False, width: float = 2.0):
        self.key, self.label, self.color, self.dashed, self.width = key, label, color, dashed, width


class TimePlot(Card):
    """Rolling time plot: x = seconds (0 = now). Legend chips in the header show the latest values.

    y_range: fixed Y range; otherwise it fits the data (never tighter than min_span).
    ref_lines: dashed horizontal lines, e.g. the range of motion."""

    def __init__(self, title: str, series: Sequence[Series], unit: str = "°",
                 window_s: float = 10.0, min_span: float = 4.0,
                 y_range: Optional[Tuple[float, float]] = None, ref_lines: Sequence[float] = (),
                 header_widget: Optional[QWidget] = None, parent=None):
        super().__init__(title, header_widget, parent)
        self.body.setSpacing(4)
        self._series = list(series)
        self._unit = unit
        self.window_s = window_s
        self._min_span = min_span
        self._fixed = y_range is not None

        legend = QHBoxLayout()
        legend.setSpacing(16)
        self._chips: Dict[str, QLabel] = {}
        for s in self._series:
            chip = QLabel()
            chip.setStyleSheet("background: transparent; font-size: 12px;")
            chip.setTextFormat(Qt.RichText)
            legend.addWidget(chip)
            self._chips[s.key] = chip
            self._set_chip(s, None)
        legend.addStretch()
        self.body.addLayout(legend)

        self.plot = pg.PlotWidget()
        _style_plot(self.plot)
        self.plot.setXRange(-window_s, 0, padding=0)
        self.plot.getPlotItem().getAxis("bottom").setLabel("s", color=theme.TEXT_FAINT)
        self.plot.setMinimumHeight(120)
        self._yrange = None
        if y_range is not None:
            self.plot.setYRange(*y_range, padding=0)
        for y in ref_lines:
            self.plot.addItem(pg.InfiniteLine(pos=y, angle=0, movable=False,
                                              pen=pg.mkPen(theme.ROM_LINE, width=1, style=Qt.DashLine)))
        self._curves = {}
        for s in self._series:
            pen = pg.mkPen(s.color, width=s.width, style=Qt.DashLine if s.dashed else Qt.SolidLine)
            self._curves[s.key] = self.plot.plot(pen=pen, connect="finite")
        self.body.addWidget(self.plot, 1)

    def set_window(self, window_s: float) -> None:
        self.window_s = window_s
        self.plot.setXRange(-window_s, 0, padding=0)

    def _set_chip(self, s: Series, v: Optional[float]) -> None:
        dash = "- - -" if s.dashed else "——"
        val = "--" if v is None or not np.isfinite(v) else f"{v:+.1f}{self._unit}"
        self._chips[s.key].setText(
            f'<span style="color:{s.color}; font-weight:700">{dash}</span>&nbsp; '
            f'<span style="color:{theme.TEXT_MUTED}">{s.label}</span>&nbsp; '
            f'<span style="font-family:Consolas; color:{theme.TEXT}">{val}</span>'
        )

    def set_data(self, t: np.ndarray, data: Dict[str, np.ndarray]) -> None:
        lo, hi = np.inf, -np.inf
        for s in self._series:
            y = data.get(s.key)
            if y is None or len(y) == 0:
                self._curves[s.key].setData([], [])
                self._set_chip(s, None)
                continue
            self._curves[s.key].setData(t, y)
            self._set_chip(s, float(y[-1]))
            finite = y[np.isfinite(y)]
            if finite.size:
                lo, hi = min(lo, finite.min()), max(hi, finite.max())
        if self._fixed:
            return
        # Y range: fit the data, never tighter than min_span (so noise doesn't look like motion).
        # It only changes when the data leaves it or shrinks a lot: redrawing the axis is expensive.
        if not np.isfinite(lo):
            lo, hi = -self._min_span / 2, self._min_span / 2
        mid, span = (lo + hi) / 2, max(hi - lo, self._min_span)
        want = (mid - span * 0.6, mid + span * 0.6)
        cur = self._yrange
        if cur is None or lo < cur[0] or hi > cur[1] or span < 0.4 * (cur[1] - cur[0]):
            self._yrange = want
            self.plot.setYRange(*want, padding=0)
