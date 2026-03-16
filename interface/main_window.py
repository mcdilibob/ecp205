"""
main_window.py — ECP205 GUI main window (PyQt6).

Layout:
  ┌─ Serial Connection ─────────────────────────────────────────────────────┐
  ├──────────────────────────────────┬──────────────────────────────────────┤
  │   Angle plot (real-time)         │   АЧХ / Bode magnitude plot          │
  ├──────────────────────────────────┴──────────────────────────────────────┤
  │ [Motor Control]  [Plant Parameters J/k/c + disk selector]               │
  └─────────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import serial.tools.list_ports
from PyQt6.QtCore import QTimer, pyqtSlot
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from bode_widget import BodeWidget
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

    PLOT_REFRESH_MS = 50   # 20 Hz repaint

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ECP205 — Frequency Response Tool")
        self.resize(1280, 680)

        self._worker = SerialWorker(self)
        self._buffer = DataBuffer(max_seconds=60.0, sample_rate_hz=200.0)
        self._connected = False

        # Debounce: send AMP/FREQ 200 ms after last change
        self._cmd_timer = QTimer(self)
        self._cmd_timer.setSingleShot(True)
        self._cmd_timer.setInterval(200)
        self._cmd_timer.timeout.connect(self._send_control_params)

        # Debounce: redraw Bode 300 ms after last param change
        self._bode_timer = QTimer(self)
        self._bode_timer.setSingleShot(True)
        self._bode_timer.setInterval(300)
        self._bode_timer.timeout.connect(self._update_bode)

        # Plot refresh timer
        self._plot_timer = QTimer(self)
        self._plot_timer.setInterval(self.PLOT_REFRESH_MS)
        self._plot_timer.timeout.connect(self._refresh_plot)

        self._build_ui()
        self._connect_signals()
        self._set_controls_enabled(False)
        self._update_bode()   # draw with default params on startup

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

        # Plots side by side — angle plot (wider) | Bode plot
        plots_row = QHBoxLayout()
        self._plot = AnglePlotWidget(window_seconds=15.0)
        plots_row.addWidget(self._plot, stretch=3)
        self._bode = BodeWidget()
        plots_row.addWidget(self._bode, stretch=2)
        root.addLayout(plots_row, stretch=1)

        # Bottom controls row
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(8)
        ctrl_row.addWidget(self._build_control_panel())
        ctrl_row.addWidget(self._build_plant_params())
        ctrl_row.addStretch()
        root.addLayout(ctrl_row)

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

        self._btn_export = QPushButton("Export CSV")
        self._btn_export.clicked.connect(self._on_export)
        layout.addWidget(self._btn_export)

        self._btn_clear = QPushButton("Clear Buffer")
        self._btn_clear.clicked.connect(self._on_clear)
        layout.addWidget(self._btn_clear)

        return box

    def _build_control_panel(self) -> QGroupBox:
        box = QGroupBox("Motor Control")
        outer = QVBoxLayout(box)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)

        self._amp_spin = self._make_spinbox(
            self.AMP_MIN, self.AMP_MAX, self.AMP_STEP, decimals=2, initial=1.0
        )
        self._freq_spin = self._make_spinbox(
            self.FREQ_MIN, self.FREQ_MAX, self.FREQ_STEP, decimals=2, initial=1.0
        )

        grid.addWidget(QLabel("Amplitude (V):"),  0, 0)
        grid.addWidget(self._amp_spin,             0, 1)
        grid.addWidget(QLabel("Frequency (Hz):"), 1, 0)
        grid.addWidget(self._freq_spin,            1, 1)
        outer.addLayout(grid)

        btn_row = QHBoxLayout()
        self._btn_start = QPushButton("START")
        self._btn_start.setStyleSheet("background:#2a7a2a; color:white; font-weight:bold;")
        self._btn_start.clicked.connect(self._on_start)
        btn_row.addWidget(self._btn_start)

        self._btn_stop = QPushButton("STOP")
        self._btn_stop.setStyleSheet("background:#7a2a2a; color:white; font-weight:bold;")
        self._btn_stop.clicked.connect(self._on_stop)
        btn_row.addWidget(self._btn_stop)

        outer.addLayout(btn_row)
        return box

    def _build_plant_params(self) -> QGroupBox:
        box = QGroupBox("Plant Parameters")
        outer = QVBoxLayout(box)

        # ---- Parameter spinboxes ----
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)

        # Helper: (label, lo, hi, step, decimals, default)
        params = [
            ("J₁", 0.0001, 1.0, 0.0001, 4, 0.002),
            ("J₂", 0.0001, 1.0, 0.0001, 4, 0.002),
            ("J₃", 0.0001, 1.0, 0.0001, 4, 0.002),
            ("k₁", 0.01, 200.0, 0.01, 2, 0.5),
            ("k₂", 0.01, 200.0, 0.01, 2, 0.5),
            ("c₁", 0.0001, 10.0, 0.001, 4, 0.01),
            ("c₂", 0.0001, 10.0, 0.001, 4, 0.01),
            ("c₃", 0.0001, 10.0, 0.001, 4, 0.01),
        ]
        self._param_spins: list[QDoubleSpinBox] = []

        # Layout: 3 columns of (label, spinbox) pairs
        positions = [
            (0, 0), (0, 2), (0, 4),   # J₁ J₂ J₃
            (1, 0), (1, 2),            # k₁ k₂
            (2, 0), (2, 2), (2, 4),   # c₁ c₂ c₃
        ]
        for (row, col), (lbl, lo, hi, step, dec, default) in zip(positions, params):
            sb = self._make_spinbox(lo, hi, step, decimals=dec, initial=default, width=80)
            grid.addWidget(QLabel(lbl), row, col)
            grid.addWidget(sb, row, col + 1)
            self._param_spins.append(sb)

        outer.addLayout(grid)

        # ---- Disk selector ----
        disk_row = QHBoxLayout()
        disk_row.addWidget(QLabel("АЧХ диска:"))
        self._disk_group = QButtonGroup(self)
        for i, label in enumerate(("1", "2", "3"), start=1):
            rb = QRadioButton(label)
            if i == 1:
                rb.setChecked(True)
            self._disk_group.addButton(rb, i)
            disk_row.addWidget(rb)
        disk_row.addStretch()
        outer.addLayout(disk_row)

        return box

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _make_spinbox(
        lo: float, hi: float, step: float,
        decimals: int = 2, initial: float = 0.0, width: int = 90,
    ) -> QDoubleSpinBox:
        sb = QDoubleSpinBox()
        sb.setRange(lo, hi)
        sb.setSingleStep(step)
        sb.setDecimals(decimals)
        sb.setValue(initial)
        sb.setFixedWidth(width)
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
        for w in (self._btn_start, self._btn_stop, self._amp_spin, self._freq_spin):
            w.setEnabled(enabled)

    def _plant_params(self) -> tuple:
        J1, J2, J3, k1, k2, c1, c2, c3 = (s.value() for s in self._param_spins)
        disk = self._disk_group.checkedId()
        return J1, J2, J3, k1, k2, c1, c2, c3, disk

    # -------------------------------------------------------------------------
    # Signal wiring
    # -------------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self._worker.data_received.connect(self._on_data)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.connected.connect(self._on_connected)
        self._worker.disconnected.connect(self._on_disconnected)

        self._amp_spin.valueChanged.connect(lambda _: self._cmd_timer.start())
        self._freq_spin.valueChanged.connect(lambda _: self._cmd_timer.start())

        for sb in self._param_spins:
            sb.valueChanged.connect(lambda _: self._bode_timer.start())
        self._disk_group.idToggled.connect(lambda _, checked: checked and self._update_bode())

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

    @pyqtSlot(object, object, object, object, object)
    def _on_data(self, t_ms, a1, a2, a3, vq) -> None:
        self._buffer.append_batch(t_ms, a1, a2, a3, vq)

    @pyqtSlot()
    def _refresh_plot(self) -> None:
        t_ms, a1, a2, a3, vq = self._buffer.last_n_seconds(15.0)
        self._plot.update_data(t_ms, a1, a2, a3, vq)

    @pyqtSlot()
    def _update_bode(self) -> None:
        J1, J2, J3, k1, k2, c1, c2, c3, disk = self._plant_params()
        self._bode.update_tf(J1, J2, J3, k1, k2, c1, c2, c3, disk)

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

    def _send_control_params(self) -> None:
        if not self._connected:
            return
        self._worker.send_command(f"AMP:{self._amp_spin.value():.2f}")
        self._worker.send_command(f"FREQ:{self._freq_spin.value():.2f}")
