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

    start_requested       = pyqtSignal()
    stop_requested        = pyqtSignal()
    put_point_requested   = pyqtSignal()
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
        self._amp_spin.setEnabled(not running)
        self._freq_spin.setEnabled(not running)
        self._btn_put.setEnabled(not running)

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
    """Plant parameter spinboxes (J, k, c) and output disk selector."""

    params_changed = pyqtSignal()

    _PARAMS = [
        ("J₁", 0.0001, 1.0,   0.0001, 4, 0.0024),
        ("J₂", 0.0001, 1.0,   0.0001, 4, 0.0019),
        ("J₃", 0.0001, 1.0,   0.0001, 4, 0.0019),
        ("k₁", 0.01,   200.0, 0.01,   2, 2.7),
        ("k₂", 0.01,   200.0, 0.01,   2, 2.8),
        ("c₁", 0.0,    10.0,  0.001,  4, 0.0),
        ("c₂", 0.0,    10.0,  0.001,  4, 0.0),
        ("c₃", 0.0,    10.0,  0.001,  4, 0.0),
    ]
    # Layout positions: (row, col) for each of the 8 params
    _POSITIONS = [
        (0, 0), (0, 2), (0, 4),   # J₁ J₂ J₃
        (1, 0), (1, 2),            # k₁ k₂
        (2, 0), (2, 2), (2, 4),   # c₁ c₂ c₃
    ]

    def __init__(self, parent=None) -> None:
        super().__init__("Plant Parameters", parent)
        self._build()

    # ---- public API ----

    def get_params(self) -> tuple[float, float, float, float, float,
                                   float, float, float, int]:
        """Return (J1, J2, J3, k1, k2, c1, c2, c3, disk)."""
        J1, J2, J3, k1, k2, c1, c2, c3 = (s.value() for s in self._spins)
        return J1, J2, J3, k1, k2, c1, c2, c3, self._disk_group.checkedId()

    def set_params(
        self,
        J1: float, J2: float, J3: float,
        k1: float, k2: float,
        c1: float, c2: float, c3: float,
        disk: int,
    ) -> None:
        """Restore saved values without triggering params_changed."""
        for spin, val in zip(self._spins, (J1, J2, J3, k1, k2, c1, c2, c3)):
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
