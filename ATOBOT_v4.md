# ATOBOT v4 — Ankle TOe roBOT

> **Shared project file.** Single source of truth for progress, decisions and tasks.
> Claude reads this at the start of every session and updates it after every step.
> Last updated: **2026-10-05**

---

## ▶ Resume here (next session)

**Where we stopped (2026-10-01):** firmware + GUI run on the real hardware (COM9). Zero, Enable, POS moves and SINE
work, but the sine stopped after ~1 cycle. Root cause found and **fixed in fw 0.2** — the board was still running
**fw 0.1** in the last test (GUI header showed `ATOBOT_fw 0.1`).

**Next steps, in order:**
1. Disconnect the GUI → upload `FRIMWARE/ATOBOT_fw` → reconnect → header must show **`ATOBOT_fw 0.2`**.
2. Re-run the sine (e.g. ankle 40 ± 40°, toe 30 ± 15°, 0.2 Hz) — it must run until STOP.
   If it still stops: copy the **Messages** lines around the stop (`mode SINE -> HOLD (...)`).
3. Check JOINT_DIR (positive command = intended direction) for both joints.
4. Tune Kp/Kd per joint.
5. Answer Q11 (limit switches) → firmware limit-switch faults + calibration.
6. GUI changes the user wants (to be listed after testing).

---

## 1. Goal

Therapeutic rehabilitation device for the **ankle** and **toes**.
v4 is a simplification of v3 (capstan drive, see `../FAB/V3.x`, `../ARCHIVES`) with a **direct-drive approach**.

**Control roadmap:** position control → (later) impedance control on both modules.

---

## 2. System Architecture (v4)

```
 PC (Python GUI) ──USB serial──► Teensy 4.1 ──CAN1 TX/RX──► 3.3 V CAN transceiver ══CAN 1 Mbps══► Ankle motor (ID 2)
                                                                                              └──► Toe motor   (ID 1)
```

| Module | Drive | Motor | CAN ID | Ratio | ROM |
|---|---|---|---|---|---|
| Ankle | Direct coupled | CubeMars AK60-39 V3.0, Kv80 | **2** | 1:1 | 0–80° |
| Toe | Bowden cable + pulleys | CubeMars AK60-39 V3.0, Kv80 | **1** | 1:1 pulley | 0–60° |

### Hardware
- **MCU:** Teensy 4.1 (CAN1: pin 22 = CTX1, pin 23 = CRX1)
- **CAN transceiver:** 3.3 V transceiver (replaces MCP2551, solves R1)
- **Motor bus:** CAN, 1 Mbps, 48 V motor supply
- **PC link:** USB serial

### Firmware — `FRIMWARE/ATOBOT_fw/` (current: **v0.2**)
- Teensy + FlexCAN_T4 (built-in CAN controller)
- **CubeMars MIT mode only — one codebase for both phases**
  - MIT command: τ = Kp·(p_des − p) + Kd·(v_des − v) + τ_ff (ext ID `(8<<8)|id`)
  - Phase 1 position control = Kp/Kd PD, v_des = 0, τ_ff = 0, smooth setpoints (min-jerk POS, ramped SINE)
  - Phase 3 impedance control = same frame, low Kp (stiffness K), Kd (damping B), τ_ff (assist/gravity)
- Modes: IDLE (limp) / HOLD / POSITION / SINE. Manual ZERO per joint.
- Safety: ROM limits, over-travel, over-current, motor error, feedback lost → limp; STOP / PC timeout → hold
- USB: ASCII commands, `D` telemetry at 100 Hz (see firmware README)
- Files: `config.h` (all limits/IDs), `motors.h` (CAN/MIT), `control.h` (modes/safety), `comms.h` (USB)

### Software — `SOFTWARE/atobot_gui/` (current: **v0.1**)
- Python desktop GUI, same stack & style as Dynabo: **PySide6 + pyqtgraph**, dark theme
  (ref: `I:\001_Dynamic Balance Board\CODE\DYNABO-RR-main\DYNABO-RR-main\software\dynabo_gui`)
