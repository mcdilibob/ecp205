#pragma once

#include <Wire.h>
#include <Adafruit_ADS1X15.h>
#include "config.h"

// =============================================================================
// EncoderReader
// Reads three AS5600 magnetic encoders (analog output) via ADS1115 ADC.
//
// Wiring: AS5600 OUT pin → ADS1115 AIN0/1/2
//         AS5600 MODE pin → VCC  (enables analog output mode)
//         AS5600 DIR  pin → GND  (clockwise = increasing angle)
//
// Gain GAIN_ONE: ±4.096 V range, 0.125 mV per LSB.
// At 5 V supply the AS5600 output spans 0–5 V → 0–2π rad.
// If AS5600 is powered from 3.3 V, update AS5600_VCC in config.h.
// =============================================================================

class EncoderReader {
public:
    bool begin() {
        Wire.setSDA(PIN_SDA);
        Wire.setSCL(PIN_SCL);
        Wire.begin();

        if (!_ads.begin()) {
            return false;  // ADS1115 not found on I2C bus
        }

//        _ads.setGain(GAIN_ONE);               // ±4.096 V, 0.125 mV/bit
        _ads.setDataRate(RATE_ADS1115_860SPS); // maximum sample rate

        // Calibrate: record initial angles as zero offsets
        delay(100);
        _offsets[0] = _readAngleRaw(ADS_CH_DISK1);
        _offsets[1] = _readAngleRaw(ADS_CH_DISK2);
        _offsets[2] = _readAngleRaw(ADS_CH_DISK3);

        // Configure inversion from config.h
        _invert[0] = ENCODER_INVERT_DISK1;
        _invert[1] = ENCODER_INVERT_DISK2;
        _invert[2] = ENCODER_INVERT_DISK3;

        return true;
    }

    // Returns angle in radians [-π, π) with calibration and inversion applied
    // channel: ADS_CH_DISK1 / ADS_CH_DISK2 / ADS_CH_DISK3
    float readAngle(uint8_t channel) {
        float angle = _readAngleRaw(channel);

        // Apply zero offset (assumes channel == index 0/1/2)
        angle -= _offsets[channel];

        // Apply direction inversion if configured
        if (_invert[channel]) {
            angle = -angle;
        }

        // Wrap to [-π, π)
        while (angle < -PI)  angle += TWO_PI;
        while (angle >= PI)  angle -= TWO_PI;

        return angle;
    }

    // Read all three disks in one call; results written to a1/a2/a3 (radians)
    void readAll(float &a1, float &a2, float &a3) {
        a1 = readAngle(ADS_CH_DISK1);
        a2 = readAngle(ADS_CH_DISK2);
        a3 = readAngle(ADS_CH_DISK3);
    }

private:
    Adafruit_ADS1115 _ads;
    float _offsets[3] = {0.0f, 0.0f, 0.0f};
    bool  _invert[3]  = {false, false, false};

    // Read raw angle in radians without calibration or inversion.
    // Takes 3 ADC samples and returns the median to reject single-sample glitches.
    float _readAngleRaw(uint8_t channel) {
        float s[3];
        for (int i = 0; i < 3; i++) {
            int16_t raw = _ads.readADC_SingleEnded(channel);
            if (raw < 0) raw = 0;
            s[i] = (_ads.computeVolts(raw) / AS5600_VCC) * TWO_PI;
        }
        // Sort network for 3 elements → s[1] is the median
        if (s[0] > s[1]) { float t = s[0]; s[0] = s[1]; s[1] = t; }
        if (s[1] > s[2]) { float t = s[1]; s[1] = s[2]; s[2] = t; }
        if (s[0] > s[1]) { float t = s[0]; s[0] = s[1]; s[1] = t; }
        float angle = s[1];
        if (angle < 0.0f)    angle = 0.0f;
        if (angle > TWO_PI)  angle = TWO_PI;
        return angle;
    }
};
