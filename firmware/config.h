#pragma once

// =============================================================================
// ECP205 Torsional Plant — Firmware Configuration
// VBCores VB32G4 (STM32G474RE) on BLDC Driver Board
// =============================================================================

// --- Motor PWM (BLDCDriver3PWM) ---
#define PIN_PWM_A    PA8
#define PIN_PWM_B    PA9
#define PIN_PWM_C    PA10

// --- Gate driver ---
#define PIN_EN_GATE  PB3
#define PIN_PULL_HI1 PB13   // complementary/bootstrap — keep HIGH
#define PIN_PULL_HI2 PB14
#define PIN_PULL_HI3 PB15

// --- Inline current sense (ACS711, 45 mV/A) ---
#define PIN_CS_A     PC1
#define PIN_CS_B     PC2
#define PIN_CS_C     PC3
#define CURRENT_SENSE_MV_A  45.0f

// --- Hall sensors — *** VERIFY FROM HARDWARE SCHEMATIC *** ---
#define PIN_HALL_A   PB6
#define PIN_HALL_B   PC7
#define PIN_HALL_C   PC8

// --- I2C bus (ADS1115) ---
#define PIN_SDA      PB_7_ALT1
#define PIN_SCL      PC6

// --- ADS1115 (I2C address 0x48, ADDR pin to GND) ---
#define ADS_I2C_ADDR       0x48
#define ADS_CH_DISK1       0    // AIN0 → AS5600 on disk 1
#define ADS_CH_DISK2       1    // AIN1 → AS5600 on disk 2
#define ADS_CH_DISK3       2    // AIN2 → AS5600 on disk 3
// AS5600 supply voltage — update if powered from 3.3 V
#define AS5600_VCC         5.0f

// Encoder direction inversion (true = reverse direction)
#define ENCODER_INVERT_DISK1   true
#define ENCODER_INVERT_DISK2   true    // disk 2 mounted in reverse
#define ENCODER_INVERT_DISK3   false

// --- Motor parameters — *** FILL IN FROM MOTOR SPEC *** ---
#define MOTOR_POLE_PAIRS    11       // update to actual pole pair count
#define SUPPLY_VOLTAGE      12.0f   // update to actual supply voltage (V)
#define MOTOR_VOLTAGE_LIMIT 10.0f   // max output Vq from current PI (V) — keep as voltage rail guard

// Motor electrical parameters (required for foc_current mode)
// PHASE_RESISTANCE: measure phase-to-phase with multimeter, divide by 2
// MOTOR_KV: from motor datasheet (RPM/V no-load); comment out if unknown
#define PHASE_RESISTANCE   1.5f     // Ω  *** MEASURE WITH MULTIMETER ***
#define MOTOR_KV           110      // RPM/V *** FROM MOTOR DATASHEET ***

// ACS711 inline current sense (45 mV/A at 5 V supply)
// SimpleFOC InlineCurrentSense(shunt_R, gain, phA, phB, phC)
// Formula: I = V_adc / (shunt_R * gain)  →  shunt_R * gain = 0.045 V/A
#define CURRENT_SENSE_R    0.045f   // effective Ω encoding sensor sensitivity
#define CURRENT_SENSE_GAIN 1.0f     // no external amplifier

// Maximum commanded current (replaces voltage limit as excitation cap)
#define MOTOR_CURRENT_LIMIT 3.0f    // A  — set below motor stall current

// --- Control loop rates ---
#define FOC_RATE_HZ        1000     // FOC interrupt frequency (Hz)
#define DATA_RATE_HZ       200       // serial data output rate (Hz)

// --- Serial ---
#define SERIAL_BAUD        500000
