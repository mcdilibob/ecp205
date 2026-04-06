"""
gui/control_panel.py — Motor control and plant parameter widgets.

MotorControlPanel  — amplitude/frequency spinboxes, START/STOP/Put Point buttons.
PlantParamsPanel   — J/k/c spinboxes and disk selector.

Both widgets expose Qt signals so MainWindow stays decoupled from their internals.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from .widgets import NoScrollDoubleSpinBox


# ---------------------------------------------------------------------------
# Module-level helper (shared by both panels)
# ---------------------------------------------------------------------------

def _make_spinbox(
    lo: float, hi: float, step: float,
    decimals: int = 2, initial: float = 0.0, width: int = 90,
) -> NoScrollDoubleSpinBox:
    sb = NoScrollDoubleSpinBox()
    sb.setRange(lo, hi)
    sb.setSingleStep(step)
    sb.setDecimals(decimals)
    sb.setValue(initial)
    sb.setFixedWidth(width)
    return sb


# ---------------------------------------------------------------------------
# MotorControlPanel
# ---------------------------------------------------------------------------

class MotorControlPanel(QGroupBox):
    """Controls for motor excitation: amplitude, frequency, and action buttons."""

    # Emitted when amp or freq spinbox value changes (debounce in MainWindow)
    params_changed = pyqtSignal()

    start_requested        = pyqtSignal()
    stop_requested         = pyqtSignal()
    sim_start_requested    = pyqtSignal()
    sim_stop_requested     = pyqtSignal()
    put_point_requested    = pyqtSignal()
    clear_points_requested = pyqtSignal()

    _AMP_MIN,  _AMP_MAX,  _AMP_STEP  = 0.0, 10.0, 0.1
    _FREQ_MIN, _FREQ_MAX, _FREQ_STEP = 0.1, 20.0, 0.1

    def __init__(self, parent=None) -> None:
        super().__init__("Motor Control", parent)
        self._build()

    # ---- public API ----

    def amp(self) -> float:
        return self._amp_spin.value()

    def freq(self) -> float:
        return self._freq_spin.value()

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable all interactive controls (called on connect/disconnect)."""
        for w in (self._btn_toggle, self._amp_spin, self._freq_spin, self._btn_put):
            w.setEnabled(enabled)

    def set_running(self, running: bool) -> None:
        """Sync toggle button state and lock spinboxes while excitation is active."""
        self._btn_toggle.blockSignals(True)
        self._btn_toggle.setChecked(running)
        self._btn_toggle.setText("Stop Plant" if running else "Start Plant")
        self._btn_toggle.blockSignals(False)
        self._btn_sim_toggle.setEnabled(not running)
        self._amp_spin.setEnabled(not running)
        self._freq_spin.setEnabled(not running)
        self._btn_put.setEnabled(not running)

    def set_sim_running(self, running: bool) -> None:
        """Sync sim toggle button state and lock controls while simulation is active."""
        self._btn_sim_toggle.blockSignals(True)
        self._btn_sim_toggle.setChecked(running)
        self._btn_sim_toggle.setText("Stop Model" if running else "Start Model")
        self._btn_sim_toggle.blockSignals(False)
        self._btn_toggle.setEnabled(not running)
        self._amp_spin.setEnabled(not running)
        self._freq_spin.setEnabled(not running)
        self._btn_put.setEnabled(True)   # Put Point активен во время и после симуляции

    def set_values(self, amp: float, freq: float) -> None:
        """Restore saved values without triggering params_changed."""
        for spin, val in ((self._amp_spin, amp), (self._freq_spin, freq)):
            spin.blockSignals(True)
            spin.setValue(val)
            spin.blockSignals(False)

    # ---- internal ----

    def _on_toggle(self, checked: bool) -> None:
        self._btn_toggle.setText("Stop Plant" if checked else "Start Plant")
        if checked:
            self.start_requested.emit()
        else:
            self.stop_requested.emit()

    def _on_sim_toggle(self, checked: bool) -> None:
        self._btn_sim_toggle.setText("Stop Model" if checked else "Start Model")
        if checked:
            self.sim_start_requested.emit()
        else:
            self.sim_stop_requested.emit()

    def _build(self) -> None:
        outer = QVBoxLayout(self)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)

        self._amp_spin  = _make_spinbox(self._AMP_MIN,  self._AMP_MAX,  self._AMP_STEP,  2, 1.0)
        self._freq_spin = _make_spinbox(self._FREQ_MIN, self._FREQ_MAX, self._FREQ_STEP, 2, 1.0)

        self._amp_spin.valueChanged.connect(self.params_changed)
        self._freq_spin.valueChanged.connect(self.params_changed)

        grid.addWidget(QLabel("Amplitude (V):"),  0, 0)
        grid.addWidget(self._amp_spin,             0, 1)
        grid.addWidget(QLabel("Frequency (Hz):"), 1, 0)
        grid.addWidget(self._freq_spin,            1, 1)
        outer.addLayout(grid)

        btn_row = QHBoxLayout()

        self._btn_toggle = QPushButton("Start Plant")
        self._btn_toggle.setObjectName("btn_toggle_plant")
        self._btn_toggle.setCheckable(True)
        self._btn_toggle.toggled.connect(self._on_toggle)
        btn_row.addWidget(self._btn_toggle)

        self._btn_sim_toggle = QPushButton("Start Model")
        self._btn_sim_toggle.setObjectName("btn_toggle_model")
        self._btn_sim_toggle.setCheckable(True)
        self._btn_sim_toggle.toggled.connect(self._on_sim_toggle)
        btn_row.addWidget(self._btn_sim_toggle)

        self._btn_put = QPushButton("Put Point")
        self._btn_put.clicked.connect(self.put_point_requested)
        btn_row.addWidget(self._btn_put)

        btn_clear = QPushButton("Clear Points")
        btn_clear.clicked.connect(self.clear_points_requested)
        btn_row.addWidget(btn_clear)

        outer.addLayout(btn_row)


