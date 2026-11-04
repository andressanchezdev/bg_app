from PIL import Image
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import (
    QImage, QPixmap, QPainter, QPen, QColor, QWheelEvent, QBrush
)


def create_checkerboard_pixmap(size=14) -> QPixmap:
    """Crea un patrón de cuadrícula ajedrezada para evidenciar la transparencia."""
    pm = QPixmap(size * 2, size * 2)
    pm.fill(QColor("#16161a"))
    p = QPainter(pm)
    p.fillRect(0, 0, size, size, QColor("#1e1e24"))
    p.fillRect(size, size, size, size, QColor("#1e1e24"))
    p.end()
    return pm


class MaskEditableCanvas(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        # Fondo con cuadrícula ajedrezada de transparencia
        self.scene.setBackgroundBrush(QBrush(create_checkerboard_pixmap(14)))

        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)

        # Capas de datos internas
        self.original_rgb = None      # QImage de la imagen RGB
        self.mask_image = None        # QImage ARGB32/RGBA8888 dedicada a la máscara alfa

        # Estado del pincel
        self.mode = "NAVIGATE"        # "NAVIGATE", "ERASE", "RESTORE"
        self.brush_size = 30
        self.is_drawing = False
        self.last_point = None

        # Configuración del motor gráfico de Qt
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self._update_drag_mode()

    def set_brush_mode(self, mode: str):
        self.mode = mode
        self._update_drag_mode()

    def set_brush_size(self, size: int):
        self.brush_size = size

    def _update_drag_mode(self):
        if self.mode == "NAVIGATE":
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self.setCursor(Qt.OpenHandCursor)
        else:
            self.setDragMode(QGraphicsView.NoDrag)
            self.setCursor(Qt.CrossCursor)

    def load_from_pil(self, pil_image: Image.Image, base_rgb_image: Image.Image = None):
        """
        Carga la imagen de PIL y prepara el lienzo y la máscara.
        Si se pasa base_rgb_image (imagen original sin recortar/sin fondo),
        se usa como fuente RGB para que el pincel restaurador recupere
        detalles reales de la foto original.
        """
        rgba = pil_image.convert("RGBA")
        width, height = rgba.size

        # 1. Imagen base RGB
        if base_rgb_image:
            base_rgb = base_rgb_image.convert("RGB")
            if base_rgb.size != (width, height):
                base_rgb = base_rgb.resize((width, height), Image.Resampling.LANCZOS)
        else:
            base_rgb = rgba.convert("RGB")

        rgb_bytes = base_rgb.tobytes()
        self.original_rgb = QImage(rgb_bytes, width, height, width * 3, QImage.Format_RGB888).copy()

        # 2. Máscara Alfa
        alpha_pil = rgba.split()[3]
        mask_rgba = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        mask_rgba.paste((255, 255, 255, 255), (0, 0, width, height), mask=alpha_pil)
        
        mask_bytes = mask_rgba.tobytes()
        self.mask_image = QImage(mask_bytes, width, height, width * 4, QImage.Format_RGBA8888).copy()

        # Dibujar composición e inicializar vista
        self.render_combined()
        self.scene.setSceneRect(0, 0, width, height)
        self.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def render_combined(self):
        """Combina la imagen original con la máscara alfa actual."""
        if self.original_rgb is None or self.mask_image is None:
            return

        w, h = self.original_rgb.width(), self.original_rgb.height()

        combined = QImage(w, h, QImage.Format_RGBA8888)
        combined.fill(Qt.transparent)

        painter = QPainter(combined)
        # Dibujar imagen base
        painter.drawImage(0, 0, self.original_rgb)
        # Aplicar la máscara Alfa mediante DestinationIn
        painter.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        painter.drawImage(0, 0, self.mask_image)
        painter.end()

        # Actualizar la escena e instruir el repintado
        self.pixmap_item.setPixmap(QPixmap.fromImage(combined))
        self.scene.update()
        self.viewport().update()

    def get_final_pil_image(self) -> Image.Image:
        """Devuelve la imagen con la transparencia aplicada lista para exportar."""
        if self.original_rgb is None or self.mask_image is None:
            return None

        w, h = self.original_rgb.width(), self.original_rgb.height()

        # Extraer el canal alfa de la máscara manipulada
        mask_pil = Image.frombytes("RGBA", (w, h), self.mask_image.bits().tobytes())
        alpha_channel = mask_pil.split()[3]

        rgb_pil = Image.frombytes("RGB", (w, h), self.original_rgb.bits().tobytes())
        rgb_pil.putalpha(alpha_channel)
        return rgb_pil

    # --- Eventos de Pincel ---
    def mousePressEvent(self, event):
        if self.mode in ("ERASE", "RESTORE") and event.button() == Qt.LeftButton:
            self.is_drawing = True
            pos = self.mapToScene(event.pos())
            self.last_point = pos
            self.apply_brush_stroke(pos, pos)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_drawing and self.mode in ("ERASE", "RESTORE"):
            pos = self.mapToScene(event.pos())
            self.apply_brush_stroke(self.last_point, pos)
            self.last_point = pos
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_drawing:
            self.is_drawing = False
            self.last_point = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def apply_brush_stroke(self, start_p: QPointF, end_p: QPointF):
        """Aplica la pincelada a la máscara Alfa."""
        if self.mask_image is None:
            return

        painter = QPainter(self.mask_image)
        painter.setRenderHint(QPainter.Antialiasing)

        if self.mode == "ERASE":
            # Borrar = Hacer transparente (Alpha 0)
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            color = QColor(0, 0, 0, 0)
        else:
            # Restaurar = Hacer opaco (Alpha 255)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            color = QColor(255, 255, 255, 255)

        pen = QPen(color, self.brush_size, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)

        if start_p == end_p:
            painter.drawPoint(start_p)
        else:
            painter.drawLine(start_p, end_p)

        painter.end()

        # Actualizar lienzo en pantalla
        self.render_combined()

    def wheelEvent(self, event: QWheelEvent):
        """Zoom interactivo con la rueda del ratón."""
        zoom_factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(zoom_factor, zoom_factor)
