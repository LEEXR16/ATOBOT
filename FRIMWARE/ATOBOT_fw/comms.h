// comms.h — USB serial protocol with the PC (GUI or Arduino Serial Monitor, Newline).
// PC -> Teensy: one command per line, comma separated, case-insensitive (see printHelp).
// Teensy -> PC:
//   D,<ms>,<mode>,<faults>,<ankle 11 fields>,<toe 11 fields>,<vbus>      100 Hz while STREAM,1
//       per joint: state,zeroed,cmd,pos,vel,cur,torque,temp,err,kp,kd
//       mode 0 IDLE 1 HOLD 2 POSITION 3 SINE; state 0 WAIT 1 READY 2 LOST; vbus = 0 (not measured yet)
//   OK,<cmd>            command accepted
//   E,<text>            command refused, or an error / fault
//   I,<text>            information
//   V,<name>,<version>  firmware version
#pragma once

bool streaming = false;
uint32_t lastPcMs = 0;
uint32_t lastTelemetryMs = 0;
bool pcTimeoutReported = false;

char lineBuf[96];
uint8_t lineLen = 0;
bool lineOverflow = false;

void printVersion() { Serial.printf("V,%s,%s\n", FW_NAME, FW_VERSION); }

void printHelp() {
  Serial.println("I,--- ATOBOT_fw commands (j: 1 = ANKLE, 2 = TOE; '-' = leave that joint) ---");
  Serial.println("I,EN                  enable: hold where it is");
  Serial.println("I,DIS                 disable: motors limp");
  Serial.println("I,STOP                stop POS / SIN, hold here");
  Serial.println("I,ZERO,j              set joint zero here (only when disabled)");
  Serial.println("I,POS,ankle,toe,time  move to deg in time s, e.g. POS,30,-,2");
  Serial.println("I,SIN,c1,a1,c2,a2,f   sine: centre / amplitude deg per joint, freq Hz, e.g. SIN,40,20,-,0,0.5");
  Serial.println("I,GAIN,j,kp,kd        Kp Nm/rad, Kd Nm*s/rad");
  Serial.println("I,CLR                 clear faults (when disabled)");
  Serial.println("I,STREAM,0|1          100 Hz D lines + PC watchdog (the GUI turns this on)");
  Serial.println("I,S                   status    VER  version    PING  keep-alive");
}

void printStatus() {
  Serial.printf("I,mode %s, faults 0x%02X, stream %d, CAN tx fail %lu, rx other %lu\n", modeText(mode), faults,
                streaming, (unsigned long)canTxFail, (unsigned long)canRxOther);
  for (uint8_t i = 0; i < NUM_JOINTS; i++) {
    Motor& m = mot[i];
    Serial.printf("I,%s ID %u %s%s: cmd %+.1f pos %+.1f deg, vel %+.1f deg/s, %+.2f A (%+.1f Nm), %d C, err %u (%s), Kp %.2f Kd %.3f\n",
                  m.name, m.id, motorStateText(m.state), m.zeroed ? " zeroed" : " NOT zeroed", m.cmd, m.pos, m.vel,
                  m.cur, m.torque, m.temp, m.err, motorErrorText(m.err), m.kp, m.kd);
  }
}

// "-" -> NAN (leave that joint), otherwise the whole token must be a number
bool parseNum(const char* tok, float& out) {
  if (!tok) return false;
  while (*tok == ' ') tok++;
  if (tok[0] == '-' && (tok[1] == 0 || tok[1] == ' ')) { out = NAN; return true; }
  char* end;
  out = strtof(tok, &end);
  while (*end == ' ') end++;
  return end != tok && *end == 0;
}

bool parseJoint(const char* tok, int8_t& j) {
  float v;
  if (!parseNum(tok, v) || !(v == 1.0f || v == 2.0f)) return false;
  j = (int8_t)v - 1;
  return true;
}

void reply(const char* cmd, const char* err) {
  if (err) Serial.printf("E,%s: %s\n", cmd, err);
  else Serial.printf("OK,%s\n", cmd);
}

