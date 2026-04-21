"""
serial_comm/protocol.py — ECP205 serial protocol: parsing and command builders.

Firmware → PC (responses):
    DATA:<t_ms>:<a1>:<a2>:<a3>:<iq>\n   (iq = commanded current in A)
    ERR:<message>\n
    READY\n

PC → Firmware (commands):
    START\n
    STOP\n
    AMP:<value_A>\n   (peak current amplitude, 0 – MOTOR_CURRENT_LIMIT)
    FREQ:<value_Hz>\n
"""

from __future__ import annotations


def parse_data(payload: str) -> tuple[float, float, float, float, float] | None:
    """Parse the payload of a DATA: frame.

    *payload* is the string after the "DATA:" prefix, e.g.
    "12345:1.234:2.345:3.456:0.500"

    Returns (t_ms, a1_rad, a2_rad, a3_rad, iq_A) or None on error.
    """
    parts = payload.split(":")
    if len(parts) != 5:
        return None
    try:
        return (
            float(parts[0]),
            float(parts[1]),
            float(parts[2]),
            float(parts[3]),
            float(parts[4]),
        )
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Command builders — return ready-to-send strings (newline included)
# ---------------------------------------------------------------------------

def cmd_start() -> str:
    return "START\n"


def cmd_stop() -> str:
    return "STOP\n"


def cmd_amp(amps: float) -> str:
    return f"AMP:{amps:.2f}\n"


def cmd_freq(hz: float) -> str:
    return f"FREQ:{hz:.2f}\n"
