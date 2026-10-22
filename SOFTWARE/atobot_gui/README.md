# ATOBOT GUI

This is the desktop GUI for ATOBOT v4. It connects to the Teensy over USB serial and works with the `ATOBOT_fw` firmware. Its style matches the Dynabo GUI: PySide6 and pyqtgraph with the same dark theme.

## Run

Double-click **`run_gui.bat`**.

- **First run:** it creates a Python environment in `%USERPROFILE%\.venvs\atobot`. This needs internet and takes a few minutes.
- **No hardware?** Choose **Simulator** as the port. It runs the same commands as the firmware, with simulated joint movement.

## Layout

| Area | What it shows |
|---|---|
| **Header** | Firmware version, stream rate and loss, mode (IDLE / HOLD / POSITION / SINE), faults, **Play game / Back to live** button, port and Connect button |
| **Left** | For each joint (ankle, toe): angle, target, speed, current, torque, temperature, voltage (0 for now), motor error, zero status and gains. Below that: link statistics and the firmware message log |
| **Centre** | **LIVE** tab: ankle and toe angle plots (target and actual, with dashed range-of-motion lines), plus a torque plot. Plot window: 5, 10 or 30 s. **GAME** tab: Ankle Flyer (see below) |
| **Right** | Motors (enable, disable, zero, clear faults), Position, Sine, Gains, Recording, **STOP** |

- **When motion buttons work:** only while the motors are enabled, at least one joint is zeroed, and there are no faults. A joint that isn't zeroed is left where it is.
- **Sine checks:** the GUI runs the same checks as the firmware (stays inside the range of motion, peak speed at most 90°/s) and explains why **Start sine** is greyed out.
- **STOP and Esc:** both stop any motion and the motors hold. If you disconnect, the GUI sends STOP first.
- **Recordings:** saved to `Documents\ATOBOT\ATOBOT_<date>_<time>.csv`, one row per data line (100 per second).

## Game: Ankle Flyer (GAME tab)

A Flappy-Bird style demo. The bird's height **is** the joint angle (no gravity), so each gap is a range-of-motion target.

- **Hand mode:** press **Disable** (motors limp), then move the ankle (or toe) by hand.
- **Robot mode:** press **Enable**. The GUI sends one POS move per pipe and the robot flies the bird itself.
- **Before playing:** the joint must be zeroed. **Calibrate range** (hand mode) maps the bird to the range you actually reach in 6 s; otherwise the full ROM is used.
- **Levels:** Easy, Normal, Hard. The game speeds up a little with every point.
- **Keys:** Space starts. Esc (STOP) also ends the round. The round also ends if the link drops, a fault appears, or the motor mode no longer matches the player mode.
- **After a round:** it shows the score, the time and the range of motion actually used.

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
ui/game.py           Ankle Flyer game (GAME tab)
ui/main_window.py    the window
```
