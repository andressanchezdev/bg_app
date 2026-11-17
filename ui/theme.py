"""
SISTEMA DE DISEÑO CENTRALIZADO (DESIGN SYSTEM)
Paleta de color unificada, escala tipográfica modular y estilos estándar.
"""

# -----------------------------------------------------------------------------
# TOKENS DE COLOR
# -----------------------------------------------------------------------------
COLOR_BG_ROOT = "#0e0e11"         # Fondo base de la aplicación
COLOR_BG_SURFACE = "#16161a"      # Superficie de contenedores y cards
COLOR_BG_HOVER = "#1c1c22"        # Superficie en estado hover
COLOR_BG_ACTIVE = "#22222a"       # Superficie activa o seleccionada

COLOR_BORDER_DEFAULT = "#25252e"   # Borde estándar sutil
COLOR_BORDER_HOVER = "#3e3e4a"     # Borde en hover / enfoque

COLOR_TEXT_PRIMARY = "#f4f4f5"     # Texto principal de alto contraste
COLOR_TEXT_SECONDARY = "#9e9ea8"   # Texto secundario, subtítulos y labels
COLOR_TEXT_MUTED = "#555560"       # Texto desactivado, notas y placeholders

COLOR_ACCENT = "#f4f4f5"           # Botón de acción principal
COLOR_ACCENT_TEXT = "#0e0e11"      # Texto sobre acento principal

COLOR_STATUS_OK = "#4ade80"        # Éxito / Operativo (Verde)
COLOR_STATUS_ERR = "#f87171"       # Error / Alerta (Rojo suave)

# -----------------------------------------------------------------------------
# PILAS TIPOGRÁFICAS
# -----------------------------------------------------------------------------
FONT_FAMILY_BASE = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
FONT_FAMILY_MONO = "'JetBrains Mono', Consolas, 'Courier New', monospace"

