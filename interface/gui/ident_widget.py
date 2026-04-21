"""
gui/ident_widget.py — Parameter identification page (Chapter 5).

Added-inertia method (Perfilev_Term_Paper_2024.pdf §5):
  - Fix disk 2.  Deflect disk 1 (or 3) → free oscillation.
  - Record with weights → ω₁;  record without weights → ω₂.
  - Formulas (6): J = ω₂²/(ω₁²−ω₂²)·Jₘ,  k = ω₁²ω₂²/(ω₁²−ω₂²)·Jₘ
  - Formula  (7): c = √(Jk)/(πn) · ln(A₀/Aₙ)

Four configurations, each with its own 30-s ring buffer:
    d1_with    — Disk 1, with weights   → ω₁ for disk 1
    d1_without — Disk 1, without weights→ ω₂ for disk 1
    d3_with    — Disk 3, with weights   → ω₁ for disk 3
    d3_without — Disk 3, without weights→ ω₂ for disk 3

MainWindow wires:
    worker.data_received  → ident_widget.on_live_data
    ident_widget.params_identified → _on_apply_identified
    _on_clear             → ident_widget.clear_all_buffers
"""

from __future__ import annotations

import math
from collections import OrderedDict

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from data.data_buffer import DataBuffer

# ── configuration registry ─────────────────────────────────────────────────────
_CONFIGS: OrderedDict[str, dict] = OrderedDict([
    ("d1_with",    {"disk": 1, "with_weights": True,  "label": "Disk 1 — with weights"}),
    ("d1_without", {"disk": 1, "with_weights": False, "label": "Disk 1 — without weights"}),
    ("d3_with",    {"disk": 3, "with_weights": True,  "label": "Disk 3 — with weights"}),
    ("d3_without", {"disk": 3, "with_weights": False, "label": "Disk 3 — without weights"}),
])

_PAIRS = [
    (1, "d1_with", "d1_without"),   # disk 1: with → ω₁,  without → ω₂
    (3, "d3_with", "d3_without"),   # disk 3: with → ω₁,  without → ω₂
]

# ── visual constants ───────────────────────────────────────────────────────────
_WEIGHT_MASS  = 0.500   # kg per cylindrical weight
_WEIGHT_RADIUS = 0.025   # m
_BUF_SECONDS  = 30.0    # s per config buffer
_BUF_RATE_HZ  = 200.0   # must match firmware DATA_RATE_HZ
_BG           = "#1e1e1e"
_C_ANGLE      = "#4e9af1"
_C_PEAKS      = "#f1884e"
_C_FFT        = "#61c972"
_C_PEAK_LINE  = "#ff4444"


class _NoScrollSpin(QDoubleSpinBox):
    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


def _dspin(lo, hi, step, dec, val, w=80):
    sb = _NoScrollSpin()
    sb.setRange(lo, hi)
    sb.setSingleStep(step)
    sb.setDecimals(dec)
    sb.setValue(val)
    sb.setFixedWidth(w)
    return sb


# ── main widget ────────────────────────────────────────────────────────────────

