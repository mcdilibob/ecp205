"""
emulator.py — ECP205 plant emulator over a virtual serial port (PTY).

Creates a pseudo-terminal pair; prints the slave device name (e.g. /dev/pts/3)
so you can enter it in the GUI as the serial port.

Simulated dynamics (very simplified, continuous-time):
  Disk 1 — direct drive, small inertia:  fast response to Vq
  Disk 2 — coupled through spring:       moderate lag & attenuation
  Disk 3 — end of chain:                 more lag & attenuation

Each disk angle is integrated from a velocity that responds to Vq
with first-order lag, giving realistic-looking phase shifts on a Bode plot.

Usage:
    /home/pda/ecp205/interface/.venv/bin/python emulator.py
    # note the printed /dev/pts/N, enter it in the GUI, baud 230400
"""

from __future__ import annotations

import math
import os
import pty
import select
import sys
import time
import tty

# ---------------------------------------------------------------------------
# Plant model parameters
# ---------------------------------------------------------------------------
# Each disk: velocity v follows Vq through a first-order lag  dv/dt = (K*Vq - v) / tau
# Angle integrates velocity.  Units are arbitrary (degrees/s).

_DISKS = [
    {"K": 30.0,  "tau": 0.05},   # disk 1: fast, high gain
    {"K": 18.0,  "tau": 0.18},   # disk 2: moderate
    {"K":  8.0,  "tau": 0.40},   # disk 3: slow, attenuated
]

DATA_RATE_HZ = 200
DT           = 1.0 / DATA_RATE_HZ


def main() -> None:
    # Create PTY pair
    master_fd, slave_fd = pty.openpty()
    slave_name = os.ttyname(slave_fd)
    tty.setraw(master_fd)

    print(f"[emulator] Virtual serial port: \033[1;32m{slave_name}\033[0m")
    print( "[emulator] Connect the GUI to that port at baud 230400.")
    print( "[emulator] Press Ctrl+C to stop.\n")

    # Send READY
    os.write(master_fd, b"READY\n")

    # State
    running   = False
    amplitude = 1.0    # V
    frequency = 1.0    # Hz

    velocities = [0.0, 0.0, 0.0]
    angles     = [0.0, 0.0, 0.0]

    cmd_buf = bytearray()
    t0 = time.monotonic()
    next_tick = t0

    try:
        while True:
            now = time.monotonic()

            # --- Read any incoming bytes from GUI (non-blocking) ---
            r, _, _ = select.select([master_fd], [], [], 0)
            if r:
                data = os.read(master_fd, 256)
                cmd_buf.extend(data)
                while b"\n" in cmd_buf:
                    idx = cmd_buf.index(b"\n")
                    line = cmd_buf[:idx].decode("utf-8", errors="replace").strip()
                    cmd_buf = cmd_buf[idx + 1:]
                    running, amplitude, frequency = _handle(
                        line, running, amplitude, frequency
                    )

            # --- Physics step + transmit at DATA_RATE_HZ ---
            if now >= next_tick:
                next_tick += DT

                t = now - t0
                vq = amplitude * math.sin(2 * math.pi * frequency * t) if running else 0.0

                for i, disk in enumerate(_DISKS):
                    dv = (disk["K"] * vq - velocities[i]) / disk["tau"]
                    velocities[i] += dv * DT
                    angles[i]      = (angles[i] + velocities[i] * DT) % 360.0

                ts_ms = int((now - t0) * 1000)
                line  = (
                    f"DATA:{ts_ms}"
                    f":{angles[0]:.2f}"
                    f":{angles[1]:.2f}"
                    f":{angles[2]:.2f}"
                    f":{vq:.3f}\n"
                )
                os.write(master_fd, line.encode())

                # Pace: sleep until next tick
                sleep = next_tick - time.monotonic()
                if sleep > 0:
                    time.sleep(sleep)

    except KeyboardInterrupt:
        print("\n[emulator] Stopped.")
    finally:
        os.close(master_fd)
        os.close(slave_fd)


# ---------------------------------------------------------------------------

def _handle(line: str, running: bool, amplitude: float, frequency: float):
    line = line.strip()
    if line == "START":
        running = True
        print(f"[emulator] START  amp={amplitude:.2f} V  freq={frequency:.2f} Hz")
    elif line == "STOP":
        running = False
        print("[emulator] STOP")
    elif line.startswith("AMP:"):
        try:
            amplitude = float(line[4:])
            print(f"[emulator] amplitude → {amplitude:.2f} V")
        except ValueError:
            pass
    elif line.startswith("FREQ:"):
        try:
            frequency = float(line[5:])
            print(f"[emulator] frequency → {frequency:.2f} Hz")
        except ValueError:
            pass
    return running, amplitude, frequency



if __name__ == "__main__":
    main()