- Start: `run_gui.bat` (creates venv `%USERPROFILE%\.venvs\atobot` on first run)
- QtSerialPort link + **"Simulator" port** (test without hardware)
- Left: per-joint values (angle, target, speed, current, torque, temp, voltage = 0, error, zero, gains), link stats, message log
- Centre: ankle / toe angle plots (target vs actual, ROM lines), torque plot
- Right: Motors (enable/disable/zero/clear), Position, Sine, Gains, Record CSV, STOP (Esc)
- Recordings: `Documents\ATOBOT\ATOBOT_<date>_<time>.csv`

---

## 3. Open Questions

- [x] **Q1:** Teensy 4.1
- [x] **Q2:** Toe = same AK60-39 V3.0 Kv80
- [x] **Q3:** Ankle = ID 2, Toe = ID 1 (swapped 2026-10-01)
- [x] **Q4:** Dynabo ref → `I:\001_Dynamic Balance Board\CODE\DYNABO-RR-main\DYNABO-RR-main`
- [x] **Q5:** Ankle 0–80°, Toe 0–60°
- [x] **Q6:** MIT mode from day 1; Phase 1 = PD position control via Kp/Kd
- [x] **Q7:** 48 V
- [x] **Q8:** 3.3 V transceiver
- [x] **Q9:** Voltage shown in GUI but fixed at 0 for now (no measurement yet)
- [x] **Q10:** GUI layout approved (changes to come once the base GUI runs)
- [ ] **Q11:** Limit switches — type (NC/NO), Teensy pins, 4 switches (ankle min/max, toe min/max)?

## 4. Risks / Notes

- **R1 — Logic levels (SOLVED):** 3.3 V transceiver used (Teensy 4.1 is not 5 V tolerant).
- **R2 — CAN termination:** 120 Ω at both ends of the bus.
- **R3 — Bowden cable:** stretch/friction/backlash means toe joint angle ≠ motor angle exactly; consider a joint encoder later for impedance control.
- **R4 — Patient safety:** hard mechanical stops + limit switches + software limits + E-stop before any human testing.
- **R5 — Mode switch (SOLVED):** MIT frames work on the V3 motors without any mode switch; ZERO (origin frame) also applies to MIT positions.
- **R6 — PD steady-state error:** MIT is PD (no integral) → under load/gravity the joint sits slightly off target. Fix with higher Kp or a τ_ff gravity/friction term.
- **R7 — MIT hold on comm loss:** motor keeps executing last command if the Teensy stops → PC loss handled (watchdog → HOLD); Teensy crash/reset still leaves last command active → hardware E-stop on 48 V.
- **R8 — Unverified scaling:** AK60-39 not in manual MIT table; `MIT_V_MAX`, `MIT_T_MAX`, `ERPM_TO_DEG_S`, `NM_PER_AMP` marked VERIFY in `config.h`. Safe now because v_des = t_ff = 0.
- **R9 — Packet loss:** last hardware run showed ~1.1 % lost D lines (sim: 0 %). Harmless for display; watch it (possible USB/PC load).

---

## 5. TODO

### 🔴 Now — Phase 1: Bring-up & Position Control
- [x] Answer open questions Q1–Q10
- [x] MIT frame format from V3 manual (ext ID 8, Kp/Kd/P/V/T layout; feedback = timed upload)
- [x] Wiring table: Teensy ↔ 3.3 V transceiver ↔ motors (in firmware README)
- [x] Firmware: CAN init + set zero (origin, confirmed + retries)
- [x] Firmware: read & decode motor feedback (pos, vel, current, torque, temp, error)
- [x] Firmware: MIT position command, min-jerk POS moves + SINE mode
- [x] Firmware: 2 motors
- [x] Firmware: USB serial protocol (D telemetry 100 Hz, ASCII commands)
- [x] Firmware: safety — ROM limits, over-travel, over-current, motor error, feedback lost, PC watchdog
- [x] Software: serial connection + port selection (+ Simulator port)
- [x] Software: live dashboard for 2 motors
- [x] Software: control panel (enable, disable, zero, POS, SINE, gains, STOP/Esc, CSV record)
- [x] Flash firmware + first hardware run (both motors READY, zero, EN, POS, SINE start)
- [x] Fix: sine/moves stopping randomly (fw 0.2, `loopNow`)
- [ ] **Upload fw 0.2 and confirm sine runs until STOP** ← next
- [ ] Bench: verify JOINT_DIR for both joints
- [ ] Bench: verify speed/torque scaling (`ERPM_TO_DEG_S`, `NM_PER_AMP`)
- [ ] R-Link: confirm upload rate 200–500 Hz
- [ ] Verify AK60-39 MIT_V_MAX / MIT_T_MAX (R-Link or CubeMars support)
- [ ] Tune Kp/Kd: ankle (direct) and toe (Bowden) separately — start low, raise Kp, add Kd until no overshoot
- [ ] Hardware E-stop on 48 V line
- [ ] **Mechanical end stops + limit switches** (hard min/max) on ankle and toe — 4 switches
- [ ] Decide limit-switch pins & wiring (INPUT_PULLUP, NC preferred so a broken wire reads as "hit") — Q11
- [ ] Firmware: limit switch hit → fault, motors limp (active in every mode)
- [ ] Firmware: auto-calibration — move slowly to min switch → set zero; move to max switch → measure ROM; set soft limits inside the switches
- [ ] GUI: limit switch indicators + "Calibrate" button
- [ ] GUI: user's change list after testing
- [ ] Bench test: toe through Bowden cable under load

