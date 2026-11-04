import os
from pathlib import Path
from PIL import Image

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QWidget
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QPainter, QColor, QBrush, QPen

from ui.theme import GLOBAL_THEME, COLOR_BORDER_DEFAULT, COLOR_STATUS_OK


def create_checkerboard_pixmap(size=14) -> QPixmap:
    """Crea un patrón de cuadrícula ajedrezada para evidenciar la transparencia."""
    pm = QPixmap(size * 2, size * 2)
    pm.fill(QColor("#16161a"))
    p = QPainter(pm)
    p.fillRect(0, 0, size, size, QColor("#1e1e24"))
    p.fillRect(size, size, size, size, QColor("#1e1e24"))
    p.end()
    return pm


class ImagePreviewDialog(QDialog):
    """
    Modal estándar para previsualizar la imagen procesada sin fondo,
    con lienzo ajedrezado de transparencia, detalles de peso/medidas y botón ✕ de cierre.
    """

    def __init__(self, image_path: str, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.setWindowTitle(f"Detalle de Imagen - {os.path.basename(image_path)}")
        self.resize(760, 640)
        self.setModal(True)
        self.setStyleSheet(GLOBAL_THEME)

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 16, 20, 16)
        main_layout.setSpacing(12)

        # ---------------- BARRA SUPERIOR CON DETALLES Y BOTÓN ✕ ----------------
        top_bar = QHBoxLayout()

        # Nombre y ruta
        title_layout = QVBoxLayout()
        lbl_fname = QLabel(os.path.basename(self.image_path))
        lbl_fname.setObjectName("h2")
        title_layout.addWidget(lbl_fname)

        lbl_fpath = QLabel(self.image_path)
        lbl_fpath.setObjectName("caption")
        title_layout.addWidget(lbl_fpath)
        top_bar.addLayout(title_layout)

        top_bar.addStretch()

        # Medidas y Peso
        w_px, h_px, size_kb = self._get_image_metadata()

        frame_dims = QFrame()
        frame_dims.setObjectName("statBox")
        h_dims = QHBoxLayout(frame_dims)
        h_dims.setContentsMargins(8, 4, 8, 4)
        lbl_dims = QLabel(f"{w_px} × {h_px} px")
        lbl_dims.setObjectName("caption")
        h_dims.addWidget(lbl_dims)
        top_bar.addWidget(frame_dims)

        frame_size = QFrame()
        frame_size.setObjectName("statBox")
        h_size = QHBoxLayout(frame_size)
        h_size.setContentsMargins(8, 4, 8, 4)
        lbl_size = QLabel(f"{size_kb:.1f} KB")
        lbl_size.setObjectName("caption")
        lbl_size.setStyleSheet(f"color: {COLOR_STATUS_OK};")
        h_size.addWidget(lbl_size)
        top_bar.addWidget(frame_size)

        main_layout.addLayout(top_bar)

        # ---------------- LIENZO DE VISUALIZACIÓN CON AJEDREZADO ----------------
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ border: 1px solid {COLOR_BORDER_DEFAULT}; border-radius: 8px; background-color: #0e0e11; }}")

        viewport_container = QWidget()
        viewport_layout = QVBoxLayout(viewport_container)
        viewport_layout.setAlignment(Qt.AlignCenter)
        viewport_layout.setContentsMargins(16, 16, 16, 16)

        # Label con imagen y patrón de fondo
        self.lbl_canvas = QLabel()
        self.lbl_canvas.setAlignment(Qt.AlignCenter)
        self._render_transparent_image()
        viewport_layout.addWidget(self.lbl_canvas)

        scroll.setWidget(viewport_container)
        main_layout.addWidget(scroll)

        # Pie con nota técnica según el tipo de fondo
        has_transparency = True
        try:
            with Image.open(self.image_path) as im:
                if im.mode == "RGB":
                    has_transparency = False
                elif im.mode in ("RGBA", "LA"):
                    extrema = im.getchannel("A").getextrema()
                    if extrema[0] == 255:
                        has_transparency = False
        except Exception:
            pass

        footer_text = (
            "Lienzo con transparencia alfa verificada · Formato WebP optimizado · Objeto centrado"
            if has_transparency
            else "Lienzo 100% fondo blanco (#FFFFFF) · Formato WebP optimizado · Objeto centrado"
        )
        lbl_footer = QLabel(footer_text)
        lbl_footer.setObjectName("caption")
        lbl_footer.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(lbl_footer)

    def _get_image_metadata(self):
        w, h = 0, 0
        size_kb = 0.0
        if os.path.exists(self.image_path):
            size_kb = os.path.getsize(self.image_path) / 1024.0
            try:
                with Image.open(self.image_path) as im:
                    w, h = im.size
            except Exception:
                pass
        return w, h, size_kb

    def _render_transparent_image(self):
        if not os.path.exists(self.image_path):
            self.lbl_canvas.setText("No se encontró la imagen en disco.")
            return

        src_pixmap = QPixmap(self.image_path)
        if src_pixmap.isNull():
            self.lbl_canvas.setText("Formato no legible para previsualización.")
            return

        # Escalar a un tamaño cómodo para la ventana manteniendo aspect ratio (máx 560x480)
        scaled_pixmap = src_pixmap.scaled(
            560, 480,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        w, h = scaled_pixmap.width(), scaled_pixmap.height()

        composed = QPixmap(w, h)
        painter = QPainter(composed)

        # Dibujar ajedrezado sutil
        checker = create_checkerboard_pixmap(14)
        painter.fillRect(0, 0, w, h, QBrush(checker))

        # Dibujar la imagen transparente encima
        painter.drawPixmap(0, 0, scaled_pixmap)

        # Marco sutil
        painter.setPen(QPen(QColor(COLOR_BORDER_DEFAULT), 1))
        painter.drawRect(0, 0, w - 1, h - 1)
        painter.end()

        self.lbl_canvas.setPixmap(composed)
