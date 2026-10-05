"""recorder.py - CSV recording to Documents/ATOBOT/ (same as the Dynabo GUI's recorder)."""
from __future__ import annotations

import csv
import datetime as _dt
import time
from pathlib import Path
from typing import Sequence


def recordings_folder() -> Path:
    folder = Path.home() / "Documents" / "ATOBOT"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


class CsvRecorder:
    FLUSH_S = 1.0          # flush to disk every second, so a crash loses at most 1 s

    def __init__(self, name: str, header: Sequence[str]):
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = recordings_folder() / f"{name}_{ts}.csv"
        self._file = open(self.path, "w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        self._writer.writerow(header)
        self.rows = 0
        self._t0 = time.monotonic()
        self._last_flush = self._t0

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self._t0

    def write(self, row: Sequence) -> None:
        self._writer.writerow(row)
        self.rows += 1
        now = time.monotonic()
        if now - self._last_flush >= self.FLUSH_S:
            self._file.flush()
            self._last_flush = now

    def close(self) -> None:
        self._file.flush()
        self._file.close()
