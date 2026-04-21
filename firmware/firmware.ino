// =============================================================================
// ECP205 Torsional Plant — Main Firmware
// VBCores VB32G4 (STM32G474RE) on BLDC Driver Board
//
// Required Arduino libraries:
//   - VBCoreG4 board package (via Boards Manager)
//     URL: https://raw.githubusercontent.com/VBCores/VBCoreG4_arduino_system/main/package_vbcores_index.json
//   - Simple FOC  (Library Manager: "Simple FOC")
//   - Adafruit ADS1X15  (Library Manager: "Adafruit ADS1X15")
//   - Adafruit BusIO    (auto-installed as dependency)
//
// Before first use:
//   1. Verify MOTOR_POLE_PAIRS and SUPPLY_VOLTAGE in config.h
//   2. Verify PIN_HALL_A/B/C in config.h from the BLDC board schematic
//   3. Verify ADS_CH_DISKx channel assignment matches physical wiring
// =============================================================================

#include <VBCoreG4_arduino_system.h>
#include <SimpleFOC.h>

#include "config.h"
#include "encoder_reader.h"
#include "serial_comm.h"

// --- Global state (shared with serial_comm.h) --------------------------------
volatile bool  g_running   = false;
volatile float g_amplitude = 1.0f;   // A (commanded peak current)
volatile float g_frequency = 1.0f;   // Hz

// --- SimpleFOC objects -------------------------------------------------------
HallSensor hall(PIN_HALL_A, PIN_HALL_B, PIN_HALL_C, MOTOR_POLE_PAIRS);

void doA() { hall.handleA(); }
void doB() { hall.handleB(); }
void doC() { hall.handleC(); }

BLDCDriver3PWM    driver(PIN_PWM_A, PIN_PWM_B, PIN_PWM_C);
BLDCMotor         motor(MOTOR_POLE_PAIRS);
InlineCurrentSense current_sense(45.0, PIN_CS_A, PIN_CS_B, PIN_CS_C);

// --- Encoder reader ----------------------------------------------------------
EncoderReader encoders;

// --- FOC timer interrupt -----------------------------------------------------
HardwareTimer *foc_timer = nullptr;

void foc_isr() {
    motor.loopFOC();
}

// --- Setup -------------------------------------------------------------------
void setup() {
    Serial.begin(SERIAL_BAUD);

    // Bootstrap / complementary enable lines — must be HIGH before driver init
    pinMode(PIN_PULL_HI1, OUTPUT); digitalWrite(PIN_PULL_HI1, HIGH);
    pinMode(PIN_PULL_HI2, OUTPUT); digitalWrite(PIN_PULL_HI2, HIGH);
    pinMode(PIN_PULL_HI3, OUTPUT); digitalWrite(PIN_PULL_HI3, HIGH);

    // Enable gate driver
    pinMode(PIN_EN_GATE, OUTPUT);
    digitalWrite(PIN_EN_GATE, HIGH);
    delay(10);

    // Hall sensor
    hall.init();
    hall.enableInterrupts(doA, doB, doC);

    // BLDC driver
    driver.voltage_power_supply = SUPPLY_VOLTAGE;
    driver.pwm_frequency = 25000;  // 25 kHz — above audible range
    if (!driver.init()) {
        serial_send_error("driver init failed");
        while (1) {}
    }

    // BLDC motor — FOC current mode (Iq = target, torque ∝ Iq)
    motor.linkSensor(&hall);
    motor.linkDriver(&driver);
    motor.torque_controller = TorqueControlType::foc_current;
    motor.controller        = MotionControlType::torque;
//   motor.phase_resistance  = PHASE_RESISTANCE;
//    motor.KV_rating         = MOTOR_KV;
    motor.voltage_limit     = MOTOR_VOLTAGE_LIMIT;  // output voltage cap for current PI
    motor.current_limit     = MOTOR_CURRENT_LIMIT;
    motor.velocity_limit    = 200.0f;  // rad/s — safety cap

    motor.init();

    // Current sense must be linked after driver.init() and motor.init()
    current_sense.linkDriver(&driver);
    if (!current_sense.init()) {
        serial_send_error("current sense init failed");
        // Continue — motor can run without current sense (falls back to voltage mode internally)
    }
    motor.linkCurrentSense(&current_sense);

    motor.initFOC();

    // ADS1115 + AS5600 encoders
    if (!encoders.begin()) {
        serial_send_error("ADS1115 not found at 0x48");
        // Continue without encoders so motor can still be tested
    }

    // FOC timer interrupt at FOC_RATE_HZ
    foc_timer = new HardwareTimer(TIM7);
    foc_timer->pause();
    foc_timer->setOverflow(FOC_RATE_HZ, HERTZ_FORMAT);
    foc_timer->attachInterrupt(foc_isr);
    foc_timer->refresh();
    foc_timer->resume();

    Serial.println("READY");
}

// --- Main loop ---------------------------------------------------------------
// Approximate cadence: 3× ADS1115 reads at 860 SPS ≈ 3.5 ms + serial overhead
// → effective loop rate ~250 Hz; data transmit gated to DATA_RATE_HZ.

static uint32_t last_data_ms = 0;

void loop() {
    // 1. Parse incoming serial commands
    serial_comm_update();

    // 2. Read disk angles from ADS1115
    float a1, a2, a3;
    encoders.readAll(a1, a2, a3);

    // 3. Compute sine wave current target (Iq)
    uint32_t now_ms = millis();
    float iq = 0.0f;
    if (g_running && g_amplitude > 0.0f) {
        float t = now_ms * 1e-3f;
        iq = g_amplitude * sinf(TWO_PI * g_frequency * t);
    }

    // 4. Apply to motor (SimpleFOC foc_current mode: target = Iq in A)
    motor.move(iq);

    // 5. Transmit data at DATA_RATE_HZ
    if ((now_ms - last_data_ms) >= (1000u / DATA_RATE_HZ)) {
        last_data_ms = now_ms;
        serial_send_data(now_ms, a1, a2, a3, iq);
    }
}