# ---------------------------------------------------------------------------
# PlantParamsPanel
# ---------------------------------------------------------------------------

class PlantParamsPanel(QGroupBox):
    """Plant parameter spinboxes (J, k, c), weight controls, and output disk selector."""

    params_changed = pyqtSignal()

    _WEIGHT_MASS = 0.5   # kg, mass of one weight disk

    _PARAMS = [
        ("J₁",   0.0001, 1.0,   0.0001, 4, 0.0024),
        ("J₂",   0.0001, 1.0,   0.0001, 4, 0.0019),
        ("J₃",   0.0001, 1.0,   0.0001, 4, 0.0019),
        ("k₁",   0.01,   200.0, 0.01,   2, 2.7),
        ("k₂",   0.01,   200.0, 0.01,   2, 2.8),
        ("k_hw", 0.001,  10.0,  0.001,  3, 1.0),
        ("c₁",   0.0,    10.0,  0.001,  4, 0.0),
        ("c₂",   0.0,    10.0,  0.001,  4, 0.0),
        ("c₃",   0.0,    10.0,  0.001,  4, 0.0),
    ]
    # Layout positions: (row, col) for each of the 9 params
    _POSITIONS = [
        (0, 0), (0, 2), (0, 4),   # J₁ J₂ J₃
        (1, 0), (1, 2), (1, 4),   # k₁ k₂ k_hw
        (2, 0), (2, 2), (2, 4),   # c₁ c₂ c₃
    ]

    def __init__(self, parent=None) -> None:
        super().__init__("Plant Parameters", parent)
        self._build()

    # ---- public API ----

    def get_params(self) -> tuple[float, float, float, float, float,
                                   float, float, float, float, int]:
        """Return (J1_eff, J2_eff, J3_eff, k1, k2, k_hw, c1, c2, c3, disk).

        J_i_eff = J_i (base) + n_i * m * r_i²
        """
        J1, J2, J3, k1, k2, k_hw, c1, c2, c3 = (s.value() for s in self._spins)
        J1_eff, J2_eff, J3_eff = self._effective_J(J1, J2, J3)
        return J1_eff, J2_eff, J3_eff, k1, k2, k_hw, c1, c2, c3, self._disk_group.checkedId()

    def get_weight_config(self) -> tuple[int, float, int, float, int, float]:
        """Return (n1, r1_cm, n2, r2_cm, n3, r3_cm) — raw weight config for persistence."""
        return tuple(
            val
            for cb, sb in self._weight_controls
            for val in (cb.currentData(), sb.value())
        )

    def set_weight_config(self, n1: int, r1: float, n2: int, r2: float, n3: int, r3: float) -> None:
        """Restore weight config without triggering params_changed."""
        for (cb, sb), n, r in zip(self._weight_controls, (n1, n2, n3), (r1, r2, r3)):
            cb.blockSignals(True)
            sb.blockSignals(True)
            cb.setCurrentIndex(cb.findData(n))
            sb.setValue(r)
            cb.blockSignals(False)
            sb.blockSignals(False)

    def set_params(
        self,
        J1: float, J2: float, J3: float,
        k1: float, k2: float,
        k_hw: float,
        c1: float, c2: float, c3: float,
        disk: int,
    ) -> None:
        """Restore base J/k/c values without triggering params_changed."""
        for spin, val in zip(self._spins, (J1, J2, J3, k1, k2, k_hw, c1, c2, c3)):
            spin.blockSignals(True)
            spin.setValue(val)
            spin.blockSignals(False)
        for btn in self._disk_group.buttons():
            if self._disk_group.id(btn) == disk:
                btn.blockSignals(True)
                btn.setChecked(True)
                btn.blockSignals(False)
                break

    # ---- internal ----

    def _effective_J(self, J1: float, J2: float, J3: float) -> tuple[float, float, float]:
        result = []
        for J, (cb, sb) in zip((J1, J2, J3), self._weight_controls):
            n = cb.currentData()
            r = sb.value() / 100.0   # cm → m
            result.append(J + n * self._WEIGHT_MASS * r ** 2)
        return tuple(result)

    def _build(self) -> None:
        outer = QVBoxLayout(self)

        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)

        self._spins: list[NoScrollDoubleSpinBox] = []
        for (row, col), (lbl, lo, hi, step, dec, default) in zip(
            self._POSITIONS, self._PARAMS
        ):
            sb = _make_spinbox(lo, hi, step, dec, default, width=80)
            sb.valueChanged.connect(self.params_changed)
            grid.addWidget(QLabel(lbl), row, col)
            grid.addWidget(sb, row, col + 1)
            self._spins.append(sb)

        outer.addLayout(grid)

        # Weight controls: one row per disk
        weight_grid = QGridLayout()
        weight_grid.setHorizontalSpacing(6)
        weight_grid.setVerticalSpacing(2)
        self._weight_controls: list[tuple[QComboBox, NoScrollDoubleSpinBox]] = []
        for i in range(3):
            weight_grid.addWidget(QLabel(f"Диск {i+1}: грузы"), i, 0)
            cb = QComboBox()
            for n in (0, 2, 4):
                cb.addItem(str(n), n)
            cb.setFixedWidth(55)
            cb.currentIndexChanged.connect(self.params_changed)
            weight_grid.addWidget(cb, i, 1)

            weight_grid.addWidget(QLabel("r (см):"), i, 2)
            r_spin = _make_spinbox(0.1, 30.0, 0.1, 1, 6.0, width=60)
            r_spin.valueChanged.connect(self.params_changed)
            weight_grid.addWidget(r_spin, i, 3)

            self._weight_controls.append((cb, r_spin))

        outer.addLayout(weight_grid)

        disk_row = QHBoxLayout()
        disk_row.addWidget(QLabel("АЧХ диска:"))
        self._disk_group = QButtonGroup(self)
        for i, label in enumerate(("1", "2", "3"), start=1):
            rb = QRadioButton(label)
            if i == 1:
                rb.setChecked(True)
            self._disk_group.addButton(rb, i)
            disk_row.addWidget(rb)
        self._disk_group.idToggled.connect(
            lambda _id, checked: checked and self.params_changed.emit()
        )
        disk_row.addStretch()
        outer.addLayout(disk_row)
