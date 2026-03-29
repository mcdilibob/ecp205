"""
gui/plot_widget.py — Real-time pyqtgraph plot for 3 disk angles.

Shows a rolling window of the last `window_seconds` of data.
Call update_data() from the main window whenever new samples arrive.
"""

from __future__ import annotations

from math import pi

import numpy as np
import pyqtgraph as pg
from PyQt6.QtGui import QColor


_COLORS = ("#4e9af1", "#f1884e", "#61c972")   # blue, orange, green
_DISK_LABELS = ("Disk 1", "Disk 2", "Disk 3")


_PLOT_WINDOW = 15.0   # seconds — fixed display window


class AnglePlotWidget(pg.PlotWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        # Appearance
        self.setBackground("#1e1e1e")
        self.setLabel("left",   "Angle", units="rad")
        self.setLabel("bottom", "Time",  units="s")
        self.setTitle("Disk Angles")
        self.showGrid(x=True, y=True, alpha=0.3)
        self.addLegend(offset=(10, 10))
        self.setYRange(-pi, pi)
        self.setXRange(0.0, _PLOT_WINDOW, padding=0)
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

    def update_data(
        self,
        t_s: np.ndarray,
        a1: np.ndarray,
        a2: np.ndarray,
        a3: np.ndarray,
        vq: np.ndarray,
        x_range: tuple[float, float] = (0.0, _PLOT_WINDOW),
    ) -> None:
        """Refresh all curves. t_s is in seconds (already sliced by caller)."""
        if t_s.size == 0:
            return
        for curve, angles in zip(self._curves, (a1, a2, a3)):
            curve.setData(t_s, angles)
        self._vq_curve.setData(t_s, vq)
        self.setXRange(x_range[0], x_range[1], padding=0)

    def clear_data(self) -> None:
        for curve in self._curves:
            curve.setData([], [])
        self._vq_curve.setData([], [])

    def save_png(self, path: str) -> None:
        exporter = pg.exporters.ImageExporter(self.getPlotItem())
        exporter.export(path)
