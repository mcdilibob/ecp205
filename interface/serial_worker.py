"""
serial_worker.py — Background QThread for non-blocking serial I/O.

Reads lines from the MCU, parses DATA / ERR frames, and emits Qt signals.
Commands are sent from the main thread via send_command().
"""

from __future__ import annotations

import threading

import serial
from PyQt6.QtCore import QThread, pyqtSignal


class SerialWorker(QThread):
    # Emitted for every valid DATA frame:
    #   (t_ms, angle1_deg, angle2_deg, angle3_deg, vq_V)
    data_received = pyqtSignal(float, float, float, float, float)

    # Emitted when an ERR: frame arrives or a serial exception occurs
    error_occurred = pyqtSignal(str)

    # Emitted when the connection opens / closes
    connected = pyqtSignal()
    disconnected = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._port: str = ""
        self._baud: int = 230400
        self._ser: serial.Serial | None = None
        self._stop_event = threading.Event()

    # -------------------------------------------------------------------------
    # Public API (call from main thread)
    # -------------------------------------------------------------------------

    def open(self, port: str, baud: int = 230400) -> None:
        """Configure and start the worker thread."""
        self._port = port
        self._baud = baud
        self._stop_event.clear()
        self.start()

    def close(self) -> None:
        """Signal the worker to stop and wait for it to finish."""
        self._stop_event.set()
        self.wait(2000)

    def send_command(self, cmd: str) -> None:
        """Send a command string to the MCU (adds \\n if missing)."""
        if self._ser and self._ser.is_open:
            if not cmd.endswith("\n"):
                cmd += "\n"
            try:
                self._ser.write(cmd.encode("utf-8"))
            except serial.SerialException as exc:
                self.error_occurred.emit(str(exc))

    # -------------------------------------------------------------------------
    # Thread body
    # -------------------------------------------------------------------------

    def run(self) -> None:
        try:
            self._ser = serial.Serial(
                port=self._port,
                baudrate=self._baud,
                timeout=0.1,  # short timeout so we can check _stop_event
            )
        except serial.SerialException as exc:
            self.error_occurred.emit(f"Cannot open {self._port}: {exc}")
            return

        self.connected.emit()

        try:
            while not self._stop_event.is_set():
                line = self._ser.readline()
                if not line:
                    continue

                text = line.decode("utf-8", errors="replace").strip()
                self._parse_line(text)
        except serial.SerialException as exc:
            if not self._stop_event.is_set():
                self.error_occurred.emit(str(exc))
        finally:
            self._ser.close()
            self._ser = None
            self.disconnected.emit()

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _parse_line(self, text: str) -> None:
        if text.startswith("DATA:"):
            self._parse_data(text[5:])
        elif text.startswith("ERR:"):
            self.error_occurred.emit(text[4:])
        # READY and other informational messages are silently ignored

    def _parse_data(self, payload: str) -> None:
        # payload format: <ms>:<d1>:<d2>:<d3>:<vq>
        parts = payload.split(":")
        if len(parts) != 5:
            return
        try:
            t_ms = float(parts[0])
            a1   = float(parts[1])
            a2   = float(parts[2])
            a3   = float(parts[3])
            vq   = float(parts[4])
        except ValueError:
            return
        self.data_received.emit(t_ms, a1, a2, a3, vq)
