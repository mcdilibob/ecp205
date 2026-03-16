"""
bode_widget.py — Bode magnitude (АЧХ) plot for ECP205 torsional plant.

Transfer functions from ECP Model 205 manual, Appendix A (eqns A.4-6…A.4-12):

    θᵢ(s)/T(s) = Nᵢ(s) / D(s)

where:
    N₁(s) = J₂J₃s⁴ + [J₂c₃+J₃c₂]s³ + [J₂k₂+c₂c₃+J₃k₁+J₃k₂]s²
             + [c₂k₂+c₃k₁+c₃k₂]s + k₁k₂

    N₂(s) = k₁(J₃s² + c₃s + k₂)

    N₃(s) = k₁k₂

    D(s)  = J₁J₂J₃s⁶
            + [J₁J₂c₃+J₁J₃c₂+J₂J₃c₁]s⁵
            + [J₁(J₂k₂+J₃k₁+J₃k₂+c₂c₃)+J₂(J₃k₁+c₁c₃)+J₃c₁c₂]s⁴
            + [J₁(c₂k₂+c₃k₁+c₃k₂)+J₂(c₁k₂+c₃k₁)+J₃(c₁k₁+c₁k₂+c₂k₁)+c₁c₂c₃]s³
            + [(J₁+J₂+J₃)k₁k₂+c₁(c₂k₂+c₃k₁+c₃k₂)+c₂c₃k₁]s²
            + [(c₁+c₂+c₃)k₁k₂]s
            (constant term = 0: rigid-body mode → pole at s = 0)

Units: J [kg·m²], k [N·m/rad], c [N·m·s/rad]
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt6.QtGui import QColor

_F_MIN = 0.1    # Hz  — start of frequency range
_F_MAX = 15.0   # Hz  — end of frequency range
_N_PTS = 5000    # number of frequency points


def _compute_tf(
    J1: float, J2: float, J3: float,
    k1: float, k2: float,
    c1: float, c2: float, c3: float,
    disk: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (f_hz, magnitude_dB) for the chosen output disk."""
    f = np.linspace(_F_MIN, _F_MAX, _N_PTS)
    s = 1j * 2.0 * np.pi * f

    # --- Denominator D(s) (degree 6) ---
    D = (
        (J1 * J2 * J3) * s**6
        + (J1*J2*c3 + J1*J3*c2 + J2*J3*c1) * s**5
        + (J1*(J2*k2 + J3*k1 + J3*k2 + c2*c3) + J2*(J3*k1 + c1*c3) + J3*c1*c2) * s**4
        + (J1*(c2*k2 + c3*k1 + c3*k2) + J2*(c1*k2 + c3*k1) + J3*(c1*k1 + c1*k2 + c2*k1) + c1*c2*c3) * s**3
        + ((J1+J2+J3)*k1*k2 + c1*(c2*k2 + c3*k1 + c3*k2) + c2*c3*k1) * s**2
        + ((c1+c2+c3) * k1*k2) * s
        # s⁰ term = 0
    )

    # --- Numerator Nᵢ(s) ---
    if disk == 1:
        N = (
            (J2 * J3) * s**4
            + (J2*c3 + J3*c2) * s**3
            + (J2*k2 + c2*c3 + J3*k1 + J3*k2) * s**2
            + (c2*k2 + c3*k1 + c3*k2) * s
            + k1*k2
        )
    elif disk == 2:
        N = k1 * (J3*s**2 + c3*s + k2)
    else:  # disk 3
        N = np.full_like(s, k1 * k2)

    N_mag = np.abs(N)
    mag   = N_mag / np.abs(D)
    return f, mag, N_mag


class BodeWidget(pg.PlotWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.setBackground("#1e1e1e")
        self.setTitle("АЧХ")
        self.setLabel("left",   "Magnitude")
        self.setLabel("bottom", "Frequency", units="Hz")
        self.showGrid(x=True, y=True, alpha=0.3)
        self.setXRange(_F_MIN, _F_MAX, padding=0)
        self.setYRange(0, 4, padding=0)

        self.getPlotItem().layout.setContentsMargins(0, 0, 16, 0)
        self.getViewBox().setMouseEnabled(x=False, y=False)

        pen = pg.mkPen(color=QColor("#f1884e"), width=1.5)
        self._curve = self.plot([], [], pen=pen)
        self._anti_res_lines: list[pg.InfiniteLine] = []

    def update_tf(
        self,
        J1: float, J2: float, J3: float,
        k1: float, k2: float,
        c1: float, c2: float, c3: float,
        disk: int,
    ) -> None:
        f, mag, N_mag = _compute_tf(J1, J2, J3, k1, k2, c1, c2, c3, disk)
        finite = np.isfinite(mag)
        self._curve.setData(f[finite], mag[finite])

        # Anti-resonances: local minima of |Nᵢ(jω)|
        dN = np.diff(N_mag)
        min_idx = np.where((dN[:-1] < 0) & (dN[1:] > 0))[0] + 1
        anti_res_freqs = f[min_idx]

        for line in self._anti_res_lines:
            self.removeItem(line)
        self._anti_res_lines.clear()

        ar_pen = pg.mkPen(
            color=QColor("#4e9af1"), width=1,
            style=pg.QtCore.Qt.PenStyle.DashLine,
        )
        for freq in anti_res_freqs:
            line = pg.InfiniteLine(pos=freq, angle=90, pen=ar_pen)
            self.addItem(line)
            self._anti_res_lines.append(line)
