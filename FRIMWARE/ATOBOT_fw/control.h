// control.h — modes (IDLE / HOLD / POSITION / SINE), zeroing, safety checks and the 500 Hz MIT loop.
// Every mode change starts from the current setpoint, so the motors never jump.
#pragma once

Mode mode = MODE_IDLE;
uint16_t faults = 0;                 // latched, see FAULT_* in config.h. Any fault -> IDLE (limp)

// POSITION move, also used for the sine approach to its centre
float moveStart[NUM_JOINTS], moveGoal[NUM_JOINTS];
uint32_t moveStartMs = 0;
float moveDur = 1.0f;

// SINE
float sineCenter[NUM_JOINTS], sineAmp[NUM_JOINTS];
float sineFreq = 0;
bool sineApproach = false;           // true while moving to the centres
uint32_t sineStartMs = 0;

// Zeroing (set origin), one joint at a time
int8_t zeroJoint = -1;
uint8_t zeroTries = 0;
uint32_t zeroSentMs = 0;

uint32_t overCurSinceMs[NUM_JOINTS] = {0, 0};
uint32_t lastControlUs = 0;

const char* modeText(Mode m) {
  switch (m) {
    case MODE_IDLE:     return "IDLE";
    case MODE_HOLD:     return "HOLD";
    case MODE_POSITION: return "POSITION";
    default:            return "SINE";
  }
}

bool isActive() { return mode != MODE_IDLE; }
bool jointUsable(uint8_t i) { return mot[i].state == M_READY && mot[i].zeroed; }

float clampf(float v, float lo, float hi) { return v < lo ? lo : (v > hi ? hi : v); }

// Minimum-jerk profile, s in 0..1. Peak speed = 1.875 * distance / time.
float minJerk(float s) {
  s = clampf(s, 0.0f, 1.0f);
  return s * s * s * (10.0f - 15.0f * s + 6.0f * s * s);
}

float moveTimeFor(float dist, float requested) {
  float tMin = 1.875f * fabsf(dist) / MAX_JOINT_SPEED;
  return max(max(requested, tMin), MIN_MOVE_TIME_S);
}

void setMode(Mode newMode, const char* why) {
  if (newMode == mode) return;
  if (mode == MODE_IDLE)
    for (uint8_t i = 0; i < NUM_JOINTS; i++) mot[i].cmd = mot[i].pos;   // take over from where it is
  Serial.printf("I,mode %s -> %s (%s)\n", modeText(mode), modeText(newMode), why);
  mode = newMode;
}

void raiseFault(uint8_t i, uint16_t bit, const char* text) {
  uint16_t f = bit << (4 * i);
  if (faults & f) return;
  faults |= f;
  Serial.printf("E,FAULT %s: %s. Motors limp\n", mot[i].name, text);
  setMode(MODE_IDLE, "fault");
}

void onMotorLost(uint8_t i) { raiseFault(i, FAULT_LOST, "feedback lost"); }

// ---- Commands (called from commands.h). Return nullptr on success or the reason for refusing ----

const char* cmdEnable() {
  if (faults) return "fault active, CLR first";
  if (mode == MODE_IDLE) setMode(MODE_HOLD, "EN");
  return nullptr;
}

const char* cmdStartZero(int8_t i) {
  if (mode != MODE_IDLE) return "disable (DIS) before ZERO";
  if (zeroJoint >= 0) return "zeroing already in progress";
  if (mot[i].state != M_READY) return "motor not READY";
  zeroJoint = i;
  zeroTries = 1;
  zeroSentMs = loopNow;
  mot[i].zeroed = false;
  canSetOrigin(mot[i].id);
  Serial.printf("I,%s set origin sent\n", mot[i].name);
  return nullptr;
}

// targets in deg, NAN = keep that joint where it is
const char* cmdMove(const float* target, float timeS) {
  if (!isActive()) return "not enabled (EN)";
  if (faults) return "fault active";
  if (!(timeS >= 0.0f && timeS <= MAX_MOVE_TIME_S)) return "time out of range";
  bool any = false;
  float dist = 0;
  for (uint8_t i = 0; i < NUM_JOINTS; i++) {
    moveStart[i] = mot[i].cmd;
    moveGoal[i] = mot[i].cmd;
    if (isnan(target[i])) continue;
    if (!jointUsable(i)) return mot[i].state != M_READY ? "motor not READY" : "joint not zeroed";
    if (target[i] < JOINT_MIN_DEG[i] || target[i] > JOINT_MAX_DEG[i]) return "target outside ROM";
    moveGoal[i] = target[i];
    dist = max(dist, fabsf(target[i] - moveStart[i]));
    any = true;
  }
  if (!any) return "no joint to move";
  moveDur = moveTimeFor(dist, timeS);
  if (moveDur > timeS + 0.01f) Serial.printf("I,move time raised to %.2f s (max %.0f deg/s)\n", moveDur, MAX_JOINT_SPEED);
  moveStartMs = loopNow;
  sineApproach = false;
  if (mode == MODE_POSITION) Serial.println("I,new POS target");
  setMode(MODE_POSITION, "POS");
  return nullptr;
}