void handleLine(char* line) {
  char* tok[8];
  uint8_t n = 0;
  for (char* t = strtok(line, ","); t && n < 8; t = strtok(NULL, ",")) tok[n++] = t;
  if (n == 0) return;
  char* c = tok[0];
  while (*c == ' ') c++;
  for (char* p = c; *p; p++) *p = toupper(*p);
  for (char* p = c + strlen(c); p > c && p[-1] == ' '; ) *--p = 0;

  lastPcMs = loopNow;
  pcTimeoutReported = false;

  if (!strcmp(c, "PING")) return;
  if (!strcmp(c, "VER"))  { printVersion(); return; }
  if (!strcmp(c, "H") || !strcmp(c, "HELP")) { printHelp(); return; }
  if (!strcmp(c, "S"))    { printStatus(); return; }

  if (!strcmp(c, "STREAM")) {
    float v;
    if (n != 2 || !parseNum(tok[1], v)) return reply(c, "usage STREAM,0|1");
    streaming = v != 0.0f;
    return reply(c, nullptr);
  }
  if (!strcmp(c, "EN"))  return reply(c, cmdEnable());
  if (!strcmp(c, "DIS")) { setMode(MODE_IDLE, "DIS"); return reply(c, nullptr); }
  if (!strcmp(c, "STOP")) {
    if (mode == MODE_POSITION || mode == MODE_SINE) setMode(MODE_HOLD, "STOP");
    return reply(c, nullptr);
  }
  if (!strcmp(c, "CLR")) return reply(c, cmdClearFaults());

  if (!strcmp(c, "ZERO")) {
    int8_t j;
    if (n != 2 || !parseJoint(tok[1], j)) return reply(c, "usage ZERO,j (1 ankle, 2 toe)");
    return reply(c, cmdStartZero(j));
  }
  if (!strcmp(c, "POS")) {
    float t[NUM_JOINTS], time;
    if (n != 4 || !parseNum(tok[1], t[0]) || !parseNum(tok[2], t[1]) || !parseNum(tok[3], time))
      return reply(c, "usage POS,ankle,toe,time");
    return reply(c, cmdMove(t, time));
  }
  if (!strcmp(c, "SIN")) {
    float cen[NUM_JOINTS], amp[NUM_JOINTS], f;
    if (n != 6 || !parseNum(tok[1], cen[0]) || !parseNum(tok[2], amp[0]) || !parseNum(tok[3], cen[1]) ||
        !parseNum(tok[4], amp[1]) || !parseNum(tok[5], f))
      return reply(c, "usage SIN,c1,a1,c2,a2,f");
    return reply(c, cmdSine(cen, amp, f));
  }
  if (!strcmp(c, "GAIN")) {
    int8_t j;
    float kp, kd;
    if (n != 4 || !parseJoint(tok[1], j) || !parseNum(tok[2], kp) || !parseNum(tok[3], kd))
      return reply(c, "usage GAIN,j,kp,kd");
    return reply(c, cmdGain(j, kp, kd));
  }
  reply(c, "unknown command (H for help)");
}

void pollCommands() {
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\r' || ch == '\n') {
      if (!lineOverflow && lineLen > 0) {
        lineBuf[lineLen] = 0;
        handleLine(lineBuf);
      }
      lineLen = 0;
      lineOverflow = false;
    } else if (lineLen < sizeof(lineBuf) - 1) {
      lineBuf[lineLen++] = ch;
    } else {
      lineOverflow = true;
    }
  }
}

// GUI gone (no line while streaming) -> stop motion and hold. Not active for Serial Monitor use (STREAM,0).
void pcWatchdog(uint32_t now) {
  if (!streaming || pcTimeoutReported) return;
  if (now - lastPcMs > PC_TIMEOUT_MS && (mode == MODE_POSITION || mode == MODE_SINE)) {
    setMode(MODE_HOLD, "PC timeout");
    pcTimeoutReported = true;
  }
}

void telemetryTick(uint32_t now) {
  if (!streaming || now - lastTelemetryMs < TELEMETRY_PERIOD_MS) return;
  lastTelemetryMs = now;
  Serial.printf("D,%lu,%u,%u", (unsigned long)now, mode, faults);
  for (uint8_t i = 0; i < NUM_JOINTS; i++) {
    Motor& m = mot[i];
    Serial.printf(",%u,%u,%.2f,%.2f,%.1f,%.2f,%.2f,%d,%u,%.2f,%.3f", m.state, m.zeroed, m.cmd, m.pos, m.vel,
                  m.cur, m.torque, m.temp, m.err, m.kp, m.kd);
  }
  Serial.println(",0.0");
}