# -----------------------------------------------------------------------------
# HOJA DE ESTILOS MAESTRA (GLOBAL STYLESHEET)
# -----------------------------------------------------------------------------
GLOBAL_THEME = f"""
QMainWindow, QDialog {{
    background-color: {COLOR_BG_ROOT};
    color: {COLOR_TEXT_PRIMARY};
    font-family: {FONT_FAMILY_BASE};
    font-size: 12px;
}}

QWidget {{
    color: {COLOR_TEXT_PRIMARY};
    font-family: {FONT_FAMILY_BASE};
    font-size: 12px;
}}

QWidget#centralWidget {{
    background-color: {COLOR_BG_ROOT};
}}

/* --- LABELS Y CONTROLES TRANSPARENTES (SIN FRANJAS OSCURAS) --- */
QLabel {{
    background-color: transparent;
    background: transparent;
}}
QCheckBox, QRadioButton {{
    background-color: transparent;
    background: transparent;
}}

/* --- CONTENEDORES Y PANELES --- */
QFrame#card {{
    background-color: {COLOR_BG_SURFACE};
    border: 1px solid {COLOR_BORDER_DEFAULT};
    border-radius: 8px;
}}
QFrame#card:hover {{
    background-color: {COLOR_BG_HOVER};
    border: 1px solid {COLOR_BORDER_HOVER};
}}
QFrame#statBox {{
    background-color: {COLOR_BG_SURFACE};
    border: 1px solid {COLOR_BORDER_DEFAULT};
    border-radius: 6px;
    padding: 10px;
}}
QFrame#controlPanel {{
    background-color: {COLOR_BG_SURFACE};
    border: 1px solid {COLOR_BORDER_DEFAULT};
    border-radius: 8px;
    padding: 12px;
}}

/* --- TIPOGRAFÍA SEMÁNTICA (QLabel) --- */
QLabel#h1 {{
    background-color: transparent;
    font-size: 17px;
    font-weight: 600;
    color: {COLOR_TEXT_PRIMARY};
}}
QLabel#h2 {{
    background-color: transparent;
    font-size: 14px;
    font-weight: 600;
    color: {COLOR_TEXT_PRIMARY};
}}
QLabel#body {{
    background-color: transparent;
    font-size: 12px;
    color: {COLOR_TEXT_SECONDARY};
}}
QLabel#caption {{
    background-color: transparent;
    font-size: 11px;
    font-family: {FONT_FAMILY_MONO};
    color: {COLOR_TEXT_MUTED};
    letter-spacing: 0.5px;
}}
QLabel#metricTitle {{
    background-color: transparent;
    font-size: 11px;
    font-family: {FONT_FAMILY_MONO};
    color: {COLOR_TEXT_MUTED};
}}
QLabel#metricValue {{
    background-color: transparent;
    font-size: 16px;
    font-family: {FONT_FAMILY_MONO};
    font-weight: 600;
    color: {COLOR_TEXT_PRIMARY};
}}

/* --- BOTONES --- */
QPushButton {{
    background-color: {COLOR_BG_SURFACE};
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid {COLOR_BORDER_DEFAULT};
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: {COLOR_BG_HOVER};
    border-color: {COLOR_BORDER_HOVER};
}}
QPushButton:disabled {{
    background-color: {COLOR_BG_SURFACE};
    color: {COLOR_TEXT_MUTED};
    border-color: {COLOR_BORDER_DEFAULT};
}}
QPushButton#primaryBtn {{
    background-color: {COLOR_ACCENT};
    color: {COLOR_ACCENT_TEXT};
    border: 1px solid {COLOR_ACCENT};
    font-weight: 600;
}}
QPushButton#primaryBtn:hover {{
    background-color: #e4e4e7;
    border-color: #e4e4e7;
}}
QPushButton#flatBtn {{
    background-color: transparent;
    border: none;
    color: {COLOR_TEXT_SECONDARY};
    padding: 4px 8px;
}}
QPushButton#flatBtn:hover {{
    color: {COLOR_TEXT_PRIMARY};
    text-decoration: underline;
}}
QPushButton#actionBtn {{
    background-color: {COLOR_BG_SURFACE};
    border: 1px solid {COLOR_BORDER_DEFAULT};
    border-radius: 4px;
    padding: 3px 8px;
    font-size: 11px;
    color: {COLOR_TEXT_PRIMARY};
}}
QPushButton#actionBtn:hover {{
    background-color: {COLOR_BG_HOVER};
    border-color: {COLOR_BORDER_HOVER};
}}
QPushButton#actionEye {{
    background-color: {COLOR_BG_SURFACE};
    border: 1px solid {COLOR_BORDER_DEFAULT};
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 13px;
    color: {COLOR_TEXT_PRIMARY};
    min-width: 28px;
    max-width: 34px;
    min-height: 22px;
    max-height: 24px;
}}
QPushButton#actionEye:hover {{
    background-color: {COLOR_BG_HOVER};
    border-color: {COLOR_BORDER_HOVER};
    color: #ffffff;
}}
QPushButton#actionReload {{
    background-color: {COLOR_BG_SURFACE};
    border: 1px solid {COLOR_BORDER_DEFAULT};
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 13px;
    color: {COLOR_TEXT_PRIMARY};
    min-width: 28px;
    max-width: 34px;
    min-height: 22px;
    max-height: 24px;
}}
QPushButton#actionReload:hover {{
    background-color: {COLOR_BG_HOVER};
    border-color: {COLOR_BORDER_HOVER};
    color: #60a5fa;
}}
QPushButton#actionDelete {{
    background-color: {COLOR_BG_SURFACE};
    border: 1px solid {COLOR_BORDER_DEFAULT};
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 13px;
    color: {COLOR_TEXT_PRIMARY};
    min-width: 28px;
    max-width: 34px;
    min-height: 22px;
    max-height: 24px;
}}
QPushButton#actionDelete:hover {{
    background-color: {COLOR_BG_HOVER};
    border-color: rgba(248, 113, 113, 0.5);
    color: {COLOR_STATUS_ERR};
}}
QPushButton#homeBtn {{
    background-color: {COLOR_BG_SURFACE};
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid {COLOR_BORDER_DEFAULT};
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 500;
}}
QPushButton#homeBtn:hover {{
    background-color: {COLOR_BG_HOVER};
    border-color: {COLOR_BORDER_HOVER};
}}
QPushButton#closeBtn {{
    background-color: transparent;
    border: 1px solid {COLOR_BORDER_DEFAULT};
    border-radius: 4px;
    color: {COLOR_TEXT_SECONDARY};
    font-size: 12px;
    font-weight: bold;
    padding: 2px 8px;
}}
QPushButton#closeBtn:hover {{
    background-color: {COLOR_BG_HOVER};
    color: {COLOR_TEXT_PRIMARY};
    border-color: {COLOR_BORDER_HOVER};
}}

/* --- FORMULARIOS, INPUTS Y TABLAS --- */
QLineEdit, QSpinBox, QComboBox {{
    background-color: {COLOR_BG_SURFACE};
    border: 1px solid {COLOR_BORDER_DEFAULT};
    border-radius: 6px;
    padding: 5px 8px;
    color: {COLOR_TEXT_PRIMARY};
    font-size: 12px;
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border: 1px solid {COLOR_BORDER_HOVER};
}}
QTableWidget {{
    background-color: {COLOR_BG_SURFACE};
    border: 1px solid {COLOR_BORDER_DEFAULT};
    border-radius: 6px;
    gridline-color: {COLOR_BG_ROOT};
    font-family: {FONT_FAMILY_MONO};
    font-size: 11px;
}}
QHeaderView::section {{
    background-color: {COLOR_BG_HOVER};
    color: {COLOR_TEXT_SECONDARY};
    border: none;
    border-bottom: 1px solid {COLOR_BORDER_DEFAULT};
    padding: 6px;
    font-size: 11px;
    font-weight: 600;
}}
QProgressBar {{
    background-color: {COLOR_BG_SURFACE};
    border: none;
    border-radius: 3px;
    height: 6px;
    text-align: center;
}}
QProgressBar::chunk {{
    background-color: {COLOR_TEXT_PRIMARY};
    border-radius: 3px;
}}
QGroupBox {{
    border: 1px solid {COLOR_BORDER_DEFAULT};
    border-radius: 6px;
    margin-top: 10px;
    font-weight: 600;
    color: {COLOR_TEXT_PRIMARY};
    font-size: 12px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}}

/* --- SUPERFICIES QUE TOMABAN EL FONDO DE WINDOWS (blanco en modo claro) --- */
QMessageBox {{
    background-color: {COLOR_BG_ROOT};
}}
QScrollArea, QScrollArea > QWidget > QWidget {{
    background-color: {COLOR_BG_ROOT};
}}
QTextEdit, QPlainTextEdit, QListView, QListWidget, QTreeView {{
    background-color: {COLOR_BG_SURFACE};
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid {COLOR_BORDER_DEFAULT};
    border-radius: 6px;
}}
QComboBox QAbstractItemView {{
    background-color: {COLOR_BG_SURFACE};
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid {COLOR_BORDER_HOVER};
    selection-background-color: {COLOR_BG_ACTIVE};
    selection-color: {COLOR_TEXT_PRIMARY};
    outline: 0;
}}
QMenu {{
    background-color: {COLOR_BG_SURFACE};
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid {COLOR_BORDER_DEFAULT};
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 18px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background-color: {COLOR_BG_ACTIVE};
}}
QMenu::item:disabled {{
    color: {COLOR_TEXT_MUTED};
}}
QScrollBar:vertical {{
    background: {COLOR_BG_ROOT};
    width: 10px;
    margin: 0;
}}
QScrollBar:horizontal {{
    background: {COLOR_BG_ROOT};
    height: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: {COLOR_BORDER_HOVER};
    border-radius: 4px;
    min-height: 24px;
    min-width: 24px;
}}
QScrollBar::handle:hover {{
    background: {COLOR_TEXT_MUTED};
}}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
    background: none;
    border: none;
    width: 0;
    height: 0;
}}
QToolTip {{
    background-color: {COLOR_BG_SURFACE};
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid {COLOR_BORDER_HOVER};
    padding: 4px 6px;
}}
"""


