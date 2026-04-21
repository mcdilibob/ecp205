#pragma once

#include <Arduino.h>
#include "config.h"

// =============================================================================
// Serial communication — command parser
//
// PC → MCU protocol (text, newline-terminated):
//   AMP:<value>\n    set sine wave amplitude in amps (0.0 – MOTOR_CURRENT_LIMIT)
//   FREQ:<value>\n   set sine wave frequency in Hz  (0.0 – 20.0)
//   START\n          enable motor output
//   STOP\n           disable motor output
//
// MCU → PC protocol:
//   DATA:<ms>:<d1>:<d2>:<d3>:<iq>\n   sent at DATA_RATE_HZ  (iq in A)
//   ERR:<message>\n                   on error (e.g. ADS not found)
// =============================================================================

// These are written from serial_comm_update() and read by the main sketch.
// Declared extern so the main sketch can also read/write them.
extern volatile bool  g_running;
extern volatile float g_amplitude;
extern volatile float g_frequency;

// Call once per loop() iteration
inline void serial_comm_update() {
    static char buf[32];
    static uint8_t idx = 0;

    while (Serial.available()) {
        char c = (char)Serial.read();
        if (c == '\r') continue;  // ignore CR in CRLF sequences
        if (c == '\n') {
            buf[idx] = '\0';

            if (strcmp(buf, "START") == 0) {
                g_running = true;
            } else if (strcmp(buf, "STOP") == 0) {
                g_running = false;
            } else if (strncmp(buf, "AMP:", 4) == 0) {
                float v = atof(buf + 4);
                if (v >= 0.0f && v <= MOTOR_CURRENT_LIMIT)
                    g_amplitude = v;
            } else if (strncmp(buf, "FREQ:", 5) == 0) {
                float f = atof(buf + 5);
                if (f >= 0.0f && f <= 20.0f)
                    g_frequency = f;
            }

            idx = 0;
        } else if (idx < 31) {
            buf[idx++] = c;
        }
    }
}

// Send one DATA frame
inline void serial_send_data(uint32_t ts_ms,
                              float a1, float a2, float a3,
                              float u) {
    Serial.print("DATA:");
    Serial.print(ts_ms);
    Serial.print(':');
    Serial.print(a1, 4);
    Serial.print(':');
    Serial.print(a2, 4);
    Serial.print(':');
    Serial.print(a3, 4);
    Serial.print(':');
    Serial.println(u, 4);
}

// Send an error string
inline void serial_send_error(const char* msg) {
    Serial.print("ERR:");
    Serial.println(msg);
}
