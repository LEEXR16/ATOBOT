// config.h — IDs, joint limits, MIT ranges, gains, safety limits and rates for ATOBOT_fw (Teensy 4.1)
#pragma once
#include <Arduino.h>

#define FW_NAME     "ATOBOT_fw"
#define FW_VERSION  "0.2 (2026-10-01)"

// ---- CAN: CAN1 on Teensy 4.1 (CTX1 = pin 22, CRX1 = pin 23), 3.3 V transceiver, 1 Mbps ----
#define CAN_BAUD    1000000

// ---- Joints: index 0 = ankle, 1 = toe. Both CubeMars AK60-39 V3.0 KV80, 1:1 to the joint ----
#define NUM_JOINTS  2
const uint8_t JOINT_ID[NUM_JOINTS]        = {2, 1};       // CAN IDs: ANKLE = 2, TOE = 1
const char*   JOINT_NAME[NUM_JOINTS]      = {"ANKLE", "TOE"};
const int8_t  JOINT_DIR[NUM_JOINTS]       = {+1, +1};       // joint deg = DIR * motor deg. Flip if a joint moves the wrong way (VERIFY on bench)
const float   JOINT_MIN_DEG[NUM_JOINTS]   = {0.0f, 0.0f};   // range of motion, joint deg (0 = where ZERO was set)
const float   JOINT_MAX_DEG[NUM_JOINTS]   = {80.0f, 60.0f};
const float   DEFAULT_KP[NUM_JOINTS]      = {10.0f, 10.0f}; // Nm/rad  — start low, tune up
const float   DEFAULT_KD[NUM_JOINTS]      = {0.5f, 0.5f};   // Nm*s/rad

// ---- MIT frame ranges (AK Series manual v3, §4.2) ----
// AK60-39 is not in the manual's table. P, Kp and Kd ranges are the same for every AK model.
// V and T ranges only matter when v_des / t_ff are non-zero, and this version always sends 0
// (0 encodes to mid-scale whatever the range). VERIFY both with CubeMars R-Link before using them.
#define MIT_P_MAX   12.56f      // rad
#define MIT_V_MAX   10.0f       // rad/s  VERIFY
#define MIT_T_MAX   72.0f       // Nm     VERIFY
#define MIT_KP_MAX  500.0f
#define MIT_KD_MAX  5.0f

// ---- Feedback scaling (timed upload, manual §4.3.1): pos 0.1 deg, speed 10 ERPM, current 0.01 A ----
#define MOTOR_POLE_PAIRS  14
#define MOTOR_GEAR        39.0f
#define ERPM_TO_DEG_S     (6.0f / (MOTOR_POLE_PAIRS * MOTOR_GEAR))   // electrical rpm -> output deg/s   VERIFY
#define NM_PER_AMP        (0.12f * MOTOR_GEAR)                       // Kt 0.12 Nm/A x 39 -> output Nm   VERIFY

// ---- Safety ----
#define KP_LIMIT            150.0f  // GAIN command clamp (below MIT_KP_MAX on purpose)
#define KD_LIMIT            3.0f
#define MAX_JOINT_SPEED     90.0f   // deg/s, peak speed of POS moves and sine
#define MIN_MOVE_TIME_S     0.3f
#define MAX_MOVE_TIME_S     30.0f
#define SINE_MAX_HZ         2.0f
#define SINE_RAMP_S         2.0f    // sine amplitude ramps in over this time
#define OVERTRAVEL_DEG      5.0f    // active and measured beyond ROM by this much -> fault, motors limp
#define CURRENT_TRIP_A      8.0f    // ~37 Nm at the joint (rated 24 Nm)
#define CURRENT_TRIP_MS     300
#define FEEDBACK_TIMEOUT_MS 200     // no CAN upload for this long -> motor LOST
#define PC_TIMEOUT_MS       1000    // streaming on and no line from the PC -> POS / SINE stop, HOLD
#define ZERO_TOLERANCE_DEG  1.0f    // origin accepted when feedback reads within this of 0

// ---- Rates ----
#define CONTROL_PERIOD_US   2000    // MIT commands at 500 Hz per motor
#define TELEMETRY_PERIOD_MS 10      // D lines at 100 Hz

// Time of this loop pass (millis() read once at the top of loop()). Everything that stamps a time uses it:
// a fresh millis() can be 1 ms ahead of the loop's "now", and "now - stamp" then wraps to ~49 days.
uint32_t loopNow = 0;

// Modes: IDLE = limp (Kp = Kd = 0), HOLD = hold setpoint, POSITION = timed move, SINE = sine about a centre
enum Mode : uint8_t { MODE_IDLE = 0, MODE_HOLD = 1, MODE_POSITION = 2, MODE_SINE = 3 };

// Fault bits, 4 per joint: joint i uses bits 4*i .. 4*i+3
#define FAULT_LOST        0x1
#define FAULT_MOTOR_ERR   0x2
#define FAULT_OVERTRAVEL  0x4
#define FAULT_OVERCURRENT 0x8
