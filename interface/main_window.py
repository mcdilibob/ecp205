"""
main_window.py — ECP205 GUI main window (PyQt6).

Layout:
  ┌─ connection bar ──────────────────────────────────────────────────┐
  │  Port [COM/ttyUSB ▼]  Baud [230400 ▼]  [Connect]  [Disconnect]   │
  ├─ plot ────────────────────────────────────────────────────────────┤
  │                  Real-time angle plot (3 disks + Vq)              │
  ├─ controls ────────────────────────────────────────────────────────┤
  │  Amplitude (V): [slider ──●──]  [spinbox]                         │
  │  Frequency (Hz): [slider ──●──]  [spinbox]                        │
  │  [START]   [STOP]   [Export CSV]                                  │
  └───────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import serial.tools.list_ports
from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from data_buffer import DataBuffer
from plot_widget import AnglePlotWidget
from serial_worker import SerialWorker


class MainWindow(QMainWindow):
    # Amplitude range (V)
    AMP_MIN  = 0.0
    AMP_MAX  = 10.0
    AMP_STEP = 0.1

    # Frequency range (Hz)
    FREQ_MIN  = 0.1
    FREQ_MAX  = 20.0
    FREQ_STEP = 0.1

    # Plot refresh rate
    PLOT_REFRESH_MS = 50   # 20 Hz repaint

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ECP205 — Frequency Response Tool")
        self.resize(1000, 650)

        self._worker = SerialWorker(self)
        self._buffer = DataBuffer(max_seconds=60.0, sample_rate_hz=200.0)
        self._connected = False

        # Debounce timer: sends AMP/FREQ command 200 ms after last slider move
        self._cmd_timer = QTimer(self)
        self._cmd_timer.setSingleShot(True)
        self._cmd_timer.setInterval(200)
        self._cmd_timer.timeout.connect(self._send_control_params)

        # Plot refresh timer
        self._plot_timer = QTimer(self)
        self._plot_timer.setInterval(self.PLOT_REFRESH_MS)
        self._plot_timer.timeout.connect(self._refresh_plot)

        self._build_ui()
        self._connect_signals()
        self._set_controls_enabled(False)

    # -------------------------------------------------------------------------
    # UI construction
    # -------------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(6)
        root.setContentsMargins(8, 8, 8, 8)

        root.addWidget(self._build_connection_bar())

        self._plot = AnglePlotWidget(window_seconds=10.0)
        root.addWidget(self._plot, stretch=1)

        root.addWidget(self._build_control_panel())

        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Disconnected")

    def _build_connection_bar(self) -> QGroupBox:
        box = QGroupBox("Serial Connection")
        layout = QHBoxLayout(box)

        layout.addWidget(QLabel("Port:"))
        self._port_combo = QComboBox()
        self._port_combo.setEditable(False)
        self._port_combo.setMinimumWidth(160)
        self._refresh_ports()
        layout.addWidget(self._port_combo)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self._refresh_ports)
        layout.addWidget(btn_refresh)

        layout.addWidget(QLabel("Baud:"))
        self._baud_combo = QComboBox()
        for b in ("230400", "115200", "57600"):
            self._baud_combo.addItem(b)
        layout.addWidget(self._baud_combo)

        self._btn_connect = QPushButton("Connect")
        self._btn_connect.clicked.connect(self._on_connect)
        layout.addWidget(self._btn_connect)

        self._btn_disconnect = QPushButton("Disconnect")
        self._btn_disconnect.setEnabled(False)
        self._btn_disconnect.clicked.connect(self._on_disconnect)
        layout.addWidget(self._btn_disconnect)

        layout.addStretch()
        return box

    def _build_control_panel(self) -> QGroupBox:
        box = QGroupBox("Motor Control")
        grid = QVBoxLayout(box)

        # Amplitude row
        amp_row = QHBoxLayout()
        amp_row.addWidget(QLabel("Amplitude (V):"))
        self._amp_slider = self._make_slider(
            self.AMP_MIN, self.AMP_MAX, self.AMP_STEP, initial=1.0
        )
        amp_row.addWidget(self._amp_slider, stretch=1)
        self._amp_spin = self._make_spinbox(
            self.AMP_MIN, self.AMP_MAX, self.AMP_STEP, initial=1.0
        )
        amp_row.addWidget(self._amp_spin)
        grid.addLayout(amp_row)

        # Frequency row
        freq_row = QHBoxLayout()
        freq_row.addWidget(QLabel("Frequency (Hz):"))
        self._freq_slider = self._make_slider(
            self.FREQ_MIN, self.FREQ_MAX, self.FREQ_STEP, initial=1.0
        )
        freq_row.addWidget(self._freq_slider, stretch=1)
        self._freq_spin = self._make_spinbox(
            self.FREQ_MIN, self.FREQ_MAX, self.FREQ_STEP, initial=1.0
        )
        freq_row.addWidget(self._freq_spin)
        grid.addLayout(freq_row)

        # Buttons row
        btn_row = QHBoxLayout()
        self._btn_start = QPushButton("START")
        self._btn_start.setStyleSheet("background:#2a7a2a; color:white; font-weight:bold;")
        self._btn_start.clicked.connect(self._on_start)
        btn_row.addWidget(self._btn_start)

        self._btn_stop = QPushButton("STOP")
        self._btn_stop.setStyleSheet("background:#7a2a2a; color:white; font-weight:bold;")
        self._btn_stop.clicked.connect(self._on_stop)
        btn_row.addWidget(self._btn_stop)

        btn_row.addStretch()

        self._btn_export = QPushButton("Export CSV")
        self._btn_export.clicked.connect(self._on_export)
        btn_row.addWidget(self._btn_export)

        self._btn_clear = QPushButton("Clear Buffer")
        self._btn_clear.clicked.connect(self._on_clear)
        btn_row.addWidget(self._btn_clear)

        grid.addLayout(btn_row)
        return box

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _make_slider(lo: float, hi: float, step: float, initial: float) -> QSlider:
        steps = round((hi - lo) / step)
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(0, steps)
        s.setValue(round((initial - lo) / step))
        return s

    @staticmethod
    def _make_spinbox(lo: float, hi: float, step: float, initial: float) -> QDoubleSpinBox:
        sb = QDoubleSpinBox()
        sb.setRange(lo, hi)
        sb.setSingleStep(step)
        sb.setDecimals(2)
        sb.setValue(initial)
        sb.setFixedWidth(80)
        return sb

    _DEFAULT_PORT = "/dev/ttyACM0"

    def _refresh_ports(self) -> None:
        self._port_combo.clear()
        ports = [p.device for p in serial.tools.list_ports.comports()]
        if self._DEFAULT_PORT not in ports:
            ports.insert(0, self._DEFAULT_PORT)
        for dev in ports:
            self._port_combo.addItem(dev)
        idx = self._port_combo.findText(self._DEFAULT_PORT)
        if idx >= 0:
            self._port_combo.setCurrentIndex(idx)

    def _set_controls_enabled(self, enabled: bool) -> None:
        for w in (
            self._btn_start, self._btn_stop,
            self._amp_slider, self._amp_spin,
            self._freq_slider, self._freq_spin,
            self._btn_export, self._btn_clear,
        ):
            w.setEnabled(enabled)

    def _amplitude(self) -> float:
        return self.AMP_MIN + self._amp_slider.value() * self.AMP_STEP

    def _frequency(self) -> float:
        return self.FREQ_MIN + self._freq_slider.value() * self.FREQ_STEP

    # -------------------------------------------------------------------------
    # Signal wiring
    # -------------------------------------------------------------------------

    def _connect_signals(self) -> None:
        # Serial worker
        self._worker.data_received.connect(self._on_data)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.connected.connect(self._on_connected)
        self._worker.disconnected.connect(self._on_disconnected)

        # Sliders ↔ spinboxes (keep in sync, debounce command)
        self._amp_slider.valueChanged.connect(self._on_amp_slider)
        self._amp_spin.valueChanged.connect(self._on_amp_spin)
        self._freq_slider.valueChanged.connect(self._on_freq_slider)
        self._freq_spin.valueChanged.connect(self._on_freq_spin)

    # -------------------------------------------------------------------------
    # Slots
    # -------------------------------------------------------------------------

    @pyqtSlot()
    def _on_connect(self) -> None:
        port = self._port_combo.currentText().strip()
        if not port:
            QMessageBox.warning(self, "No Port", "Select a serial port first.")
            return
        baud = int(self._baud_combo.currentText())
        self._worker.open(port, baud)

    @pyqtSlot()
    def _on_disconnect(self) -> None:
        self._worker.send_command("STOP")
        self._worker.close()

    @pyqtSlot()
    def _on_connected(self) -> None:
        self._connected = True
        self._btn_connect.setEnabled(False)
        self._btn_disconnect.setEnabled(True)
        self._set_controls_enabled(True)
        self._plot_timer.start()
        self._status_bar.showMessage(
            f"Connected — {self._port_combo.currentText()} @ {self._baud_combo.currentText()}"
        )

    @pyqtSlot()
    def _on_disconnected(self) -> None:
        self._connected = False
        self._btn_connect.setEnabled(True)
        self._btn_disconnect.setEnabled(False)
        self._set_controls_enabled(False)
        self._plot_timer.stop()
        self._status_bar.showMessage("Disconnected")

    @pyqtSlot(float, float, float, float, float)
    def _on_data(self, t_ms: float, a1: float, a2: float, a3: float, vq: float) -> None:
        self._buffer.append(t_ms, a1, a2, a3, vq)

    @pyqtSlot()
    def _refresh_plot(self) -> None:
        t_ms, a1, a2, a3, vq = self._buffer.last_n_seconds(10.0)
        self._plot.update_data(t_ms, a1, a2, a3, vq)

    @pyqtSlot(str)
    def _on_error(self, msg: str) -> None:
        self._status_bar.showMessage(f"Error: {msg}")

    @pyqtSlot()
    def _on_start(self) -> None:
        self._send_control_params()
        self._worker.send_command("START")

    @pyqtSlot()
    def _on_stop(self) -> None:
        self._worker.send_command("STOP")

    @pyqtSlot()
    def _on_export(self) -> None:
        if len(self._buffer) == 0:
            QMessageBox.information(self, "Empty", "No data to export yet.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", str(Path.home()), "CSV files (*.csv)"
        )
        if path:
            try:
                self._buffer.export_csv(path)
                self._status_bar.showMessage(f"Exported {len(self._buffer)} samples → {path}")
            except Exception as exc:
                QMessageBox.critical(self, "Export Error", str(exc))

    @pyqtSlot()
    def _on_clear(self) -> None:
        self._buffer.clear()
        self._plot.clear_data()

    # --- Slider / spinbox sync -----------------------------------------------

    def _on_amp_slider(self, value: int) -> None:
        v = self.AMP_MIN + value * self.AMP_STEP
        self._amp_spin.blockSignals(True)
        self._amp_spin.setValue(v)
        self._amp_spin.blockSignals(False)
        self._cmd_timer.start()

    def _on_amp_spin(self, value: float) -> None:
        idx = round((value - self.AMP_MIN) / self.AMP_STEP)
        self._amp_slider.blockSignals(True)
        self._amp_slider.setValue(idx)
        self._amp_slider.blockSignals(False)
        self._cmd_timer.start()

    def _on_freq_slider(self, value: int) -> None:
        f = self.FREQ_MIN + value * self.FREQ_STEP
        self._freq_spin.blockSignals(True)
        self._freq_spin.setValue(f)
        self._freq_spin.blockSignals(False)
        self._cmd_timer.start()

    def _on_freq_spin(self, value: float) -> None:
        idx = round((value - self.FREQ_MIN) / self.FREQ_STEP)
        self._freq_slider.blockSignals(True)
        self._freq_slider.setValue(idx)
        self._freq_slider.blockSignals(False)
        self._cmd_timer.start()

    def _send_control_params(self) -> None:
        if not self._connected:
            return
        self._worker.send_command(f"AMP:{self._amplitude():.2f}")
        self._worker.send_command(f"FREQ:{self._frequency():.2f}")
