#include <Servo.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

// Arduino controller for the two-servo hemispherical mapping stage.
//
// Serial protocol at 115200 baud:
//   PING
//   CENTER
//   MOVEABS,<base physical degrees>,<inclination physical degrees>
//   FIRE
//
// The Python application converts logical map angles into calibrated physical
// motor angles before sending MOVEABS.

// -----------------------------------------------------------------------------
// Board pins
// -----------------------------------------------------------------------------
// Defaults are suitable for an Arduino Uno/Nano. Update them for another board.
constexpr uint8_t BASE_SERVO_PIN = 9;
constexpr uint8_t INCLINATION_SERVO_PIN = 10;
constexpr uint8_t TMS_TRIGGER_PIN = 7;

// -----------------------------------------------------------------------------
// Servo pulse and physical limits
// -----------------------------------------------------------------------------
constexpr float BASE_MIN_DEG = 0.0F;
constexpr float BASE_MAX_DEG = 180.0F;
constexpr float INCLINATION_MIN_DEG = 0.0F;
constexpr float INCLINATION_MAX_DEG = 180.0F;

constexpr uint16_t BASE_MIN_PULSE_US = 500;
constexpr uint16_t BASE_MAX_PULSE_US = 2500;
constexpr uint16_t INCLINATION_MIN_PULSE_US = 500;
constexpr uint16_t INCLINATION_MAX_PULSE_US = 2500;

// Legacy fallback center. Normal operation uses calibrated MOVEABS commands
// generated from config/calibration/angular_stage.toml.
constexpr float BASE_FALLBACK_CENTER_DEG = 90.0F;
constexpr float INCLINATION_FALLBACK_CENTER_DEG = 92.0F;

// -----------------------------------------------------------------------------
// Timing and TMS safety
// -----------------------------------------------------------------------------
constexpr unsigned long SERVO_SETTLING_TIME_MS = 700;
constexpr unsigned long TMS_TRIGGER_PULSE_MS = 20;
constexpr bool TMS_TRIGGER_ACTIVE_HIGH = true;

// Keep this false until the TMS trigger voltage, isolation, and polarity have
// been verified for the selected Arduino board.
constexpr bool ENABLE_TMS_TRIGGER = false;

// -----------------------------------------------------------------------------
// Serial input
// -----------------------------------------------------------------------------
constexpr size_t COMMAND_BUFFER_SIZE = 64;
char commandBuffer[COMMAND_BUFFER_SIZE];
size_t commandLength = 0;
bool discardingOversizedCommand = false;

Servo baseServo;
Servo inclinationServo;


uint16_t degreesToPulse(
    float degrees,
    float minimumDegrees,
    float maximumDegrees,
    uint16_t minimumPulse,
    uint16_t maximumPulse) {
  const float fraction =
      (degrees - minimumDegrees) / (maximumDegrees - minimumDegrees);
  return static_cast<uint16_t>(
      lroundf(minimumPulse + fraction * (maximumPulse - minimumPulse)));
}


bool isWithinLimits(float baseDegrees, float inclinationDegrees) {
  return isfinite(baseDegrees) && isfinite(inclinationDegrees) &&
         baseDegrees >= BASE_MIN_DEG && baseDegrees <= BASE_MAX_DEG &&
         inclinationDegrees >= INCLINATION_MIN_DEG &&
         inclinationDegrees <= INCLINATION_MAX_DEG;
}


void moveServos(float baseDegrees, float inclinationDegrees) {
  if (!isWithinLimits(baseDegrees, inclinationDegrees)) {
    Serial.println(F("MOVE_ERROR,OUT_OF_RANGE"));
    return;
  }

  baseServo.writeMicroseconds(degreesToPulse(
      baseDegrees,
      BASE_MIN_DEG,
      BASE_MAX_DEG,
      BASE_MIN_PULSE_US,
      BASE_MAX_PULSE_US));
  inclinationServo.writeMicroseconds(degreesToPulse(
      inclinationDegrees,
      INCLINATION_MIN_DEG,
      INCLINATION_MAX_DEG,
      INCLINATION_MIN_PULSE_US,
      INCLINATION_MAX_PULSE_US));

  delay(SERVO_SETTLING_TIME_MS);

  Serial.print(F("MOVED,"));
  Serial.print(baseDegrees, 3);
  Serial.print(',');
  Serial.println(inclinationDegrees, 3);
}


