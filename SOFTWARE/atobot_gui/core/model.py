"""model.py - latest sample, rolling history for the plots, link statistics and CSV recording."""
from __future__ import annotations

import time
from collections import deque
from typing import Dict, Optional, Tuple

import numpy as np

from core import protocol as P
from core.recorder import CsvRecorder

HISTORY_S = 30
RATE_HZ = 100
STREAM_TIMEOUT_S = 0.5
KEYS = ("cmd0", "pos0", "cmd1", "pos1", "tq0", "tq1")


class Model:
    def __init__(self):
        self.recorder: Optional[CsvRecorder] = None
        self.reset()

    def reset(self) -> None:
        n = HISTORY_S * RATE_HZ
        self._t = deque(maxlen=n)
        self._data = {k: deque(maxlen=n) for k in KEYS}
        self.latest: Optional[P.Sample] = None
        self.last_rx = 0.0
        self.received = 0
        self.lost = 0
        self._rate_times = deque(maxlen=400)

    def add(self, s: P.Sample) -> None:
        now = time.monotonic()
        prev = self.latest
        if prev is not None:
            gap = s.device_ms - prev.device_ms
            if gap < 0:                                  # Teensy reset
                self.reset()
            elif gap > 15:
                self.lost += round(gap / 10) - 1
        self.latest = s
        self.last_rx = now
        self.received += 1
        self._rate_times.append(now)
        self._t.append(s.device_ms / 1000.0)
        a, t = s.joints
        for k, v in zip(KEYS, (a.cmd, a.pos, t.cmd, t.pos, a.torque, t.torque)):
            self._data[k].append(v)
        if self.recorder is not None:
            self.recorder.write(P.csv_row(time.time(), s))

    # ---- status ----
    @property
    def stream_age(self) -> float:
        return time.monotonic() - self.last_rx if self.last_rx else float("inf")

    @property
    def stream_ok(self) -> bool:
        return self.stream_age < STREAM_TIMEOUT_S

    @property
    def rate(self) -> float:
        now = time.monotonic()
        return sum(1 for t in self._rate_times if now - t <= 1.0)

    @property
    def loss_percent(self) -> float:
        total = self.received + self.lost
        return 100.0 * self.lost / total if total else 0.0

    def history(self, window_s: float) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
        """x = seconds relative to the newest sample (0 = now)."""
        if not self._t:
            return np.empty(0), {}
        t = np.fromiter(self._t, float)
        keep = t >= t[-1] - window_s
        t = t[keep] - t[-1]
        return t, {k: np.fromiter(v, float)[keep] for k, v in self._data.items()}

    # ---- recording ----
    def start_recording(self) -> CsvRecorder:
        self.stop_recording()
        self.recorder = CsvRecorder("ATOBOT", P.CSV_HEADER)
        return self.recorder

    def stop_recording(self) -> None:
        if self.recorder is not None:
            self.recorder.close()
            self.recorder = None
