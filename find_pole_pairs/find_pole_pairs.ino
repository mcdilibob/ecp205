// =============================================================================
// ECP205 — Pole Pair Detection Utility
// VBCores VB32G4 (STM32G474RE) on BLDC Driver Board
//
// Rotates the motor open-loop through a known electrical angle and measures
// the mechanical rotation via Hall sensors to compute pole pairs.
//
// Formula:  pole_pairs = electrical_revolutions / mechanical_revolutions
//
// Required libraries: same as main firmware (SimpleFOC, VBCoreG4)
//
// Usage:
//   1. Upload this sketch
//   2. Open Serial Monitor at 115200 baud
//   3. Motor will rotate slowly; watch serial output for result
//   4. Update MOTOR_POLE_PAIRS in config.h with the printed value
// =============================================================================

#include <VBCoreG4_arduino_system.h>
#include <SimpleFOC.h>
#include "config.h"

// --- SimpleFOC objects -------------------------------------------------------
// Start with an initial guess of pole pairs (will be overridden)
HallSensor hall(PIN_HALL_A, PIN_HALL_B, PIN_HALL_C, 7);

void doA() { hall.handleA(); }
void doB() { hall.handleB(); }
void doC() { hall.handleC(); }

BLDCDriver3PWM driver(PIN_PWM_A, PIN_PWM_B, PIN_PWM_C);
BLDCMotor      motor(7);  // initial pole pairs — doesn't matter for open-loop

// -----------------------------------------------------------------------------

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("\n=== ECP205 Pole Pair Detection ===\n");

    // Bootstrap / enable pins
    pinMode(PIN_PULL_HI1, OUTPUT); digitalWrite(PIN_PULL_HI1, HIGH);
    pinMode(PIN_PULL_HI2, OUTPUT); digitalWrite(PIN_PULL_HI2, HIGH);
    pinMode(PIN_PULL_HI3, OUTPUT); digitalWrite(PIN_PULL_HI3, HIGH);
    pinMode(PIN_EN_GATE, OUTPUT);  digitalWrite(PIN_EN_GATE, HIGH);
    delay(10);

    // Hall sensor
    hall.init();
    hall.enableInterrupts(doA, doB, doC);
    Serial.println("[1/4] Hall sensor initialized");

    // Driver
    driver.voltage_power_supply = SUPPLY_VOLTAGE;
    driver.init();
    Serial.println("[2/4] Driver initialized");

    // Motor — open-loop mode
    motor.linkSensor(&hall);
    motor.linkDriver(&driver);
    motor.controller = MotionControlType::angle_openloop;
    motor.voltage_limit = 3.0;  // low voltage for slow, safe rotation
    motor.init();
    Serial.println("[3/4] Motor initialized in open-loop mode");

}

void loop() {
    // Nothing — detection runs once in setup()
}
