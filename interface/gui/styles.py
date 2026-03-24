"""
gui/styles.py — Dark QSS theme for ECP205 (Catppuccin Mocha palette).

Apply once at startup via app.setStyleSheet(DARK_THEME).
pyqtgraph plot widgets have their own background set via pg.setConfigOptions
and are not affected by this stylesheet.
"""

# Catppuccin Mocha colour tokens
_BASE    = "#1e1e2e"   # main window / widget background
_MANTLE  = "#181825"   # deeper background (status bar, disabled)
_SURFACE0 = "#313244"  # input fields, cards
_SURFACE1 = "#45475a"  # borders, button backgrounds
_SURFACE2 = "#585b70"  # hover accents, disabled text
_TEXT    = "#cdd6f4"   # primary text
_SUBTEXT = "#a6adc8"   # secondary / dim text
_BLUE    = "#89b4fa"   # accent, connect, focus rings
_GREEN   = "#a6e3a1"   # success, START
_RED     = "#f38ba8"   # error, STOP, disconnect
_ORANGE  = "#fab387"   # warning

DARK_THEME = f"""
/* ── Base ──────────────────────────────────────────────────────────── */
QMainWindow, QWidget {{
    background-color: {_BASE};
    color: {_TEXT};
    font-size: 12px;
}}

/* ── Group boxes ────────────────────────────────────────────────────── */
QGroupBox {{
    border: 1px solid {_SURFACE1};
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 6px;
    font-weight: bold;
    color: {_BLUE};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    left: 10px;
}}

/* ── Buttons (default) ──────────────────────────────────────────────── */
QPushButton {{
    background-color: {_SURFACE0};
    color: {_TEXT};
    border: 1px solid {_SURFACE1};
    border-radius: 4px;
    padding: 4px 12px;
    min-height: 24px;
}}
QPushButton:hover {{
    background-color: {_SURFACE1};
    border-color: {_BLUE};
}}
QPushButton:pressed {{
    background-color: {_SURFACE2};
}}
QPushButton:disabled {{
    background-color: {_MANTLE};
    color: {_SURFACE2};
    border-color: {_SURFACE0};
}}

/* ── Connect button ─────────────────────────────────────────────────── */
QPushButton#btn_connect {{
    background-color: #1a2f4a;
    color: {_BLUE};
    border-color: {_BLUE};
    font-weight: bold;
}}
QPushButton#btn_connect:hover {{
    background-color: #254570;
}}
QPushButton#btn_connect:disabled {{
    background-color: {_MANTLE};
    color: {_SURFACE2};
    border-color: {_SURFACE0};
}}

/* ── Disconnect button ──────────────────────────────────────────────── */
QPushButton#btn_disconnect {{
    background-color: #3a1f1f;
    color: {_RED};
    border-color: {_RED};
    font-weight: bold;
}}
QPushButton#btn_disconnect:hover {{
    background-color: #542a2a;
}}
QPushButton#btn_disconnect:disabled {{
    background-color: {_MANTLE};
    color: {_SURFACE2};
    border-color: {_SURFACE0};
}}

/* ── START button ───────────────────────────────────────────────────── */
QPushButton#btn_start {{
    background-color: #1a3320;
    color: {_GREEN};
    border-color: {_GREEN};
    font-weight: bold;
}}
QPushButton#btn_start:hover {{
    background-color: #264d2f;
}}
QPushButton#btn_start:disabled {{
    background-color: {_MANTLE};
    color: {_SURFACE2};
    border-color: {_SURFACE0};
}}

/* ── STOP button ────────────────────────────────────────────────────── */
QPushButton#btn_stop {{
    background-color: #3a1f1f;
    color: {_RED};
    border-color: {_RED};
    font-weight: bold;
}}
QPushButton#btn_stop:hover {{
    background-color: #542a2a;
}}
QPushButton#btn_stop:disabled {{
    background-color: {_MANTLE};
    color: {_SURFACE2};
    border-color: {_SURFACE0};
}}

/* ── Spinboxes ──────────────────────────────────────────────────────── */
QDoubleSpinBox, QSpinBox {{
    background-color: {_SURFACE0};
    color: {_TEXT};
    border: 1px solid {_SURFACE1};
    border-radius: 4px;
    padding: 2px 4px;
    min-height: 22px;
}}
QDoubleSpinBox:focus, QSpinBox:focus {{
    border-color: {_BLUE};
}}
QDoubleSpinBox:disabled, QSpinBox:disabled {{
    background-color: {_MANTLE};
    color: {_SURFACE2};
}}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
QSpinBox::up-button,       QSpinBox::down-button {{
    background-color: {_SURFACE1};
    border: none;
    width: 16px;
}}
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover,
QSpinBox::up-button:hover,       QSpinBox::down-button:hover {{
    background-color: {_SURFACE2};
}}

/* ── ComboBox ───────────────────────────────────────────────────────── */
QComboBox {{
    background-color: {_SURFACE0};
    color: {_TEXT};
    border: 1px solid {_SURFACE1};
    border-radius: 4px;
    padding: 2px 6px;
    min-height: 22px;
}}
QComboBox:focus {{
    border-color: {_BLUE};
}}
QComboBox::drop-down {{
    border: none;
    background-color: {_SURFACE1};
    width: 20px;
    border-top-right-radius: 4px;
    border-bottom-right-radius: 4px;
}}
QComboBox::down-arrow {{
    width: 8px;
    height: 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {_SURFACE0};
    color: {_TEXT};
    selection-background-color: {_SURFACE1};
    border: 1px solid {_SURFACE1};
    outline: none;
}}

/* ── Radio buttons ──────────────────────────────────────────────────── */
QRadioButton {{
    color: {_TEXT};
    spacing: 6px;
}}
QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border: 2px solid {_SURFACE2};
    border-radius: 7px;
    background-color: {_SURFACE0};
}}
QRadioButton::indicator:checked {{
    background-color: {_BLUE};
    border-color: {_BLUE};
}}
QRadioButton::indicator:hover {{
    border-color: {_BLUE};
}}

/* ── Labels ─────────────────────────────────────────────────────────── */
QLabel {{
    color: {_TEXT};
}}

/* ── Status bar ─────────────────────────────────────────────────────── */
QStatusBar {{
    background-color: {_MANTLE};
    color: {_SUBTEXT};
    border-top: 1px solid {_SURFACE0};
}}

/* ── Scrollbars ─────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: {_MANTLE};
    width: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {_SURFACE2};
    border-radius: 4px;
    min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{
    background: {_BLUE};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

/* ── Message boxes ──────────────────────────────────────────────────── */
QMessageBox {{
    background-color: {_BASE};
}}
QMessageBox QLabel {{
    color: {_TEXT};
}}
"""