void moveToFallbackCenter() {
  moveServos(BASE_FALLBACK_CENTER_DEG, INCLINATION_FALLBACK_CENTER_DEG);
  Serial.print(F("CENTERED,"));
  Serial.print(BASE_FALLBACK_CENTER_DEG, 3);
  Serial.print(',');
  Serial.println(INCLINATION_FALLBACK_CENTER_DEG, 3);
  Serial.println(F("SERVOS_OK"));
}


void writeTrigger(bool active) {
  const bool outputHigh = active == TMS_TRIGGER_ACTIVE_HIGH;
  digitalWrite(TMS_TRIGGER_PIN, outputHigh ? HIGH : LOW);
}


void fireTms() {
  if (!ENABLE_TMS_TRIGGER) {
    Serial.println(F("FIRE_ERROR,DISABLED"));
    return;
  }

  Serial.println(F("FIRING"));
  writeTrigger(true);
  delay(TMS_TRIGGER_PULSE_MS);
  writeTrigger(false);
  Serial.println(F("FIRE_DONE"));
}


bool parseFloatStrict(char *text, float &value) {
  char *end = nullptr;
  value = static_cast<float>(strtod(text, &end));
  return end != text && *end == '\0' && isfinite(value);
}


void handleMoveCommand(char *command) {
  char *baseText = command + strlen("MOVEABS,");
  char *separator = strchr(baseText, ',');
  if (separator == nullptr || strchr(separator + 1, ',') != nullptr) {
    Serial.println(F("MOVE_ERROR,FORMAT"));
    return;
  }

  *separator = '\0';
  char *inclinationText = separator + 1;
  float baseDegrees = 0.0F;
  float inclinationDegrees = 0.0F;
  if (!parseFloatStrict(baseText, baseDegrees) ||
      !parseFloatStrict(inclinationText, inclinationDegrees)) {
    Serial.println(F("MOVE_ERROR,INVALID_NUMBER"));
    return;
  }

  moveServos(baseDegrees, inclinationDegrees);
}


void handleCommand(char *command) {
  if (strcmp(command, "PING") == 0) {
    Serial.println(F("PONG"));
  } else if (strcmp(command, "CENTER") == 0) {
    moveToFallbackCenter();
  } else if (strcmp(command, "FIRE") == 0) {
    fireTms();
  } else if (strncmp(command, "MOVEABS,", strlen("MOVEABS,")) == 0) {
    handleMoveCommand(command);
  } else if (command[0] != '\0') {
    Serial.println(F("COMMAND_ERROR,UNKNOWN"));
  }
}


void setup() {
  Serial.begin(115200);

  baseServo.attach(BASE_SERVO_PIN, BASE_MIN_PULSE_US, BASE_MAX_PULSE_US);
  inclinationServo.attach(
      INCLINATION_SERVO_PIN,
      INCLINATION_MIN_PULSE_US,
      INCLINATION_MAX_PULSE_US);

  pinMode(TMS_TRIGGER_PIN, OUTPUT);
  writeTrigger(false);

  // The host sends the calibrated center explicitly. Startup therefore does
  // not move either servo.
  Serial.println(F("ARDUINO_READY"));
}


void loop() {
  while (Serial.available() > 0) {
    const char incoming = static_cast<char>(Serial.read());

    if (incoming == '\n') {
      if (!discardingOversizedCommand) {
        commandBuffer[commandLength] = '\0';
        handleCommand(commandBuffer);
      }
      commandLength = 0;
      discardingOversizedCommand = false;
      continue;
    }

    if (incoming == '\r') {
      continue;
    }

    if (discardingOversizedCommand) {
      continue;
    }

    if (commandLength + 1 >= COMMAND_BUFFER_SIZE) {
      commandLength = 0;
      discardingOversizedCommand = true;
      Serial.println(F("COMMAND_ERROR,TOO_LONG"));
      continue;
    }

    commandBuffer[commandLength++] = incoming;
  }
}
