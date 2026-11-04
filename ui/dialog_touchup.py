import os
from pathlib import Path
from PIL import Image, ImageOps

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QRadioButton, QButtonGroup,
    QSlider, QSpinBox, QCheckBox, QMessageBox, QApplication
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QBrush

from ui.canvas import MaskEditableCanvas, create_checkerboard_pixmap
from ui.theme import GLOBAL_THEME, COLOR_BORDER_DEFAULT, COLOR_STATUS_OK, COLOR_STATUS_ERR
from core.bg_remover import process_remove_background
from core.image_processor import export_to_webp


class AIReprocessThread(QThread):
    finished_ai = Signal(object)
    error_ai = Signal(str)

    def __init__(self, pil_image: Image.Image, session=None):
        super().__init__()
        self.pil_image = pil_image
        self.session = session

    def run(self):
        try:
            cut = process_remove_background(self.pil_image, session=self.session)
            self.finished_ai.emit(cut)
        except Exception as e:
            self.error_ai.emit(str(e))


class ImageTouchupDialog(QDialog):
    """
    Modal interactivo de retoque y re-procesamiento manual para una imagen.
    Integra el lienzo MaskEditableCanvas con herramientas de borrador, restaurador,
    ajuste de calidad WebP, fondo blanco y re-ejecución con IA.
    """

    def __init__(
        self,
        processed_path: str,
        original_path: str = None,
        ai_session=None,
        white_bg: bool = False,
        quality: int = 90,
        target_w: int = 900,
        target_h: int = 900,
        resize_mode: str = "contain",
        parent=None
    ):
        super().__init__(parent)
        self.processed_path = processed_path
        self.original_path = original_path
        self.ai_session = ai_session
        self.white_bg = white_bg
        self.quality = quality
        self.target_w = target_w
        self.target_h = target_h
        self.resize_mode = resize_mode

        self.original_pil = None
        self.current_pil = None

        self.setWindowTitle(f"Retoque y Re-procesamiento - {os.path.basename(processed_path)}")
        self.resize(980, 680)
        self.setModal(True)
        self.setStyleSheet(GLOBAL_THEME)

        self._init_ui()
        self._load_data()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 14, 18, 14)
        main_layout.setSpacing(12)

        # ---------------- BARRA SUPERIOR ----------------
        top_bar = QHBoxLayout()

        title_col = QVBoxLayout()
        lbl_subtitle = QLabel("RETOQUE MANUAL Y RE-PROCESAMIENTO")
        lbl_subtitle.setObjectName("caption")
        title_col.addWidget(lbl_subtitle)

        self.lbl_title = QLabel(os.path.basename(self.processed_path))
        self.lbl_title.setObjectName("h2")
        title_col.addWidget(self.lbl_title)
        top_bar.addLayout(title_col)

        top_bar.addStretch()

        # Medidas y peso actuales
        self.lbl_meta = QLabel("-")
        self.lbl_meta.setObjectName("caption")
        top_bar.addWidget(self.lbl_meta)

        main_layout.addLayout(top_bar)

        # ---------------- CONTENIDO CENTRAL: PANEL + LIENZO ----------------
        content_layout = QHBoxLayout()
        content_layout.setSpacing(14)

        # PANEL LATERAL DE CONTROLES
        panel = QFrame()
        panel.setObjectName("controlPanel")
        panel.setFixedWidth(270)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(14, 14, 14, 14)
        panel_layout.setSpacing(12)

        # 1. Herramientas de Edición
        lbl_tools = QLabel("HERRAMIENTAS DE MÁSCARA")
        lbl_tools.setObjectName("caption")
        panel_layout.addWidget(lbl_tools)

        self.rb_nav = QRadioButton("🖐️ Navegar / Zoom")
        self.rb_erase = QRadioButton("🧹 Pincel Borrador")
        self.rb_restore = QRadioButton("🖌️ Pincel Restaurador")
        self.rb_erase.setChecked(True)

        self.tool_group = QButtonGroup(self)
        self.tool_group.addButton(self.rb_nav, 0)
        self.tool_group.addButton(self.rb_erase, 1)
        self.tool_group.addButton(self.rb_restore, 2)
        self.tool_group.idClicked.connect(self._change_tool_mode)

        panel_layout.addWidget(self.rb_nav)
        panel_layout.addWidget(self.rb_erase)
        panel_layout.addWidget(self.rb_restore)

        # Slider de Tamaño de Pincel
        size_row = QHBoxLayout()
        lbl_size_title = QLabel("Tamaño:")
        lbl_size_title.setObjectName("body")
        size_row.addWidget(lbl_size_title)
        self.lbl_brush_px = QLabel("30 px")
        self.lbl_brush_px.setObjectName("caption")
        size_row.addWidget(self.lbl_brush_px)
        panel_layout.addLayout(size_row)

        self.slider_brush = QSlider(Qt.Horizontal)
        self.slider_brush.setRange(5, 150)
        self.slider_brush.setValue(30)
        self.slider_brush.valueChanged.connect(self._on_brush_size_changed)
        panel_layout.addWidget(self.slider_brush)

        # Botón para re-ejecutar IA desde el original
        self.btn_re_ai = QPushButton("✨ Re-aislar fondo con IA")
        self.btn_re_ai.setToolTip("Vuelve a ejecutar la red neuronal sobre la imagen original")
        self.btn_re_ai.clicked.connect(self._run_ai_reprocess)
        panel_layout.addWidget(self.btn_re_ai)

        panel_layout.addSpacing(6)

        # 2. Configuración de Salida
        lbl_out = QLabel("SALIDA Y OPTIMIZACIÓN")
        lbl_out.setObjectName("caption")
        panel_layout.addWidget(lbl_out)

        self.chk_white_bg = QCheckBox("Rellenar fondo blanco")
        self.chk_white_bg.setChecked(self.white_bg)
        self.chk_white_bg.setCursor(Qt.PointingHandCursor)
        self.chk_white_bg.toggled.connect(self._on_white_bg_toggled)
        panel_layout.addWidget(self.chk_white_bg)

        # Calidad
        q_row = QHBoxLayout()
        q_row.addWidget(QLabel("Calidad:"))
        self.spin_quality = QSpinBox()
        self.spin_quality.setRange(50, 100)
        self.spin_quality.setValue(self.quality)
        self.spin_quality.setSuffix("%")
        q_row.addWidget(self.spin_quality)
        panel_layout.addLayout(q_row)

        self.slider_quality = QSlider(Qt.Horizontal)
        self.slider_quality.setRange(50, 100)
        self.slider_quality.setValue(self.quality)
        self.slider_quality.valueChanged.connect(self.spin_quality.setValue)
        self.spin_quality.valueChanged.connect(self.slider_quality.setValue)
        panel_layout.addWidget(self.slider_quality)

        # Medidas
        dims_row = QHBoxLayout()
        dims_row.addWidget(QLabel("Medidas:"))
        self.spin_w = QSpinBox()
        self.spin_w.setRange(100, 6000)
        self.spin_w.setValue(self.target_w)
        self.spin_w.setSuffix("w")
        dims_row.addWidget(self.spin_w)

        self.spin_h = QSpinBox()
        self.spin_h.setRange(100, 6000)
        self.spin_h.setValue(self.target_h)
        self.spin_h.setSuffix("h")
        dims_row.addWidget(self.spin_h)
        panel_layout.addLayout(dims_row)

        panel_layout.addStretch()

        # Botón Guardar Cambios
        self.btn_save = QPushButton("Guardar y Actualizar")
        self.btn_save.setObjectName("primaryBtn")
        self.btn_save.setCursor(Qt.PointingHandCursor)
        self.btn_save.clicked.connect(self._save_changes)
        panel_layout.addWidget(self.btn_save)

        btn_cancel = QPushButton("Descartar")
        btn_cancel.clicked.connect(self.reject)
        panel_layout.addWidget(btn_cancel)

        content_layout.addWidget(panel)

        # LIENZO GRÁFICO INTERACTIVO
        canvas_container = QFrame()
        canvas_container.setObjectName("card")
        c_layout = QVBoxLayout(canvas_container)
        c_layout.setContentsMargins(2, 2, 2, 2)

        self.canvas = MaskEditableCanvas()
        self.canvas.set_brush_mode("ERASE")
        self.canvas.set_brush_size(30)
        if self.white_bg:
            self.canvas.scene.setBackgroundBrush(QBrush(QColor("#ffffff")))
        c_layout.addWidget(self.canvas)

        content_layout.addWidget(canvas_container, stretch=1)
        main_layout.addLayout(content_layout)

    def _on_white_bg_toggled(self, checked: bool):
        if checked:
            self.canvas.scene.setBackgroundBrush(QBrush(QColor("#ffffff")))
        else:
            self.canvas.scene.setBackgroundBrush(QBrush(create_checkerboard_pixmap(14)))

    def _load_data(self):
        # 1. Cargar la imagen procesada actual con orientación EXIF normalizada
        if os.path.exists(self.processed_path):
            try:
                raw_proc = Image.open(self.processed_path)
                self.current_pil = ImageOps.exif_transpose(raw_proc).convert("RGBA")
                w, h = self.current_pil.size
                kb = os.path.getsize(self.processed_path) / 1024.0
                self.lbl_meta.setText(f"Actual: {w} × {h} px · {kb:.1f} KB")

                # Cargar imagen original si está disponible (normalizando EXIF para evitar giros)
                if self.original_path and os.path.exists(self.original_path):
                    try:
                        raw_orig = Image.open(self.original_path)
                        self.original_pil = ImageOps.exif_transpose(raw_orig).convert("RGBA")
                    except Exception:
                        self.original_pil = None

                # Cargar la imagen procesada en el lienzo manteniendo capas 100% sincronizadas
                # (evita desfasar la máscara centrada contra el fondo crudo sin recortar)
                self.canvas.load_from_pil(self.current_pil)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"No se pudo cargar la imagen procesada:\n{e}")

    def _change_tool_mode(self, btn_id: int):
        modes = {0: "NAVIGATE", 1: "ERASE", 2: "RESTORE"}
        self.canvas.set_brush_mode(modes.get(btn_id, "NAVIGATE"))

    def _on_brush_size_changed(self, val: int):
        self.lbl_brush_px.setText(f"{val} px")
        self.canvas.set_brush_size(val)

    def _run_ai_reprocess(self):
        target_pil = self.original_pil or self.current_pil
        if not target_pil:
            QMessageBox.warning(self, "Aviso", "No hay imagen base disponible para re-procesar con IA.")
            return

        self.btn_re_ai.setEnabled(False)
        self.btn_re_ai.setText("Procesando con IA...")
        QApplication.setOverrideCursor(Qt.WaitCursor)

        self.worker = AIReprocessThread(target_pil, session=self.ai_session)
        self.worker.finished_ai.connect(self._on_ai_reprocess_done)
        self.worker.error_ai.connect(self._on_ai_reprocess_err)
        self.worker.start()

    def _on_ai_reprocess_done(self, cut_pil: Image.Image):
        QApplication.restoreOverrideCursor()
        self.btn_re_ai.setEnabled(True)
        self.btn_re_ai.setText("✨ Re-aislar fondo con IA")

        self.current_pil = cut_pil
        self.canvas.load_from_pil(self.current_pil, base_rgb_image=self.original_pil)
        QMessageBox.information(
            self,
            "IA Finalizada",
            "Fondo recalculado exitosamente con U2-Net + Refinamiento de Cavidades.\n"
            "Puedes usar el pincel borrador o restaurador para afinar cualquier detalle."
        )

    def _on_ai_reprocess_err(self, err_msg: str):
        QApplication.restoreOverrideCursor()
        self.btn_re_ai.setEnabled(True)
        self.btn_re_ai.setText("✨ Re-aislar fondo con IA")
        QMessageBox.critical(self, "Error de IA", f"No se pudo re-procesar:\n{err_msg}")

    def _save_changes(self):
        final_pil = self.canvas.get_final_pil_image()
        if not final_pil:
            return

        white_bg = self.chk_white_bg.isChecked()
        quality = self.spin_quality.value()
        w = self.spin_w.value()
        h = self.spin_h.value()

        try:
            resize_cfg = {"enabled": True, "width": w, "height": h, "mode": self.resize_mode}
            export_to_webp(
                pil_image=final_pil,
                output_path=self.processed_path,
                quality=quality,
                method=6,
                resize_config=resize_cfg,
                white_bg=white_bg
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error al guardar", f"No se pudo guardar la imagen:\n{e}")