def apply_app_theme(app) -> None:
    """
    Paleta oscura de respaldo para toda la aplicación: cualquier control o ventana emergente
    que la hoja de estilos no cubra deja de heredar los colores claros de Windows.
    """
    from PySide6.QtGui import QColor, QPalette

    pal = QPalette()
    roles = {
        QPalette.Window: COLOR_BG_ROOT,
        QPalette.WindowText: COLOR_TEXT_PRIMARY,
        QPalette.Base: COLOR_BG_SURFACE,
        QPalette.AlternateBase: COLOR_BG_HOVER,
        QPalette.Text: COLOR_TEXT_PRIMARY,
        QPalette.Button: COLOR_BG_SURFACE,
        QPalette.ButtonText: COLOR_TEXT_PRIMARY,
        QPalette.ToolTipBase: COLOR_BG_SURFACE,
        QPalette.ToolTipText: COLOR_TEXT_PRIMARY,
        QPalette.Highlight: COLOR_BG_ACTIVE,
        QPalette.HighlightedText: COLOR_TEXT_PRIMARY,
        QPalette.PlaceholderText: COLOR_TEXT_MUTED,
    }
    for role, color in roles.items():
        pal.setColor(role, QColor(color))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor(COLOR_TEXT_MUTED))
    app.setPalette(pal)
    app.setStyleSheet(GLOBAL_THEME)

