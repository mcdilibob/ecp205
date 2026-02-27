"""
main.py — Entry point for the ECP205 frequency-response GUI.

Usage:
    pip install -r requirements.txt
    python main.py
"""

import sys

import pyqtgraph as pg
from PyQt6.QtWidgets import QApplication

from main_window import MainWindow


def main() -> None:
    pg.setConfigOptions(antialias=True, foreground="w", background="#1e1e1e")

    app = QApplication(sys.argv)
    app.setApplicationName("ECP205 Frequency Response Tool")
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
