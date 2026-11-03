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
QMainWindow, QDialog, QWidget {{
    background-color: {COLOR_BG_ROOT};
    color: {COLOR_TEXT_PRIMARY};
    font-family: {FONT_FAMILY_BASE};
    font-size: 12px;
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
    font-size: 17px;
    font-weight: 600;
    color: {COLOR_TEXT_PRIMARY};
}}
QLabel#h2 {{
    font-size: 14px;
    font-weight: 600;
    color: {COLOR_TEXT_PRIMARY};
}}
QLabel#body {{
    font-size: 12px;
    color: {COLOR_TEXT_SECONDARY};
}}
QLabel#caption {{
    font-size: 11px;
    font-family: {FONT_FAMILY_MONO};
    color: {COLOR_TEXT_MUTED};
    letter-spacing: 0.5px;
}}
QLabel#metricTitle {{
    font-size: 11px;
    font-family: {FONT_FAMILY_MONO};
    color: {COLOR_TEXT_MUTED};
}}
QLabel#metricValue {{
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
    max-width: 36px;
    min-height: 22px;
    max-height: 24px;
}}
QPushButton#actionEye:hover {{
    background-color: {COLOR_BG_HOVER};
    border-color: {COLOR_BORDER_HOVER};
    color: #ffffff;
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
"""