// centre and amplitude per joint (NAN centre = joint not in the sine), one frequency for both
const char* cmdSine(const float* center, const float* amp, float freq) {
  if (!isActive()) return "not enabled (EN)";
  if (faults) return "fault active";
  if (!(freq > 0.0f && freq <= SINE_MAX_HZ)) return "frequency out of range";
  bool any = false;
  float dist = 0;
  for (uint8_t i = 0; i < NUM_JOINTS; i++) {
    moveStart[i] = mot[i].cmd;
    moveGoal[i] = mot[i].cmd;
    sineCenter[i] = mot[i].cmd;
    sineAmp[i] = 0;
    if (isnan(center[i])) continue;
    if (!jointUsable(i)) return mot[i].state != M_READY ? "motor not READY" : "joint not zeroed";
    if (!(amp[i] >= 0.0f)) return "amplitude must be >= 0";
    if (center[i] - amp[i] < JOINT_MIN_DEG[i] || center[i] + amp[i] > JOINT_MAX_DEG[i])
      return "centre +/- amplitude outside ROM";
    if (2.0f * PI * freq * amp[i] > MAX_JOINT_SPEED) return "too fast: 2*pi*f*amp above max joint speed";
    moveGoal[i] = center[i];
    sineCenter[i] = center[i];
    sineAmp[i] = amp[i];
    dist = max(dist, fabsf(center[i] - moveStart[i]));
    any = true;
  }
  if (!any) return "no joint in the sine";
  sineFreq = freq;
  moveDur = moveTimeFor(dist, 1.0f);
  moveStartMs = loopNow;
  sineApproach = true;
  setMode(MODE_SINE, "SIN");
  return nullptr;
}

const char* cmdGain(int8_t i, float kp, float kd) {
  if (!(kp >= 0.0f && kp <= KP_LIMIT)) return "Kp out of range";
  if (!(kd >= 0.0f && kd <= KD_LIMIT)) return "Kd out of range";
  mot[i].kp = kp;
  mot[i].kd = kd;
  Serial.printf("I,%s gains Kp %.2f Kd %.3f\n", mot[i].name, kp, kd);
  return nullptr;
}

const char* cmdClearFaults() {
  if (mode != MODE_IDLE) return "only in IDLE";
  faults = 0;
  Serial.println("I,faults cleared (they come back if the cause is still there)");
  return nullptr;
}

// ---- Zeroing: confirm the origin from the next feedback, retry up to 3 times ----
void zeroTick(uint32_t now) {
  if (zeroJoint < 0) return;
  Motor& m = mot[zeroJoint];
  if (m.state != M_READY) {
    Serial.printf("E,%s zero aborted: motor not READY\n", m.name);
    zeroJoint = -1;
    return;
  }
  if (now - zeroSentMs < 100 || m.lastFbMs <= zeroSentMs + 20) return;
  if (fabsf(m.pos) < ZERO_TOLERANCE_DEG) {
    m.zeroed = true;
    m.cmd = m.pos;
    Serial.printf("I,%s zeroed (pos %+.1f deg)\n", m.name, m.pos);
    zeroJoint = -1;
  } else if (zeroTries < 3) {
    zeroTries++;
    zeroSentMs = now;
    canSetOrigin(m.id);
    Serial.printf("I,%s origin not confirmed (pos %+.1f), retry %u\n", m.name, m.pos, zeroTries);
  } else {
    Serial.printf("E,%s zero FAILED after 3 tries (pos %+.1f deg)\n", m.name, m.pos);
    zeroJoint = -1;
  }
}

// ---- Safety: motor error, over-travel, over-current ----
void safetyTick(uint32_t now) {
  for (uint8_t i = 0; i < NUM_JOINTS; i++) {
    Motor& m = mot[i];
    if (m.state != M_READY) continue;
    if (m.err) raiseFault(i, FAULT_MOTOR_ERR, motorErrorText(m.err));
    if (!isActive()) {
      overCurSinceMs[i] = 0;
      continue;
    }
    if (m.zeroed && (m.pos < JOINT_MIN_DEG[i] - OVERTRAVEL_DEG || m.pos > JOINT_MAX_DEG[i] + OVERTRAVEL_DEG))
      raiseFault(i, FAULT_OVERTRAVEL, "over-travel");
    if (fabsf(m.cur) > CURRENT_TRIP_A) {
      if (!overCurSinceMs[i]) overCurSinceMs[i] = now;
      else if (now - overCurSinceMs[i] > CURRENT_TRIP_MS) raiseFault(i, FAULT_OVERCURRENT, "over-current");
    } else {
      overCurSinceMs[i] = 0;
    }
  }
}

// ---- 500 Hz MIT loop ----
void controlTick(uint32_t now) {
  uint32_t us = micros();
  if (us - lastControlUs < CONTROL_PERIOD_US) return;
  lastControlUs = us;

  float s = (now - moveStartMs) / 1000.0f / moveDur;
  float tSine = (now - sineStartMs) / 1000.0f;
  float env = tSine < SINE_RAMP_S ? tSine / SINE_RAMP_S : 1.0f;

  for (uint8_t i = 0; i < NUM_JOINTS; i++) {
    Motor& m = mot[i];
    if (m.state != M_READY) continue;            // never command a motor without feedback

    if (mode == MODE_IDLE) {
      m.cmd = m.pos;
      mitSend(m, m.pos, 0.0f, 0.0f);             // limp
      continue;
    }

    float target = m.cmd;                        // HOLD
    if (jointUsable(i)) {
      if (mode == MODE_POSITION || (mode == MODE_SINE && sineApproach))
        target = moveStart[i] + (moveGoal[i] - moveStart[i]) * minJerk(s);
      else if (mode == MODE_SINE)
        target = sineCenter[i] + env * sineAmp[i] * sinf(2.0f * PI * sineFreq * tSine);
      target = clampf(target, JOINT_MIN_DEG[i], JOINT_MAX_DEG[i]);
    }
    m.cmd = target;
    mitSend(m, m.cmd, m.kp, m.kd);
  }

  if (s >= 1.0f) {
    if (mode == MODE_POSITION) {
      setMode(MODE_HOLD, "move done");
    } else if (mode == MODE_SINE && sineApproach) {
      sineApproach = false;
      sineStartMs = now;
      Serial.println("I,sine started");
    }
  }
}
