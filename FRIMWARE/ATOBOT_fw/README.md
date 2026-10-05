# ATOBOT_fw

Firmware for ATOBOT v4 on a **Teensy 4.1**. It drives two CubeMars **AK60-39 V3.0** motors in **MIT mode** over CAN:

| Joint | CAN ID | Range of motion |
|---|---|---|
| Ankle | 2 | 0 to 80° |
| Toe | 1 | 0 to 60° |

**Position control in phase 1.** The motor runs a PD loop inside the MIT frame: `τ = Kp·(p_des − p) − Kd·v`. The firmware feeds that loop smooth setpoints. Impedance control later uses the same frame with lower gains.

## Build

Open the folder in the Arduino IDE (Teensyduino), select **Teensy 4.1**, and upload. The only library it needs is FlexCAN_T4, which comes with Teensyduino.

## Wiring

| Teensy 4.1 | Transceiver (3.3 V, e.g. SN65HVD230) |
|---|---|
| 3.3 V | VCC |
| GND | GND |
| Pin 22 (CTX1) | TX / D |
| Pin 23 (CRX1) | RX / R |

- Connect CANH and CANL to both motors.
- Fit a 120 Ω termination resistor at each end of the bus.
- Join the grounds of the Teensy and the motor supply.
- The motors run from 48 V.

## Motor set-up (once, in CubeMars R-Link)

- **CAN IDs:** set the ankle to 2 and the toe to 1.
- **CAN bus:** set the rate to 1 Mbps.
- **Upload rate:** set the timed upload rate to 200–500 Hz. The firmware treats a motor as lost if no upload arrives for 200 ms.

## Commands

You can type these in the Serial Monitor (Newline) or send them from the GUI.

- **Joint numbers:** `j` is 1 for the ankle and 2 for the toe. These are joint numbers, not CAN IDs.
- **Leaving a joint alone:** `-` means "don't move this joint".

| Command | Does |
|---|---|
| `EN` | Enable: hold the current position |
| `DIS` | Disable: motors go limp |
| `STOP` | Stop a POS or SIN and hold here |
| `ZERO,j` | Set this joint's 0° at its current position (only when disabled) |
| `POS,ankle,toe,time` | Move to the given angles over `time` seconds, e.g. `POS,30,-,2` |
| `SIN,c1,a1,c2,a2,f` | Sine motion: centre and amplitude per joint, frequency in Hz, e.g. `SIN,40,20,-,0,0.5` |
| `GAIN,j,kp,kd` | Set gains: Kp in Nm/rad, Kd in Nm·s/rad |
| `CLR` | Clear faults (only when disabled) |
| `STREAM,0\|1` | Turn on 100 Hz `D` data lines and the PC watchdog (the GUI does this) |
| `S`, `VER`, `H`, `PING` | Status, version, help, keep-alive |

**Replies:**

| Reply | Means |
|---|---|
| `OK,<cmd>` | Command accepted |
| `E,<text>` | Command refused, or an error or fault |
| `I,<text>` | Information |
| `V,<name>,<ver>` | Firmware version |

**Data line (`D`):**

```
D,ms,mode,faults, [state,zeroed,cmd,pos,vel,cur,torque,temp,err,kp,kd] x2 (ankle, toe), vbus
```

| Field | Values |
|---|---|
| `mode` | 0 IDLE, 1 HOLD, 2 POSITION, 3 SINE |
| `state` | 0 WAIT, 1 READY, 2 LOST |
| `faults` | Four bits per joint (ankle bits 0–3, toe bits 4–7): lost, motor error, over-travel, over-current |
| `vbus` | Always 0 for now (not measured) |

## How the firmware behaves

- **At power-up the motors are limp (IDLE).** A motor gets no commands until its first feedback arrives.
- **Zero each joint before it can move.** Put the joint at its 0° end, then send `DIS` and `ZERO,j`. The zero is temporary: it's lost when the motor is power-cycled, and the firmware then marks the joint as not zeroed.
- **Every mode change starts from the current setpoint, so nothing jumps.**
  - **POS:** uses a minimum-jerk profile. The time is lengthened if the move would be faster than 90°/s.
  - **SIN:** moves to the centre first, then ramps the amplitude in over 2 s.
- **Safety:**
  - **Faults (motors go limp):** motor error code, lost feedback, over-travel (5° beyond the range of motion), or over-current (8 A for 300 ms). Faults stay set until `CLR`.
  - **Refused commands:** targets outside the range of motion, or a sine whose peak speed is above 90°/s.
  - **PC watchdog:** with `STREAM,1` on, if no line arrives for 1 s, any POS or SIN stops and the motors hold.

All limits are in `config.h`.

## To verify on the bench

- **Joint direction (`JOINT_DIR`):** command a positive move and check each joint moves the right way.
- **Origin in MIT mode:** check that `ZERO` (the servo-mode origin frame) also resets the position the MIT command uses.
- **Speed and torque scaling (`ERPM_TO_DEG_S`, `NM_PER_AMP`):** compare the reported values with a known motion and load.
- **MIT ranges (`MIT_V_MAX`, `MIT_T_MAX`):** confirm in R-Link before ever sending a non-zero velocity or torque feed-forward.

## First power-up

1. Power the Teensy over USB and open the Serial Monitor. Power the motors and check you see `READY` for both.
2. Send `S`. Turn each joint by hand and check that `pos` follows.
3. Put each joint at 0°, then send `ZERO,1` and `ZERO,2`.
4. Send `EN`. Gently push each joint: it should spring back.
5. Send `POS,10,-,3`, then `POS,0,-,3`. Repeat for the toe.
6. Tune the gains: raise Kp until the joint tracks well, then add Kd until the overshoot is gone.