class IdentWidget(QWidget):
    """
    Parameter identification page.

    Emits params_identified(disk, J, k, c):
        disk = 1  →  J₁, k₁, c₁
        disk = 3  →  J₃, k₂, c₃
    """

    params_identified = pyqtSignal(int, float, float, float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        # One ring buffer per configuration
        self._buffers: dict[str, DataBuffer] = {
            key: DataBuffer(max_seconds=_BUF_SECONDS, sample_rate_hz=_BUF_RATE_HZ)
            for key in _CONFIGS
        }

        # Analysis state per configuration
        # cfg_key → {t, angle, omega, f_peak, A0, An, n}
        self._state: dict[str, dict] = {}

        # Computed results per disk
        # disk → {J, k, c}
        self._results: dict[int, dict] = {}

        self._is_recording = False
        self._sample_count = 0

        self._build()

    # ── public API ─────────────────────────────────────────────────────────────

    @pyqtSlot(object, object, object, object, object)
    def on_live_data(self, t_ms, a1, a2, a3, u) -> None:
        """Connected to SerialWorker.data_received in MainWindow."""
        if not self._is_recording:
            return
        cfg = self._current_cfg()
        self._buffers[cfg].append_batch(t_ms, a1, a2, a3, u)
        self._sample_count += len(t_ms)
        self._update_live_plot(t_ms, a1, a2, a3)
        self._lbl_status.setText(f"Recording…  {self._sample_count} samples")

    def clear_all_buffers(self) -> None:
        """Called by MainWindow when the global Clear Buffer button is pressed."""
        for buf in self._buffers.values():
            buf.clear()
        self._state.clear()
        self._results.clear()
        self._angle_curve.setData([], [])
        self._peak_scatter.setData([], [])
        self._fft_curve.setData([], [])
        self._fft_line.setVisible(False)
        self._clear_cfg_results()
        self._clear_disk_results()
        self._lbl_status.setText("All buffers cleared.")

    # ── layout ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(6)
        root.setContentsMargins(8, 8, 8, 8)

        root.addWidget(self._build_top_bar())
        root.addLayout(self._build_plots(), stretch=1)
        root.addWidget(self._build_cfg_results())
        root.addWidget(self._build_disk_results())

    def _build_top_bar(self) -> QGroupBox:
        box = QGroupBox("Configuration")
        lay = QHBoxLayout(box)

        # Config selector
        lay.addWidget(QLabel("Measurement:"))
        self._cfg_combo = QComboBox()
        for key, cfg in _CONFIGS.items():
            self._cfg_combo.addItem(cfg["label"], key)
        self._cfg_combo.currentIndexChanged.connect(self._on_cfg_changed)
        lay.addWidget(self._cfg_combo)

        lay.addSpacing(16)

        # Weight parameters (shown only when "with weights" config selected)
        lay.addWidget(QLabel("Weights:"))
        self._n_weights = QSpinBox()
        self._n_weights.setRange(0, 4)
        self._n_weights.setValue(4)
        self._n_weights.setFixedWidth(45)
        self._n_weights.valueChanged.connect(self._update_jm)
        lay.addWidget(self._n_weights)
        lay.addWidget(QLabel(f"× {_WEIGHT_MASS} kg,  r ="))
        self._r_cm = _dspin(0.1, 30.0, 0.1, 1, 9.0, w=60)
        self._r_cm.valueChanged.connect(self._update_jm)
        lay.addWidget(self._r_cm)
        lay.addWidget(QLabel("cm"))

        lay.addSpacing(12)
        self._lbl_jm = QLabel("Jₘ = —")
        lay.addWidget(self._lbl_jm)

        lay.addStretch()

        # Record / Stop
        self._btn_record = QPushButton("Record")
        self._btn_record.setCheckable(True)
        self._btn_record.setFixedWidth(110)
        self._btn_record.toggled.connect(self._on_record_toggled)
        lay.addWidget(self._btn_record)

        # Analyze
        self._btn_analyze = QPushButton("Analyze")
        self._btn_analyze.setFixedWidth(90)
        self._btn_analyze.setEnabled(False)
        self._btn_analyze.clicked.connect(self._auto_analyze)
        lay.addWidget(self._btn_analyze)

        # Clear all
        btn_clear = QPushButton("Clear All")
        btn_clear.setToolTip("Clear all four configuration buffers")
        btn_clear.clicked.connect(self.clear_all_buffers)
        lay.addWidget(btn_clear)

        lay.addSpacing(8)
        self._lbl_status = QLabel("Ready.")
        self._lbl_status.setMinimumWidth(180)
        lay.addWidget(self._lbl_status)

        self._update_jm()
        return box

    def _build_plots(self) -> QHBoxLayout:
        row = QHBoxLayout()

        # Angle plot
        self._angle_plot = pg.PlotWidget()
        self._angle_plot.setBackground(_BG)
        self._angle_plot.setLabel("left",   "Angle",    units="rad")
        self._angle_plot.setLabel("bottom", "Time",     units="s")
        self._angle_plot.setTitle("Free oscillation")
        self._angle_plot.showGrid(x=True, y=True, alpha=0.3)
        self._angle_plot.addLegend(offset=(10, 10))
        self._angle_curve = self._angle_plot.plot(
            [], [], pen=pg.mkPen(QColor(_C_ANGLE), width=1.5), name="θ(t)"
        )
        self._peak_scatter = pg.ScatterPlotItem(
            size=8, pen=pg.mkPen(None),
            brush=pg.mkBrush(QColor(_C_PEAKS)), symbol="o", name="peaks"
        )
        self._angle_plot.addItem(self._peak_scatter)
        row.addWidget(self._angle_plot, stretch=3)

        # FFT plot
        self._fft_plot = pg.PlotWidget()
        self._fft_plot.setBackground(_BG)
        self._fft_plot.setLabel("left",   "Amplitude", units="rad")
        self._fft_plot.setLabel("bottom", "Frequency", units="Hz")
        self._fft_plot.setTitle("FFT Spectrum")
        self._fft_plot.showGrid(x=True, y=True, alpha=0.3)
        self._fft_curve = self._fft_plot.plot(
            [], [], pen=pg.mkPen(QColor(_C_FFT), width=1.5)
        )
        self._fft_line = pg.InfiniteLine(
            angle=90, movable=False,
            pen=pg.mkPen(QColor(_C_PEAK_LINE), width=1.5,
                         style=Qt.PenStyle.DashLine)
        )
        self._fft_plot.addItem(self._fft_line)
        self._fft_line.setVisible(False)
        row.addWidget(self._fft_plot, stretch=2)

        return row

    def _build_cfg_results(self) -> QGroupBox:
        """Results panel for the currently selected configuration."""
        box = QGroupBox("Current configuration")
        lay = QHBoxLayout(box)

        lay.addWidget(QLabel("ω ="))
        self._lbl_omega = QLabel("—")
        self._lbl_omega.setMinimumWidth(70)
        lay.addWidget(self._lbl_omega)
        lay.addWidget(QLabel("rad/s"))

        lay.addSpacing(16)
        lay.addWidget(QLabel("A₀ ="))
        self._lbl_A0 = QLabel("—")
        self._lbl_A0.setMinimumWidth(70)
        lay.addWidget(self._lbl_A0)
        lay.addWidget(QLabel("rad"))

        lay.addSpacing(16)
        lay.addWidget(QLabel("Aₙ ="))
        self._lbl_An = QLabel("—")
        self._lbl_An.setMinimumWidth(70)
        lay.addWidget(self._lbl_An)
        lay.addWidget(QLabel("rad"))

        lay.addSpacing(16)
        lay.addWidget(QLabel("n periods ="))
        self._n_periods = QSpinBox()
        self._n_periods.setRange(1, 50)
        self._n_periods.setValue(5)
        self._n_periods.setFixedWidth(55)
        lay.addWidget(self._n_periods)

        lay.addStretch()
        return box

    def _build_disk_results(self) -> QGroupBox:
        """Final J/k/c results and Apply buttons for each disk."""
        box = QGroupBox("Identification results")
        lay = QGridLayout(box)
        lay.setHorizontalSpacing(8)
        lay.setVerticalSpacing(4)

        # Headers
        for col, text in enumerate(("", "J  (kg·m²)", "k  (N·m/rad)", "c  (N·m·s/rad)", "")):
            lay.addWidget(QLabel(f"<b>{text}</b>"), 0, col)

        self._disk_labels: dict[int, dict[str, QLabel]] = {}
        self._apply_btns: dict[int, QPushButton] = {}

        for row, (disk, key_with, key_without) in enumerate(_PAIRS, start=1):
            lay.addWidget(QLabel(f"Disk {disk}:"), row, 0)

            lbls = {}
            for col, name in enumerate(("J", "k", "c"), start=1):
                lbl = QLabel("—")
                lbl.setMinimumWidth(90)
                lay.addWidget(lbl, row, col)
                lbls[name] = lbl
            self._disk_labels[disk] = lbls

            btn = QPushButton(f"Apply Disk {disk}")
            btn.setEnabled(False)
            btn.clicked.connect(lambda _, d=disk: self._on_apply(d))
            lay.addWidget(btn, row, 4)
            self._apply_btns[disk] = btn

        return box

    # ── helpers ────────────────────────────────────────────────────────────────

    def _current_cfg(self) -> str:
        return self._cfg_combo.currentData()

    def _update_jm(self) -> None:
        n = self._n_weights.value()
        r = self._r_cm.value() / 100.0
        jm = n *(0.5*_WEIGHT_MASS * _WEIGHT_RADIUS**2 + _WEIGHT_MASS * r ** 2)
        self._lbl_jm.setText(f"Jₘ = {jm * 1e4:.3f}×10⁻⁴ kg·m²")

    def _clear_cfg_results(self) -> None:
        for lbl in (self._lbl_omega, self._lbl_A0, self._lbl_An):
            lbl.setText("—")

    def _clear_disk_results(self) -> None:
        for disk in (1, 3):
            for lbl in self._disk_labels[disk].values():
                lbl.setText("—")
            self._apply_btns[disk].setEnabled(False)

    def _load_cfg_into_plots(self, cfg: str) -> None:
        """Reload plots and result labels from stored state for cfg."""
        if cfg not in self._state:
            self._angle_curve.setData([], [])
            self._peak_scatter.setData([], [])
            self._fft_curve.setData([], [])
            self._fft_line.setVisible(False)
            self._clear_cfg_results()
            self._angle_plot.setTitle("Free oscillation")
            self._fft_plot.setTitle("FFT Spectrum")
            return

        s = self._state[cfg]
        t, angle = s["t"], s["angle"]
        self._angle_curve.setData(t, angle)

        if "peaks" in s:
            px, py = s["peaks"]
            self._peak_scatter.setData(x=px.tolist(), y=py.tolist())
        else:
            self._peak_scatter.setData([], [])

        if "freqs" in s:
            self._fft_curve.setData(s["freqs"], s["spec"])
            f = s.get("f_peak", 0.0)
            self._fft_line.setValue(f)
            self._fft_line.setVisible(True)
            omega = s.get("omega", 0.0)
            self._fft_plot.setTitle(
                f"FFT Spectrum — f = {f:.3f} Hz,  ω = {omega:.3f} rad/s"
            )
        else:
            self._fft_curve.setData([], [])
            self._fft_line.setVisible(False)
            self._fft_plot.setTitle("FFT Spectrum")

        self._lbl_omega.setText(f"{s.get('omega', 0):.4f}" if "omega" in s else "—")
        self._lbl_A0.setText(f"{s['A0']:.5f}" if "A0" in s else "—")
        self._lbl_An.setText(f"{s['An']:.5f}" if "An" in s else "—")
        if "n" in s:
            self._n_periods.setValue(s["n"])

        label = _CONFIGS[cfg]["label"]
        self._angle_plot.setTitle(f"Free oscillation — {label}")

    def _update_live_plot(self, t_ms, a1, a2, a3) -> None:
        """Show live angle trace while recording (called from on_live_data)."""
        cfg  = self._current_cfg()
        disk = _CONFIGS[cfg]["disk"]
        buf  = self._buffers[cfg]
        if len(buf) < 2:
            return
        t_all, a1_all, a2_all, a3_all, _ = buf.as_arrays()
        angle = (a1_all if disk == 1 else a3_all)
        angle = angle - float(np.mean(angle))
        t_s   = (t_all - float(t_all[0])) / 1000.0
        self._angle_curve.setData(t_s, angle)

    # ── slots ──────────────────────────────────────────────────────────────────

    def _on_cfg_changed(self) -> None:
        if self._is_recording:
            # Stop recording before switching
            self._btn_record.setChecked(False)
        cfg = self._current_cfg()
        self._load_cfg_into_plots(cfg)
        self._lbl_status.setText("Ready.")

    def _on_record_toggled(self, checked: bool) -> None:
        if checked:
            cfg = self._current_cfg()
            self._buffers[cfg].clear()          # fresh buffer for new recording
            self._sample_count = 0
            self._is_recording = True
            self._btn_record.setText("Stop Recording")
            self._btn_analyze.setEnabled(False)
            self._angle_curve.setData([], [])
            self._peak_scatter.setData([], [])
            self._fft_curve.setData([], [])
            self._fft_line.setVisible(False)
            self._lbl_status.setText("Recording…  0 samples")
        else:
            self._is_recording = False
            self._btn_record.setText("Record")
            self._btn_analyze.setEnabled(True)
            self._lbl_status.setText("Recording stopped. Press Analyze.")

    def _auto_analyze(self) -> None:
        """Extract angle from buffer, run FFT + peak detection, try to compute."""
        cfg = self._current_cfg()
        buf = self._buffers[cfg]
        if len(buf) < 10:
            self._lbl_status.setText("Not enough data.")
            return

        t_ms, a1, a2, a3, _ = buf.as_arrays()
        disk  = _CONFIGS[cfg]["disk"]
        angle = (a1 if disk == 1 else a3)
        angle = angle - float(np.mean(angle))
        t_s   = (t_ms - float(t_ms[0])) / 1000.0

        self._state[cfg] = {"t": t_s, "angle": angle}
        self._run_fft_and_peaks(cfg)
        self._load_cfg_into_plots(cfg)
        self._try_compute()
        n_s = len(buf)
        self._lbl_status.setText(f"Analysis done — {n_s} samples captured.")

    def _run_fft_and_peaks(self, cfg: str) -> None:
        s   = self._state[cfg]
        t   = s["t"]
        ang = s["angle"]

        # ── FFT ──────────────────────────────────────────────────────────────
        dt = float(np.median(np.diff(t)))
        if dt <= 0:
            return
        N     = len(ang)
        freqs = np.fft.rfftfreq(N, dt)
        spec  = np.abs(np.fft.rfft(ang)) * 2 / N

        # Skip DC; find peak above 0.3 Hz
        start = max(1, int(0.3 / freqs[1]) if len(freqs) > 1 else 1)
        pk    = int(np.argmax(spec[start:])) + start
        f_pk  = float(freqs[pk])
        omega = 2.0 * math.pi * f_pk

        # Zoom FFT display to 3× peak frequency
        f_max = max(f_pk * 3.0, 5.0)
        mask  = freqs <= f_max

        s["omega"]  = omega
        s["f_peak"] = f_pk
        s["freqs"]  = freqs[mask]
        s["spec"]   = spec[mask]

        # ── Peak detection ────────────────────────────────────────────────────
        n_per = self._n_periods.value()
        abs_a = np.abs(ang)
        is_pk = (abs_a[1:-1] > abs_a[:-2]) & (abs_a[1:-1] > abs_a[2:])
        pidx  = np.where(is_pk)[0] + 1

        if len(pidx) >= 2:
            A0     = float(abs_a[pidx[0]])
            target = min(n_per, len(pidx) - 1)
            An     = float(abs_a[pidx[target]])
            s["A0"]    = A0
            s["An"]    = An
            s["n"]     = target
            s["peaks"] = (t[pidx], ang[pidx])
        else:
            s["A0"]    = float(np.max(abs_a))
            s["An"]    = s["A0"]
            s["n"]     = 1
            s["peaks"] = (t[pidx], ang[pidx]) if len(pidx) else (np.array([]), np.array([]))

    def _try_compute(self) -> None:
        """Attempt to compute J/k/c for each disk pair."""
        for disk, key_with, key_without in _PAIRS:
            sw = self._state.get(key_with,    {})
            sn = self._state.get(key_without, {})
            if "omega" not in sw or "omega" not in sn:
                continue
            self._compute_disk(disk, sw, sn)

    def _compute_disk(self, disk: int, sw: dict, sn: dict) -> None:
        """Apply formulas (6) and (7) for one disk."""
        omega1 = sn["omega"]   # without weights → higher frequency
        omega2 = sw["omega"]   # with weights → lower frequency

        n_w = self._n_weights.value()
        r   = self._r_cm.value() / 100.0
        Jm  = n_w * (0.5*_WEIGHT_MASS * _WEIGHT_RADIUS**2 + _WEIGHT_MASS * r ** 2)

        denom = omega1 ** 2 - omega2 ** 2
        if abs(denom) < 1e-12 or denom < 0:
            lbls = self._disk_labels[disk]
            lbls["J"].setText("err: ω₁≥ω₂")
            lbls["k"].setText("—")
            lbls["c"].setText("—")
            self._apply_btns[disk].setEnabled(False)
            return

        # Formula (6)
        J = (omega2 ** 2 / denom) * Jm
        k = (omega1 ** 2 * omega2 ** 2 / denom) * Jm

        # Formula (7) — use decay from "with weights" measurement
        A0 = sw.get("A0", 0.0)
        An = sw.get("An", 0.0)
        n  = sw.get("n",  1)
        if A0 > 0 and An > 0 and A0 > An and n > 0:
            c = math.sqrt(J * k) / (math.pi * n) * math.log(A0 / An)
        else:
            c = 0.0

        self._results[disk] = {"J": J, "k": k, "c": c}

        lbls = self._disk_labels[disk]
        lbls["J"].setText(f"{J:.5f}")
        lbls["k"].setText(f"{k:.4f}")
        lbls["c"].setText(f"{c:.5f}")
        self._apply_btns[disk].setEnabled(True)

    def _on_apply(self, disk: int) -> None:
        r = self._results.get(disk)
        if r is None:
            return
        self.params_identified.emit(disk, r["J"], r["k"], r["c"])
