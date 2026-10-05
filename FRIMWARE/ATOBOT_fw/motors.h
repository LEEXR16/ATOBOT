// motors.h — CubeMars AK60-39 V3 on CAN1: MIT command frames, set origin, timed-upload feedback.
// Manual: AK Series Module Product Manual v3 — §4.1.6 origin, §4.2 MIT, §4.3.1 upload.
// Everything stored here is in the JOINT frame (deg, deg/s, A, Nm): joint = JOINT_DIR * motor.
#pragma once
#include <FlexCAN_T4.h>

FlexCAN_T4<CAN1, RX_SIZE_256, TX_SIZE_16> Can0;

#define CAN_PACKET_SET_ORIGIN  5
#define CAN_PACKET_SET_MIT     8

enum MotorState : uint8_t { M_WAIT_FB = 0, M_READY = 1, M_LOST = 2 };

const char* motorStateText(MotorState s) {
  switch (s) {
    case M_WAIT_FB: return "WAIT";
    case M_READY:   return "READY";
    default:        return "LOST";
  }
}

struct Motor {
  uint8_t id;
  const char* name;
  int8_t dir;
  MotorState state;
  float pos, vel, cur, torque;   // feedback: deg, deg/s, A, Nm
  int8_t temp;
  uint8_t err;
  uint32_t fbCount;
  uint32_t lastFbMs;
  bool zeroed;                   // origin set this session (temporary origin, lost at motor power-off)
  float cmd;                     // last position sent, deg
  float kp, kd;                  // gains used in HOLD / POSITION / SINE
};

Motor mot[NUM_JOINTS];
uint32_t canTxFail = 0;
uint32_t canRxOther = 0;

// ---- CAN frames ----
void canTransmit(uint32_t id, const uint8_t* data, uint8_t len) {
  CAN_message_t msg;
  msg.id = id;
  msg.len = len;
  msg.flags.extended = 1;
  for (uint8_t i = 0; i < len; i++) msg.buf[i] = data[i];
  if (Can0.write(msg) != 1) canTxFail++;
}

uint16_t floatToUint(float x, float xMin, float xMax, uint8_t bits) {
  if (x < xMin) x = xMin;
  if (x > xMax) x = xMax;
  return (uint16_t)((x - xMin) * (float)((1 << bits) - 1) / (xMax - xMin) + 0.5f);
}

// MIT frame: tau = kp * (p_des - p) + kd * (v_des - v) + t_ff, with v_des = t_ff = 0.
// kp = kd = 0 makes the motor limp.
void mitSend(const Motor& m, float posDeg, float kp, float kd) {
  uint16_t p = floatToUint(m.dir * posDeg * DEG_TO_RAD, -MIT_P_MAX, MIT_P_MAX, 16);
  uint16_t v = floatToUint(0.0f, -MIT_V_MAX, MIT_V_MAX, 12);
  uint16_t k = floatToUint(kp, 0.0f, MIT_KP_MAX, 12);
  uint16_t d = floatToUint(kd, 0.0f, MIT_KD_MAX, 12);
  uint16_t t = floatToUint(0.0f, -MIT_T_MAX, MIT_T_MAX, 12);
  uint8_t b[8];
  b[0] = k >> 4;                          // Kp high 8
  b[1] = ((k & 0xF) << 4) | (d >> 8);     // Kp low 4 | Kd high 4
  b[2] = d & 0xFF;                        // Kd low 8
  b[3] = p >> 8;                          // position high 8
  b[4] = p & 0xFF;                        // position low 8
  b[5] = v >> 4;                          // speed high 8
  b[6] = ((v & 0xF) << 4) | (t >> 8);     // speed low 4 | torque high 4
  b[7] = t & 0xFF;                        // torque low 8
  canTransmit(m.id | ((uint32_t)CAN_PACKET_SET_MIT << 8), b, 8);
}

void canSetOrigin(uint8_t id) {           // 0 = temporary origin (lost at motor power-off)
  uint8_t b[1] = {0};
  canTransmit(id | ((uint32_t)CAN_PACKET_SET_ORIGIN << 8), b, 1);
}

// ---- Setup / receive ----
void motorsInit() {
  for (uint8_t i = 0; i < NUM_JOINTS; i++) {
    Motor& m = mot[i];
    m = Motor{};
    m.id = JOINT_ID[i];
    m.name = JOINT_NAME[i];
    m.dir = JOINT_DIR[i];
    m.state = M_WAIT_FB;
    m.kp = DEFAULT_KP[i];
    m.kd = DEFAULT_KD[i];
  }
  Can0.begin();
  Can0.setBaudRate(CAN_BAUD);
  Serial.printf("I,CAN1 %lu bps (TX 22 / RX 23). ANKLE = ID %u, TOE = ID %u. Waiting for motor feedback\n",
                (unsigned long)CAN_BAUD, JOINT_ID[0], JOINT_ID[1]);
}

void motorsReadCan(uint32_t now) {
  CAN_message_t msg;
  while (Can0.read(msg)) {
    uint8_t id = msg.id & 0xFF;
    Motor* m = nullptr;
    for (uint8_t i = 0; i < NUM_JOINTS; i++)
      if (mot[i].id == id) m = &mot[i];
    if (!m || msg.len < 8) {
      canRxOther++;
      continue;
    }
    const uint8_t* b = msg.buf;
    m->pos    = m->dir * (int16_t)(b[0] << 8 | b[1]) * 0.1f;
    m->vel    = m->dir * (int16_t)(b[2] << 8 | b[3]) * 10.0f * ERPM_TO_DEG_S;
    m->cur    = m->dir * (int16_t)(b[4] << 8 | b[5]) * 0.01f;
    m->torque = m->cur * NM_PER_AMP;
    m->temp   = (int8_t)b[6];
    if (b[7] != m->err) Serial.printf("I,%s motor error code %u -> %u\n", m->name, m->err, b[7]);
    m->err = b[7];
    m->fbCount++;
    m->lastFbMs = now;
  }
}

const char* motorErrorText(uint8_t e) {
  switch (e) {
    case 0:  return "none";
    case 1:  return "motor over-temperature";
    case 2:  return "over-current";
    case 3:  return "over-voltage";
    case 4:  return "under-voltage";
    case 5:  return "encoder fault";
    case 6:  return "MOSFET over-temperature";
    case 7:  return "motor lock-up";
    default: return "unknown";
  }
}

// Hooks implemented in control.h
void onMotorLost(uint8_t i);

// Feedback state machine for one motor
void motorService(uint8_t i, uint32_t now) {
  Motor& m = mot[i];
  switch (m.state) {
    case M_WAIT_FB:
      if (m.fbCount > 0) {
        m.cmd = m.pos;
        m.state = M_READY;
        Serial.printf("I,%s first feedback: pos %+.1f deg, temp %d C, error %u. READY (limp, not zeroed)\n",
                      m.name, m.pos, m.temp, m.err);
      }
      break;

    case M_READY:
      if (now - m.lastFbMs > FEEDBACK_TIMEOUT_MS) {
        m.state = M_LOST;
        Serial.printf("E,%s feedback LOST (no CAN upload for %u ms): motor power / CAN wiring?\n",
                      m.name, FEEDBACK_TIMEOUT_MS);
        onMotorLost(i);
      }
      break;

    case M_LOST:
      if (now - m.lastFbMs < 50) {
        m.cmd = m.pos;
        m.zeroed = false;            // motor may have been power-cycled -> temporary origin gone
        m.state = M_READY;
        Serial.printf("I,%s feedback back: pos %+.1f deg. NOT zeroed, set zero again\n", m.name, m.pos);
      }
      break;
  }
}
