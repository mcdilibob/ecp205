"""
plot_widget.py — Real-time pyqtgraph plot for 3 disk angles.

Shows a rolling window of the last `window_seconds` of data.
Call update_data() from the main window whenever new samples arrive.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt6.QtGui import QColor
from math import pi


_COLORS = ("#4e9af1", "#f1884e", "#61c972")   # blue, orange, green
_DISK_LABELS = ("Disk 1", "Disk 2", "Disk 3")


class AnglePlotWidget(pg.PlotWidget):
    def __init__(self, window_seconds: float = 10.0, parent=None) -> None:
        super().__init__(parent)
        self._window_s = window_seconds

        # Appearance
        self.setBackground("#1e1e1e")
        self.setLabel("left",   "Angle", units="rad")
        self.setLabel("bottom", "Time",  units="s")
        self.setTitle("Disk Angles")
        self.showGrid(x=True, y=True, alpha=0.3)
        self.addLegend(offset=(10, 10))
        self.setYRange(0, 2 * pi)
        self.setClipToView(True)
        # Even grid: major lines every π/2, minor every π/6
        self.getAxis("left").setTickSpacing(major=pi / 2, minor=pi / 6)
        # Right padding
        self.getPlotItem().layout.setContentsMargins(0, 0, 16, 0)

        # One curve per disk
        self._curves: list[pg.PlotDataItem] = []
        for color, label in zip(_COLORS, _DISK_LABELS):
            pen = pg.mkPen(color=QColor(color), width=1.5)
            curve = self.plot([], [], pen=pen, name=label)
            self._curves.append(curve)

        # Motor command on the same Y axis
        vq_pen = pg.mkPen(color=QColor("#b0b0b0"), width=1, style=pg.QtCore.Qt.PenStyle.DashLine)
        self._vq_curve = self.plot([], [], pen=vq_pen, name="Vq")

        # Lock interaction — no zoom, no pan
        self.getViewBox().setMouseEnabled(x=False, y=False)

    def set_window(self, seconds: float) -> None:
        self._window_s = max(1.0, seconds)

    def update_data(
        self,
        t_ms: np.ndarray,
        a1: np.ndarray,
        a2: np.ndarray,
        a3: np.ndarray,
        vq: np.ndarray,
    ) -> None:
        """Refresh all curves. Arrays must be the same length."""
        if t_ms.size == 0:
            return

        # Convert to seconds, zero-based for display
        t_s = (t_ms - t_ms[0]) / 1000.0

        # Rolling window
        cutoff = t_s[-1] - self._window_s
        mask = t_s >= cutoff
        ts = t_s[mask]

        for curve, angles in zip(self._curves, (a1[mask], a2[mask], a3[mask])):
            curve.setData(ts, angles)

        self._vq_curve.setData(ts, vq[mask])

        # Always show exactly _window_s seconds on the X axis
        self.setXRange(ts[-1] - self._window_s, ts[-1], padding=0)

    def clear_data(self) -> None:
        for curve in self._curves:
            curve.setData([], [])
        self._vq_curve.setData([], [])