### 🟡 Next — Phase 2: Data & Usability
- [x] Live plots (angle/torque vs time)
- [x] CSV data logging
- [ ] Repeated ROM exercise (N cycles between two angles)
- [ ] Measure 48 V bus voltage (Teensy ADC + divider) → replace vbus = 0

### 🟢 Later — Phase 3: Impedance Control
- [ ] Impedance control law (K, B, θ_eq) per joint
- [ ] Torque calibration / friction compensation (esp. toe cable)
- [ ] Therapy modes (passive, assistive, resistive)
- [ ] Clinical safety review

---

## 6. Progress Log

| Date | Update |
|---|---|
| 2026-10-01 | v4 project file created. Architecture defined. Phase 1 = position control. |
| 2026-10-01 | Q1–Q5, Q7 answered. Reviewed Dynabo repo: AK driver (FlexCAN_T4) + PySide6/pyqtgraph GUI reusable. |
| 2026-10-01 | **Decision: MIT mode only.** Position control = MIT with tuned Kp/Kd → impedance later is just a gain change. |
| 2026-10-01 | Q8, Q9 answered. **Firmware v0.1 written & compiles** (`FRIMWARE/ATOBOT_fw`). GUI layout proposed. |
| 2026-10-01 | GUI layout approved. **GUI v0.1 written** (`SOFTWARE/atobot_gui`), tested headless against the simulator. Limit switches + calibration added to TODO. |
| 2026-10-01 | CAN IDs swapped: **Ankle = 2, Toe = 1** (`config.h` JOINT_ID). GUI/command joint numbers unchanged (1 = ankle, 2 = toe). |
| 2026-10-01 | **First hardware run** (COM9): both motors READY, zero, EN, POS working; MIT works without mode switch. Sine stopped after ~1 cycle. |
| 2026-10-01 | **Bug fixed (fw 0.2):** `millis()` stamp 1 ms ahead of loop `now` wrapped `now - lastPcMs` → false PC timeout → HOLD. Same bug could make a POS move jump to its target in one step. All time stamps now use `loopNow`. Second test still showed fw 0.1 on the board → **re-upload needed**. Session paused. |
| 2026-10-05 | Project put under git and pushed to GitHub: https://github.com/LEEXR16/ATOBOT (branch `main`). `__pycache__` ignored. |

## 7. Decisions

| Date | Decision | Why |
|---|---|---|
| 2026-10-01 | Move from v3 (capstan) to v4 direct approach | Simplify robot |
| 2026-10-01 | Start with position control, impedance later | Get hardware/comms working first |
| 2026-10-01 | MIT mode only (no Servo mode) | Single code path; Kp/Kd tuning carries straight into impedance control |
| 2026-10-01 | Faults → motors limp; STOP / PC loss → hold | Limp is safest on a fault; a plain stop should not drop the limb |
| 2026-10-01 | Manual ZERO per joint (limit-switch calibration later) | Joint may not be at 0° when powered |
| 2026-10-01 | GUI uses QtSerialPort (no pyserial) + Simulator port | One less dependency; GUI testable without hardware |
| 2026-10-01 | ASCII USB protocol | Same commands from GUI and Serial Monitor; bandwidth is not an issue |
| 2026-10-05 | Code versioned on GitHub (LEEXR16/ATOBOT) | Backup + history |
