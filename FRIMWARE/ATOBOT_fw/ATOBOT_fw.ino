// ATOBOT_fw — ATOBOT v4 firmware, Teensy 4.1.
// Two CubeMars AK60-39 V3.0 (ANKLE = CAN ID 2, TOE = CAN ID 1) in MIT mode on CAN1 at 1 Mbps.
// Phase 1: position control = MIT PD (Kp, Kd) with smooth setpoints (POS moves, SINE).
// USB serial to the PC GUI, or the Arduino Serial Monitor (Newline). Type H for help. See README.md.
// Needs the FlexCAN_T4 library (comes with Teensyduino).

#include <FlexCAN_T4.h>

#include "config.h"
#include "motors.h"
#include "control.h"
#include "comms.h"

void setup() {
  Serial.begin(115200);                   // USB: baud is ignored
  while (!Serial && millis() < 3000) {}   // give the Serial Monitor time to connect
  printVersion();
  motorsInit();
  Serial.println("I,mode IDLE (motors limp). ZERO each joint, then EN. Type H for help");
}

void loop() {
  uint32_t now = millis();
  loopNow = now;
  motorsReadCan(now);
  for (uint8_t i = 0; i < NUM_JOINTS; i++) motorService(i, now);
  pollCommands();
  zeroTick(now);
  safetyTick(now);
  pcWatchdog(now);
  controlTick(now);
  telemetryTick(now);
}
