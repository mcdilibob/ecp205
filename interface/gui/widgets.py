"""
gui/widgets.py — Custom Qt widgets for ECP205.

NoScrollDoubleSpinBox: QDoubleSpinBox that ignores the mouse wheel unless
the widget has keyboard focus. Prevents accidental parameter changes when
the user scrolls the window past a spinbox.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QDoubleSpinBox


class NoScrollDoubleSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox that ignores wheel events when not focused."""

    def wheelEvent(self, event) -> None:
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()
