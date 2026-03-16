"""
serial_worker.py — Background QThread for non-blocking serial I/O.

Reads lines from the MCU, parses DATA / ERR frames, and emits Qt signals.
Commands are sent thread-safely via send_command() — they are queued and
written from the worker thread, never blocking the main thread.

Data is batched: the worker accumulates samples and emits them together
every BATCH_SIZE samples (~50 ms at 200 Hz), reducing Qt signal overhead
from 200/s to ~20/s.
"""

from __future__ import annotations

import collections
import threading

import numpy as np
import serial
from PyQt6.QtCore import QThread, pyqtSignal

# Emit one signal per this many samples (200 Hz / 10 = 20 Hz signal rate)
_BATCH_SIZE = 10


class SerialWorker(QThread):
    # Emitted in batches: five equal-length 1-D float64 arrays
    #   (t_ms, angle1_deg, angle2_deg, angle3_deg, vq_V)
    data_received = pyqtSignal(object, object, object, object, object)

    # Emitted when an ERR: frame arrives or a serial exception occurs
    error_occurred = pyqtSignal(str)

    # Emitted when the connection opens / closes
    connected    = pyqtSignal()
    disconnected = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._port  = ""
        self._baud  = 230400
        self._ser: serial.Serial | None = None
        self._stop_event   = threading.Event()
        # Thread-safe command queue: main thread enqueues, worker dequeues
        self._cmd_queue: collections.deque[str] = collections.deque()

    # -------------------------------------------------------------------------
    # Public API (safe to call from any thread)
    # -------------------------------------------------------------------------

    def open(self, port: str, baud: int = 230400) -> None:
        self._port = port
        self._baud = baud
        self._stop_event.clear()
        self.start()

    def close(self) -> None:
        self._stop_event.set()
        self.wait(2000)

    def send_command(self, cmd: str) -> None:
        """Enqueue a command; the worker thread writes it to serial."""
        if not cmd.endswith("\n"):
            cmd += "\n"
        self._cmd_queue.append(cmd)

    # -------------------------------------------------------------------------
    # Thread body
    # -------------------------------------------------------------------------

    def run(self) -> None:
        try:
            self._ser = serial.Serial(
                port=self._port,
                baudrate=self._baud,
                timeout=0.1,
            )
        except serial.SerialException as exc:
            self.error_occurred.emit(f"Cannot open {self._port}: {exc}")
            return

        self.connected.emit()

        # Pre-allocate batch arrays
        batch_t  = np.empty(_BATCH_SIZE, dtype=np.float64)
        batch_a1 = np.empty(_BATCH_SIZE, dtype=np.float64)
        batch_a2 = np.empty(_BATCH_SIZE, dtype=np.float64)
        batch_a3 = np.empty(_BATCH_SIZE, dtype=np.float64)
        batch_vq = np.empty(_BATCH_SIZE, dtype=np.float64)
        batch_i  = 0

        try:
            while not self._stop_event.is_set():
                # --- Drain outgoing command queue (non-blocking) ---
                while self._cmd_queue:
                    try:
                        self._ser.write(self._cmd_queue.popleft().encode("utf-8"))
                    except serial.SerialException as exc:
                        self.error_occurred.emit(str(exc))

                # --- Read one line ---
                line = self._ser.readline()
                if not line:
                    continue

                text = line.decode("utf-8", errors="replace").strip()

                if text.startswith("DATA:"):
                    parsed = self._parse_data(text[5:])
                    if parsed is not None:
                        t, a1, a2, a3, vq = parsed
                        batch_t [batch_i] = t
                        batch_a1[batch_i] = a1
                        batch_a2[batch_i] = a2
                        batch_a3[batch_i] = a3
                        batch_vq[batch_i] = vq
                        batch_i += 1

                        if batch_i == _BATCH_SIZE:
                            self.data_received.emit(
                                batch_t.copy(), batch_a1.copy(),
                                batch_a2.copy(), batch_a3.copy(),
                                batch_vq.copy(),
                            )
                            batch_i = 0

                elif text.startswith("ERR:"):
                    self.error_occurred.emit(text[4:])

        except serial.SerialException as exc:
            if not self._stop_event.is_set():
                self.error_occurred.emit(str(exc))
        finally:
            self._ser.close()
            self._ser = None
            self.disconnected.emit()

    # -------------------------------------------------------------------------

    @staticmethod
    def _parse_data(payload: str) -> tuple | None:
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
