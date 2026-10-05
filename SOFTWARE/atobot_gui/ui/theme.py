"""theme.py - the dark theme: colour tokens, fonts and the application style sheet.

Copied from the Dynabo GUI so both projects look alike. Widgets pick styles by objectName
(e.g. QPushButton#Primary, QFrame#Card) instead of inline style sheets.
"""

# ---- Surfaces ----
BG = "#000000"            # window: pitch black
PANEL = "#050505"         # side panels, header
CARD = "#0D0D0D"
CARD_HI = "#161616"       # hover / inputs
BORDER = "#1F1F1F"
BORDER_HI = "#333333"

# ---- Text ----
TEXT = "#EDEDED"
TEXT_MUTED = "#999999"
TEXT_FAINT = "#5C5C5C"

# ---- Accent and status ----
ACCENT = "#4F9DFF"
ACCENT_HI = "#78B4FF"
OK = "#34D399"
WARN = "#FBBF24"
ERR = "#F87171"
ERR_STRONG = "#EF4444"
IDLE = "#6E6E6E"

# ---- Plots ----
PLOT_BG = "#000000"
PLOT_GRID = "#1A1A1A"
PLOT_AXIS = "#3A3A3A"
CMD = "#60A5FA"           # target (commanded) joint angle
ACTUAL = "#34D399"        # measured joint angle
ANKLE = "#FB7185"
TOE = "#38BDF8"
ROM_LINE = "#5C5C5C"      # range-of-motion limits

LEVEL_COLORS = {"ok": OK, "warn": WARN, "error": ERR, "idle": IDLE, "info": ACCENT}

FONT = '"Segoe UI Variable Text", "Segoe UI", "Inter", sans-serif'
MONO = '"Cascadia Mono", "Consolas", monospace'
MONO_FAMILY = "Cascadia Mono"      # for QFont; Qt falls back if it's missing


def rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{int(alpha * 255)})"


