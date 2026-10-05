# ATOBOT GUI

This is the desktop GUI for ATOBOT v4. It connects to the Teensy over USB serial and works with the `ATOBOT_fw` firmware. Its style matches the Dynabo GUI: PySide6 and pyqtgraph with the same dark theme.

## Run

Double-click **`run_gui.bat`**.

- **First run:** it creates a Python environment in `%USERPROFILE%\.venvs\atobot`. This needs internet and takes a few minutes.
- **No hardware?** Choose **Simulator** as the port. It runs the same commands as the firmware, with simulated joint movement.

## Layout

| Area | What it shows |
|---|---|
| **Header** | Firmware version, stream rate and loss, mode (IDLE / HOLD / POSITION / SINE), faults, port and Connect button |
| **Left** | For each joint (ankle, toe): angle, target, speed, current, torque, temperature, voltage (0 for now), motor error, zero status and gains. Below that: link statistics and the firmware message log |
| **Centre** | Ankle and toe angle plots (target and actual, with dashed range-of-motion lines), plus a torque plot. Plot window: 5, 10 or 30 s |
| **Right** | Motors (enable, disable, zero, clear faults), Position, Sine, Gains, Recording, **STOP** |

- **When motion buttons work:** only while the motors are enabled, at least one joint is zeroed, and there are no faults. A joint that isn't zeroed is left where it is.
- **Sine checks:** the GUI runs the same checks as the firmware (stays inside the range of motion, peak speed at most 90°/s) and explains why **Start sine** is greyed out.
- **STOP and Esc:** both stop any motion and the motors hold. If you disconnect, the GUI sends STOP first.
- **Recordings:** saved to `Documents\ATOBOT\ATOBOT_<date>_<time>.csv`, one row per data line (100 per second).

## Files

```
main.py              entry point
core/protocol.py     D line, commands, limits (match FRIMWARE/ATOBOT_fw/config.h)
core/link.py         QtSerialPort link + PING keep-alive; "Simulator" port
core/simulator.py    firmware stand-in for testing without hardware
core/model.py        latest sample, plot history, link stats, recording
core/recorder.py     CSV writer
ui/theme.py          dark theme (from Dynabo)
ui/widgets.py        cards, pills, slider rows, value rows (from Dynabo)
ui/plots.py          time plots
ui/main_window.py    the window
```
