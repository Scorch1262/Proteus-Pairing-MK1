"""Farbschema im Stil der Dashboards (dunkel, Amber/Türkis-Akzente)."""

BG = "#0a0d10"
PANEL = "#11161b"
PANEL_2 = "#161c22"
BORDER = "#222b34"
BORDER_2 = "#2e3944"
TEXT = "#d3dae1"
MUTED = "#6f7c89"
AMBER = "#f5a524"
TEAL = "#2ec4b6"
RED = "#ff5d5d"
GREEN = "#3ddc84"

MONO = '"Cascadia Mono", "Consolas", "Menlo", "SF Mono", "DejaVu Sans Mono", monospace'

QSS = f"""
* {{
    color: {TEXT};
    font-size: 13px;
}}
QMainWindow, QDialog, #root {{ background: {BG}; }}
QToolTip {{ background: {PANEL_2}; color: {TEXT}; border: 1px solid {BORDER_2}; padding: 4px; }}

/* ---------- Kopfzeile ---------- */
#header {{ background: {PANEL}; border-bottom: 1px solid {BORDER}; }}
#logo {{ background: {AMBER}; color: {BG}; font-weight: 800; font-size: 15px; border-radius: 3px; }}
#appTitle {{ font-size: 16px; font-weight: 700; letter-spacing: 3px; }}
#appSub {{ color: {MUTED}; font-size: 11px; letter-spacing: 2px; }}
#statusPill {{
    border: 1px solid {BORDER_2}; border-radius: 11px; padding: 3px 12px;
    font-size: 11px; font-weight: 700; letter-spacing: 2px; color: {MUTED};
}}
#statusPill[state="run"]  {{ color: {TEAL};  border-color: {TEAL}; }}
#statusPill[state="user"] {{ color: {BG}; background: {AMBER}; border-color: {AMBER}; }}
#statusPill[state="ok"]   {{ color: {GREEN}; border-color: {GREEN}; }}
#statusPill[state="err"]  {{ color: {RED};   border-color: {RED}; }}

/* ---------- Panels ---------- */
QFrame#panel {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 4px; }}
QLabel#panelTitle {{
    color: {MUTED}; font-size: 11px; font-weight: 700; letter-spacing: 2px;
}}
QLabel#phaseTitle {{
    color: {AMBER}; font-size: 11px; font-weight: 700; letter-spacing: 2px; padding-top: 6px;
}}
QLabel#muted {{ color: {MUTED}; }}
QLabel#value {{ font-family: {MONO}; font-size: 13px; }}
QLabel#bigMac {{ font-family: {MONO}; font-size: 22px; font-weight: 700; color: {TEAL}; letter-spacing: 1px; }}

/* ---------- Schrittliste ---------- */
QFrame#stepRow {{ border-left: 2px solid transparent; border-radius: 2px; }}
QFrame#stepRow[state="active"] {{ background: rgba(46,196,182,0.08); border-left: 2px solid {TEAL}; }}
QFrame#stepRow[state="user"]   {{ background: rgba(245,165,36,0.12); border-left: 2px solid {AMBER}; }}
QFrame#stepRow[state="error"]  {{ background: rgba(255,93,93,0.10); border-left: 2px solid {RED}; }}
QLabel#stepIcon {{
    font-family: {MONO}; font-size: 11px; font-weight: 700; color: {MUTED};
    border: 1px solid {BORDER_2}; border-radius: 10px;
}}
QLabel#stepIcon[state="active"]  {{ color: {TEAL};  border-color: {TEAL}; }}
QLabel#stepIcon[state="user"]    {{ color: {BG};    background: {AMBER}; border-color: {AMBER}; }}
QLabel#stepIcon[state="done"]    {{ color: {BG};    background: {TEAL}; border-color: {TEAL}; }}
QLabel#stepIcon[state="error"]   {{ color: {BG};    background: {RED}; border-color: {RED}; }}
QLabel#stepIcon[state="skipped"] {{ color: {BORDER_2}; border-color: {BORDER}; }}
QLabel#stepTitle {{ color: {MUTED}; }}
QLabel#stepTitle[state="active"] {{ color: {TEXT}; font-weight: 600; }}
QLabel#stepTitle[state="user"]   {{ color: {AMBER}; font-weight: 700; }}
QLabel#stepTitle[state="done"]   {{ color: {TEXT}; }}
QLabel#stepTitle[state="error"]  {{ color: {RED}; font-weight: 600; }}
QLabel#stepTitle[state="skipped"] {{ color: {BORDER_2}; }}
QLabel#stepDetail {{ color: {MUTED}; font-family: {MONO}; font-size: 11px; }}
QLabel#stepRef {{ color: {BORDER_2}; font-family: {MONO}; font-size: 10px; }}
QLabel#userTag {{
    color: {AMBER}; border: 1px solid {AMBER}; border-radius: 2px;
    font-size: 9px; font-weight: 700; letter-spacing: 1px; padding: 0 3px;
}}

/* ---------- Aktionskarte ---------- */
QFrame#actionCard {{ background: {PANEL}; border: 1px solid {BORDER}; border-left: 4px solid {BORDER_2}; border-radius: 4px; }}
QFrame#actionCard[mode="auto"]  {{ border-left-color: {TEAL}; }}
QFrame#actionCard[mode="done"]  {{ border-left-color: {GREEN}; }}
QFrame#actionCard[mode="error"] {{ border: 1px solid {RED}; border-left: 4px solid {RED}; background: #1a1012; }}
QFrame#actionCard[mode="user"]  {{ border: 2px solid {AMBER}; border-left: 6px solid {AMBER}; background: #1c160b; }}
QFrame#actionCard[mode="user"][blink="1"] {{ border-color: #7a5512; }}
QLabel#actionMode {{ font-size: 12px; font-weight: 800; letter-spacing: 3px; color: {MUTED}; }}
QLabel#actionMode[mode="auto"]  {{ color: {TEAL}; }}
QLabel#actionMode[mode="user"]  {{ color: {AMBER}; }}
QLabel#actionMode[mode="error"] {{ color: {RED}; }}
QLabel#actionMode[mode="done"]  {{ color: {GREEN}; }}
QLabel#actionText {{ font-size: 24px; font-weight: 700; }}
QLabel#actionText[mode="user"] {{ color: #ffd48a; font-size: 26px; }}
QLabel#actionHint {{ color: {MUTED}; font-size: 13px; }}
QLabel#actionStep {{ color: {MUTED}; font-family: {MONO}; font-size: 11px; }}

QProgressBar {{
    background: {PANEL_2}; border: 1px solid {BORDER}; border-radius: 2px; height: 6px;
    text-align: center; color: transparent;
}}
QProgressBar::chunk {{ background: {TEAL}; }}
QProgressBar[mode="user"]::chunk {{ background: {AMBER}; }}

/* ---------- Knöpfe ---------- */
QPushButton {{
    background: {PANEL_2}; border: 1px solid {BORDER_2}; border-radius: 3px;
    padding: 7px 14px; font-weight: 600; letter-spacing: 1px;
}}
QPushButton:hover {{ border-color: {TEAL}; color: #ffffff; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:disabled {{ color: {BORDER_2}; border-color: {BORDER}; }}
QPushButton#primary {{ background: {TEAL}; color: {BG}; border-color: {TEAL}; font-weight: 800; }}
QPushButton#primary:hover {{ background: #45d8ca; }}
QPushButton#primary:disabled {{ background: {PANEL_2}; color: {BORDER_2}; border-color: {BORDER}; }}
QPushButton#amber {{ background: {AMBER}; color: {BG}; border-color: {AMBER}; font-weight: 800; font-size: 15px; padding: 10px 26px; }}
QPushButton#amber:hover {{ background: #ffbb45; }}
QPushButton#danger:hover {{ border-color: {RED}; color: {RED}; }}
QPushButton#small {{ padding: 3px 8px; font-size: 11px; }}

/* ---------- Tabs, Log, Tabelle ---------- */
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 4px; background: {PANEL}; top: -1px; }}
QTabBar::tab {{
    background: transparent; color: {MUTED}; padding: 6px 16px; border: none;
    font-size: 11px; font-weight: 700; letter-spacing: 2px;
}}
QTabBar::tab:selected {{ color: {AMBER}; border-bottom: 2px solid {AMBER}; }}
QPlainTextEdit, QTableWidget {{
    background: {BG}; border: none; font-family: {MONO}; font-size: 12px;
    selection-background-color: #24414a;
}}
QHeaderView::section {{
    background: {PANEL_2}; color: {MUTED}; border: none; border-bottom: 1px solid {BORDER};
    padding: 4px 6px; font-size: 11px; font-weight: 700;
}}
QTableWidget {{ gridline-color: {BORDER}; }}
QScrollBar:vertical {{ background: transparent; width: 9px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BORDER_2}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 9px; }}
QScrollBar::handle:horizontal {{ background: {BORDER_2}; border-radius: 4px; min-width: 30px; }}

/* ---------- Formulare ---------- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {BG}; border: 1px solid {BORDER_2}; border-radius: 3px; padding: 5px 8px;
    font-family: {MONO};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {TEAL}; }}
QComboBox QAbstractItemView {{ background: {PANEL_2}; border: 1px solid {BORDER_2}; selection-background-color: #24414a; outline: 0; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {BORDER_2}; border-radius: 2px; background: {BG}; }}
QCheckBox::indicator:checked {{ background: {TEAL}; border-color: {TEAL}; }}
QGroupBox {{
    border: 1px solid {BORDER}; border-radius: 4px; margin-top: 14px; padding-top: 8px;
    color: {MUTED}; font-size: 11px; font-weight: 700; letter-spacing: 2px;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}
QMessageBox QLabel {{ color: {TEXT}; }}
"""