QSS = f"""
* {{
    font-family: {FONT};
    font-size: 13px;
    color: {TEXT};
    outline: none;
}}
QMainWindow, QDialog {{ background: {BG}; }}
QWidget#Page {{ background: {BG}; }}
QWidget#SidePanel {{ background: {PANEL}; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

QToolTip {{
    background: {CARD_HI}; color: {TEXT}; border: 1px solid {BORDER_HI};
    padding: 6px 8px; border-radius: 6px;
}}

/* ---- Tabs (one per device) ---- */
QTabWidget::pane {{ border: none; background: {BG}; }}
QTabWidget::tab-bar {{ left: 0px; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{
    background: transparent; color: {TEXT_MUTED};
    padding: 12px 22px; margin: 0px 2px;
    border: none; border-bottom: 2px solid transparent;
    font-size: 13px; font-weight: 600; letter-spacing: 1px;
}}
QTabBar::tab:hover {{ color: {TEXT}; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}

/* ---- Cards ---- */
QFrame#Card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 10px; }}
QLabel#CardTitle {{
    color: {TEXT_MUTED}; font-size: 11px; font-weight: 700; letter-spacing: 1.2px;
    background: transparent;
}}
QLabel#Muted {{ color: {TEXT_MUTED}; background: transparent; }}
QLabel#Faint {{ color: {TEXT_FAINT}; font-size: 11px; background: transparent; }}
QLabel#Hint {{ color: {TEXT_FAINT}; font-size: 11px; background: transparent; }}
QLabel#Value {{ font-family: {MONO}; font-size: 13px; background: transparent; }}
QLabel#BigValue {{ font-family: {MONO}; font-size: 20px; font-weight: 600; background: transparent; }}
QLabel#DeviceTitle {{ font-size: 22px; font-weight: 700; letter-spacing: 1px; background: transparent; }}
QLabel#Brand {{
    font-family: "Bahnschrift", "Segoe UI"; font-size: 22px; font-weight: 700; letter-spacing: 5px;
    padding: 0px 22px 0px 18px; background: transparent;
}}

/* ---- Buttons ---- */
QPushButton {{
    background: {CARD_HI}; color: {TEXT};
    border: 1px solid {BORDER_HI}; border-radius: 8px;
    padding: 8px 14px; font-weight: 600;
}}
QPushButton:hover {{ background: #202020; border-color: #444444; }}
QPushButton:pressed {{ background: #0A0A0A; }}
QPushButton:disabled {{ color: {TEXT_FAINT}; background: {CARD}; border-color: {BORDER}; }}

QPushButton#Primary {{
    background: {ACCENT}; color: #000000; border: 1px solid {ACCENT};
}}
QPushButton#Primary:hover {{ background: {ACCENT_HI}; border-color: {ACCENT_HI}; }}
QPushButton#Primary:disabled {{ background: {rgba(ACCENT, 0.18)}; color: {TEXT_FAINT}; border-color: transparent; }}

QPushButton#Ghost {{ background: transparent; border: 1px solid {BORDER_HI}; color: {TEXT_MUTED}; }}
QPushButton#Ghost:hover {{ color: {TEXT}; border-color: #444444; }}
QPushButton#Small {{ padding: 3px 10px; font-size: 11px; border-radius: 6px; background: transparent; color: {TEXT_MUTED}; }}
QPushButton#Small:hover {{ color: {TEXT}; }}

QPushButton#Stop {{
    background: {ERR_STRONG}; color: white; border: 1px solid {ERR_STRONG};
    border-radius: 10px; padding: 14px; font-size: 16px; font-weight: 800; letter-spacing: 3px;
}}
QPushButton#Stop:hover {{ background: #F25555; }}
QPushButton#Stop:pressed {{ background: #C93434; }}
QPushButton#Stop:disabled {{ background: {rgba(ERR_STRONG, 0.18)}; color: {rgba('#FFFFFF', 0.35)}; border-color: transparent; }}

QPushButton#Record:checked {{ background: {rgba(ERR_STRONG, 0.2)}; border-color: {ERR}; color: {ERR}; }}

/* ---- Inputs ---- */
QDoubleSpinBox, QSpinBox, QLineEdit {{
    background: {BG}; border: 1px solid {BORDER_HI}; border-radius: 6px;
    padding: 4px 6px; font-family: {MONO}; selection-background-color: {ACCENT};
}}
QDoubleSpinBox:focus, QSpinBox:focus, QLineEdit:focus {{ border-color: {ACCENT}; }}
QDoubleSpinBox:disabled {{ color: {TEXT_FAINT}; }}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 0px; border: none; }}

QSlider {{ background: transparent; }}
QSlider::groove:horizontal {{ height: 4px; background: {BORDER}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {TEXT}; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{ background: white; }}
QSlider::sub-page:horizontal:disabled {{ background: {BORDER_HI}; }}
QSlider::handle:horizontal:disabled {{ background: {TEXT_FAINT}; }}

QCheckBox {{ color: {TEXT_MUTED}; background: transparent; spacing: 6px; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {BORDER_HI}; border-radius: 4px; background: {BG}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

QComboBox {{
    background: {CARD_HI}; border: 1px solid {BORDER_HI}; border-radius: 8px; padding: 6px 10px; min-width: 150px;
}}
QComboBox QAbstractItemView {{ background: {CARD}; border: 1px solid {BORDER_HI}; selection-background-color: {rgba(ACCENT, 0.25)}; }}
QPlainTextEdit {{
    background: {BG}; border: 1px solid {BORDER}; border-radius: 8px; padding: 4px;
    font-family: {MONO}; font-size: 11px; color: {TEXT_MUTED};
}}

QListWidget {{ background: {BG}; border: 1px solid {BORDER}; border-radius: 8px; padding: 4px; }}
QListWidget::item {{ padding: 8px; border-radius: 6px; margin: 1px 0px; }}
QListWidget::item:hover {{ background: {CARD_HI}; }}
QListWidget::item:selected {{ background: {rgba(ACCENT, 0.18)}; color: {TEXT}; }}

QProgressBar {{ background: {BORDER}; border: none; border-radius: 2px; max-height: 3px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 2px; }}

QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0px; }}
QScrollBar::handle:vertical {{ background: {BORDER_HI}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
"""
