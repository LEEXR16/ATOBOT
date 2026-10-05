"""link.py - USB serial link to the Teensy (QtSerialPort), or the built-in simulator.

Lines in -> lineReceived. While connected it sends PING every 200 ms (keeps the firmware's
PC watchdog happy) and turns the 100 Hz D stream on.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional, Tuple

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtSerialPort import QSerialPort, QSerialPortInfo

from core.simulator import Simulator

SIM_PORT = "Simulator"
TEENSY_VID = 0x16C0
PING_MS = 200


class LinkState(Enum):
    DISCONNECTED = 0
    CONNECTED = 1
    ERROR = 2


def list_ports() -> List[Tuple[str, str]]:
    """(port name, description), Teensy ports first, simulator last."""
    ports = []
    for p in QSerialPortInfo.availablePorts():
        teensy = p.hasVendorIdentifier() and p.vendorIdentifier() == TEENSY_VID
        desc = "Teensy" if teensy else (p.description() or "serial port")
        ports.append((not teensy, p.portName(), f"{p.portName()} · {desc}"))
    ports.sort()
    return [(name, desc) for _, name, desc in ports] + [(SIM_PORT, "Simulator (no hardware)")]


class Link(QObject):
    stateChanged = Signal(object)        # LinkState
    lineReceived = Signal(str)
    errorText = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = LinkState.DISCONNECTED
        self.port_name = ""
        self._serial: Optional[QSerialPort] = None
        self._sim: Optional[Simulator] = None
        self._buf = b""
        self._ping = QTimer(self)
        self._ping.timeout.connect(lambda: self.send("PING"))

    @property
    def is_connected(self) -> bool:
        return self.state == LinkState.CONNECTED

    def open(self, port: str) -> None:
        self.close()
        if port == SIM_PORT:
            self._sim = Simulator(self)
            self._sim.lineOut.connect(self.lineReceived)
        else:
            s = QSerialPort(self)
            s.setPortName(port)
            s.setBaudRate(115200)                 # ignored by Teensy USB serial
            if not s.open(QSerialPort.ReadWrite):
                self.errorText.emit(f"Cannot open {port}: {s.errorString()}")
                self._set_state(LinkState.ERROR)
                return
            s.setDataTerminalReady(True)
            s.readyRead.connect(self._on_ready_read)
            s.errorOccurred.connect(self._on_serial_error)
            self._serial = s
        self.port_name = port
        self._buf = b""
        self._set_state(LinkState.CONNECTED)
        self.send("STREAM,1")
        self.send("VER")
        self._ping.start(PING_MS)

    def close(self) -> None:
        self._ping.stop()
        if self.is_connected:
            self.send("STOP")                     # stop any motion; motors keep holding
            self.send("STREAM,0")
        if self._serial is not None:
            self._serial.flush()
            self._serial.close()
            self._serial.deleteLater()
            self._serial = None
        if self._sim is not None:
            self._sim.stop()
            self._sim.deleteLater()
            self._sim = None
        if self.state != LinkState.DISCONNECTED:
            self._set_state(LinkState.DISCONNECTED)

    def send(self, line: str) -> None:
        if self._sim is not None:
            self._sim.handle_line(line)
        elif self._serial is not None:
            self._serial.write((line + "\n").encode("ascii"))

    # ---- internals ----
    def _set_state(self, state: LinkState) -> None:
        self.state = state
        self.stateChanged.emit(state)

    def _on_ready_read(self) -> None:
        self._buf += bytes(self._serial.readAll())
        *lines, self._buf = self._buf.split(b"\n")
        for raw in lines:
            line = raw.decode("ascii", "replace").strip()
            if line:
                self.lineReceived.emit(line)

    def _on_serial_error(self, err) -> None:
        if err in (QSerialPort.NoError, QSerialPort.TimeoutError):
            return
        msg = self._serial.errorString() if self._serial else str(err)
        self.errorText.emit(f"Serial error: {msg}")
        if err == QSerialPort.ResourceError:      # cable pulled / Teensy reset
            self._ping.stop()
            self._serial.close()
            self._serial.deleteLater()
            self._serial = None
            self._set_state(LinkState.ERROR)
