"""
gui/main_window.py — ECP205 GUI main window (PyQt6).

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
from PyQt6.QtCore import QSettings, QTimer, pyqtSlot
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from .bode_widget import BodeWidget
from .control_panel import MotorControlPanel, PlantParamsPanel
from .plot_widget import AnglePlotWidget, _PLOT_WINDOW
from data.data_buffer import DataBuffer
from serial_comm.serial_worker import SerialWorker
from serial_comm.protocol import cmd_start, cmd_stop, cmd_amp, cmd_freq
from simulation.sim_worker import SimWorker

_SETTINGS_ORG = "ECP205"
_SETTINGS_APP = "FrequencyResponseTool"


class MainWindow(QMainWindow):
    PLOT_REFRESH_MS = 50   # 20 Hz repaint

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ECP205 — Frequency Response Tool")
        self.resize(1280, 680)

        self._worker     = SerialWorker(self)
        self._sim_worker = SimWorker(self)
        self._buffer     = DataBuffer(max_seconds=60.0, sample_rate_hz=100.0)
        self._connected  = False
        self._sim_active = False        # simulation is running
        self._running    = False        # gates data + plot (plant OR sim)
        self._autoscroll = True         # sliding window vs freeze
        self._t0_ms: float | None = None  # timestamp of first sample in run

        # Debounce: send AMP/FREQ 200 ms after last spinbox change
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
        self._restore_settings()
        self._motor_ctrl.set_enabled(False)
        self._update_bode()   # draw with restored/default params on startup

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
        self._plot = AnglePlotWidget()
        plots_row.addWidget(self._plot, stretch=3)
        self._bode = BodeWidget()
        plots_row.addWidget(self._bode, stretch=2)
        root.addLayout(plots_row, stretch=1)

        # Bottom controls row
        self._motor_ctrl  = MotorControlPanel()
        self._plant_panel = PlantParamsPanel()
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(8)
        ctrl_row.addWidget(self._motor_ctrl)
        ctrl_row.addWidget(self._plant_panel)
        ctrl_row.addStretch()
        root.addLayout(ctrl_row)

        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Disconnected")

    def _build_connection_bar(self) -> QGroupBox:
        box = QGroupBox("Serial Connection")
        layout = QHBoxLayout(box)

        # LED status indicator
        self._led = QLabel()
        self._led.setFixedSize(12, 12)
        self._set_led(False)
        layout.addWidget(self._led)

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
        for b in ("115200", "57600"):
            self._baud_combo.addItem(b)
        layout.addWidget(self._baud_combo)

        self._btn_connect = QPushButton("Connect")
        self._btn_connect.setObjectName("btn_connect")
        self._btn_connect.clicked.connect(self._on_connect)
        layout.addWidget(self._btn_connect)

        self._btn_disconnect = QPushButton("Disconnect")
        self._btn_disconnect.setObjectName("btn_disconnect")
        self._btn_disconnect.setEnabled(False)
        self._btn_disconnect.clicked.connect(self._on_disconnect)
        layout.addWidget(self._btn_disconnect)

        layout.addStretch()

        btn_plot_png = QPushButton("Plot PNG")
        btn_plot_png.clicked.connect(self._on_save_plot_png)
        layout.addWidget(btn_plot_png)

        btn_bode_png = QPushButton("Bode PNG")
        btn_bode_png.clicked.connect(self._on_save_bode_png)
        layout.addWidget(btn_bode_png)

        self._btn_export = QPushButton("Export CSV")
        self._btn_export.clicked.connect(self._on_export)
        layout.addWidget(self._btn_export)

        self._btn_clear = QPushButton("Clear Buffer")
        self._btn_clear.clicked.connect(self._on_clear)
        layout.addWidget(self._btn_clear)

        self._btn_autoscroll = QPushButton("Autoscroll")
        self._btn_autoscroll.setCheckable(True)
        self._btn_autoscroll.setChecked(True)
        self._btn_autoscroll.toggled.connect(self._on_autoscroll_toggled)
        layout.addWidget(self._btn_autoscroll)

        return box

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _set_led(self, connected: bool) -> None:
        color = "#a6e3a1" if connected else "#585b70"
        self._led.setStyleSheet(f"background-color: {color}; border-radius: 6px;")

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

    # -------------------------------------------------------------------------
    # Settings persistence
    # -------------------------------------------------------------------------

    def _restore_settings(self) -> None:
        s = QSettings(_SETTINGS_ORG, _SETTINGS_APP)

        # Connection
        port = s.value("connection/port", self._DEFAULT_PORT)
        baud = s.value("connection/baud", "115200")
        idx = self._port_combo.findText(port)
        if idx >= 0:
            self._port_combo.setCurrentIndex(idx)
        idx = self._baud_combo.findText(baud)
        if idx >= 0:
            self._baud_combo.setCurrentIndex(idx)

        # Motor control
        amp  = float(s.value("motor/amp",  1.0))
        freq = float(s.value("motor/freq", 1.0))
        self._motor_ctrl.set_values(amp, freq)

        # Plant parameters
        _keys     = ("J1", "J2", "J3", "k1", "k2", "k_hw", "c1", "c2", "c3")
        _defaults = (0.0024, 0.0019, 0.0019, 2.7, 2.8, 1.0, 0.0, 0.0, 0.0)
        vals = [float(s.value(f"plant/{k}", d)) for k, d in zip(_keys, _defaults)]
        disk = int(s.value("plant/disk", 1))
        self._plant_panel.set_params(*vals, disk)

        # Weights
        _wkeys    = ("n1", "r1", "n2", "r2", "n3", "r3")
        _wdefs    = (0, 6.0, 0, 6.0, 0, 6.0)
        wvals = [float(s.value(f"weights/{k}", d)) for k, d in zip(_wkeys, _wdefs)]
        self._plant_panel.set_weight_config(
            int(wvals[0]), wvals[1], int(wvals[2]), wvals[3], int(wvals[4]), wvals[5]
        )

    def closeEvent(self, event) -> None:
        s = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        s.setValue("connection/port", self._port_combo.currentText())
        s.setValue("connection/baud", self._baud_combo.currentText())
        s.setValue("motor/amp",  self._motor_ctrl.amp())
        s.setValue("motor/freq", self._motor_ctrl.freq())
        # Save base J values (spins), not effective — weights are saved separately
        base_J1 = self._plant_panel._spins[0].value()
        base_J2 = self._plant_panel._spins[1].value()
        base_J3 = self._plant_panel._spins[2].value()
        _, _, _, k1, k2, k_hw, c1, c2, c3, disk = self._plant_panel.get_params()
        for key, val in zip(
            ("J1", "J2", "J3", "k1", "k2", "k_hw", "c1", "c2", "c3"),
            (base_J1, base_J2, base_J3, k1, k2, k_hw, c1, c2, c3),
        ):
            s.setValue(f"plant/{key}", val)
        s.setValue("plant/disk", disk)

        n1, r1, n2, r2, n3, r3 = self._plant_panel.get_weight_config()
        for key, val in zip(("n1", "r1", "n2", "r2", "n3", "r3"), (n1, r1, n2, r2, n3, r3)):
            s.setValue(f"weights/{key}", val)
        super().closeEvent(event)

    # -------------------------------------------------------------------------
    # Signal wiring
    # -------------------------------------------------------------------------

    def _connect_signals(self) -> None:
        # Serial worker
        self._worker.data_received.connect(self._on_data)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.connected.connect(self._on_connected)
        self._worker.disconnected.connect(self._on_disconnected)

        # Simulation worker
        self._sim_worker.data_received.connect(self._on_data)

        # Motor control panel
        self._motor_ctrl.params_changed.connect(lambda: self._cmd_timer.start())
        self._motor_ctrl.start_requested.connect(self._on_start)
        self._motor_ctrl.stop_requested.connect(self._on_stop)
        self._motor_ctrl.sim_start_requested.connect(self._on_sim_start)
        self._motor_ctrl.sim_stop_requested.connect(self._on_sim_stop)
        self._motor_ctrl.put_point_requested.connect(self._on_put_point)
        self._motor_ctrl.clear_points_requested.connect(self._bode.clear_exp_points)

        # Plant params panel
        self._plant_panel.params_changed.connect(lambda: self._bode_timer.start())

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
        self._worker.send_command(cmd_stop())
        self._worker.close()

    @pyqtSlot()
    def _on_connected(self) -> None:
        self._connected = True
        self._btn_connect.setEnabled(False)
        self._btn_disconnect.setEnabled(True)
        self._motor_ctrl.set_enabled(True)
        self._set_led(True)
        self._plot_timer.start()
        self._status_bar.showMessage(
            f"Connected — {self._port_combo.currentText()} @ {self._baud_combo.currentText()}"
        )

    @pyqtSlot()
    def _on_disconnected(self) -> None:
        self._connected = False
        self._btn_connect.setEnabled(True)
        self._btn_disconnect.setEnabled(False)
        self._motor_ctrl.set_enabled(False)
        self._set_led(False)
        if not self._sim_active:
            self._plot_timer.stop()
        self._status_bar.showMessage("Disconnected")

    @pyqtSlot(object, object, object, object, object)
    def _on_data(self, t_ms, a1, a2, a3, vq) -> None:
        if not self._running:
            return   # installation stopped — discard incoming frames
        self._buffer.append_batch(t_ms, a1, a2, a3, vq)

    @pyqtSlot()
    def _refresh_plot(self) -> None:
        if not self._running:
            return   # plot is frozen — nothing to redraw

        t_ms, a1, a2, a3, vq = self._buffer.as_arrays()
        if t_ms.size == 0:
            return

        if self._t0_ms is None:
            self._t0_ms = float(t_ms[0])

        t_s     = (t_ms - self._t0_ms) / 1000.0
        elapsed = float(t_s[-1])

        if elapsed <= _PLOT_WINDOW:
            # Phase 1: fill left → right, axis fixed at [0, 15 s]
            self._plot.update_data(t_s, a1, a2, a3, vq,
                                   x_range=(0.0, _PLOT_WINDOW))
        elif self._autoscroll:
            # Phase 2: sliding window — new data on the right
            lo = elapsed - _PLOT_WINDOW
            mask = t_s >= lo
            self._plot.update_data(t_s[mask], a1[mask], a2[mask], a3[mask], vq[mask],
                                   x_range=(lo, elapsed))
        # Phase 3: autoscroll OFF + elapsed > window → no-op, plot stays frozen

    @pyqtSlot(bool)
    def _on_autoscroll_toggled(self, checked: bool) -> None:
        self._autoscroll = checked

    @pyqtSlot()
    def _update_bode(self) -> None:
        J1, J2, J3, k1, k2, k_hw, c1, c2, c3, disk = self._plant_panel.get_params()
        self._bode.update_tf(J1, J2, J3, k1, k2, k_hw, c1, c2, c3, disk)

    @pyqtSlot(str)
    def _on_error(self, msg: str) -> None:
        self._status_bar.showMessage(f"Error: {msg}")

    @pyqtSlot()
    def _on_start(self) -> None:
        self._buffer.clear()
        self._t0_ms  = None
        self._running = True
        self._send_control_params()
        self._worker.send_command(cmd_start())
        self._motor_ctrl.set_running(True)

    @pyqtSlot()
    def _on_stop(self) -> None:
        self._running = False          # freeze plot and stop accepting data
        self._worker.send_command(cmd_stop())
        self._motor_ctrl.set_running(False)

    @pyqtSlot()
    def _on_sim_start(self) -> None:
        J1, J2, J3, k1, k2, k_hw, c1, c2, c3, _ = self._plant_panel.get_params()
        self._sim_worker.set_params(J1, J2, J3, k1, k2, k_hw, c1, c2, c3)
        self._sim_worker.set_excitation(self._motor_ctrl.amp(), self._motor_ctrl.freq())
        self._buffer.clear()
        self._t0_ms   = None
        self._running  = True
        self._sim_active = True
        self._sim_worker.start_sim()
        self._plot_timer.start()
        self._motor_ctrl.set_sim_running(True)
        self._status_bar.showMessage("Simulation running")

    @pyqtSlot()
    def _on_sim_stop(self) -> None:
        self._running    = False
        self._sim_active = False
        self._sim_worker.stop_sim()
        if not self._connected:
            self._plot_timer.stop()
        self._motor_ctrl.set_sim_running(False)
        self._status_bar.showMessage("Simulation stopped")

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
                self._status_bar.showMessage(
                    f"Exported {len(self._buffer)} samples → {path}"
                )
            except Exception as exc:
                QMessageBox.critical(self, "Export Error", str(exc))

    @pyqtSlot()
    def _on_clear(self) -> None:
        self._buffer.clear()
        self._plot.clear_data()

    @pyqtSlot()
    def _on_put_point(self) -> None:
        freq   = self._motor_ctrl.freq()
        amp_in = self._motor_ctrl.amp()
        if amp_in == 0.0:
            return

        # Use at least 5 full periods, minimum 2 s — more periods → sharper FFT bin
        window = max(2.0, 5.0 / freq)
        t_ms, a1, a2, a3, _ = self._buffer.last_n_seconds(window)
        if t_ms.size < 4:
            return

        # Compute amplitude via FFT at the excitation frequency bin
        dt = float(np.median(np.diff(t_ms))) / 1000.0  # s, robust to jitter
        n  = len(t_ms)
        fft_freqs = np.fft.rfftfreq(n, dt)
        bin_idx   = int(np.argmin(np.abs(fft_freqs - freq)))

        def _fft_mag(sig: np.ndarray) -> float:
            return 2.0 * float(np.abs(np.fft.rfft(sig)[bin_idx])) / n / amp_in

        mag1, mag2, mag3 = _fft_mag(a1), _fft_mag(a2), _fft_mag(a3)
        self._bode.add_exp_point(freq, mag1, mag2, mag3)

    @pyqtSlot()
    def _on_save_plot_png(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Plot PNG", str(Path.home()), "PNG images (*.png)"
        )
        if path:
            self._plot.save_png(path)
            self._status_bar.showMessage(f"Plot saved → {path}")

    @pyqtSlot()
    def _on_save_bode_png(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Bode PNG", str(Path.home()), "PNG images (*.png)"
        )
        if path:
            self._bode.save_png(path)
            self._status_bar.showMessage(f"Bode saved → {path}")

    def _send_control_params(self) -> None:
        if not self._connected:
            return
        self._worker.send_command(cmd_amp(self._motor_ctrl.amp()))
        self._worker.send_command(cmd_freq(self._motor_ctrl.freq()))
