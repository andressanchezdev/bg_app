import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QCheckBox, QSlider, QSpinBox,
    QComboBox
)
from PySide6.QtCore import Qt
import config
from ui.theme import GLOBAL_THEME, COLOR_BORDER_DEFAULT, COLOR_STATUS_OK


class BatchProcessConfigDialog(QDialog):
    """
    Modal de configuración de procesamiento en lote.
    Permite al usuario definir las opciones clave antes de iniciar:
      - Rellenar fondo blanco (o mantener transparencia).
      - Calidad WebP (%).
      - Estandarización de medidas y centrado.
      - Validación y subida directa a Google Cloud Storage.
    """

    def __init__(self, initial_config: dict = None, total_images: int = 0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuración de Procesamiento")
        self.resize(540, 520)
        self.setModal(True)
        self.setStyleSheet(GLOBAL_THEME)

        cfg = initial_config or {}
        self.white_bg_initial = cfg.get("white_bg", False)
        self.quality_initial = cfg.get("quality", 90)
        self.resize_enabled_initial = cfg.get("resize_enabled", True)
        self.target_width_initial = cfg.get("target_width", 900)
        self.target_height_initial = cfg.get("target_height", 900)
        self.resize_mode_initial = cfg.get("resize_mode", "contain")
        self.upload_gcs_initial = cfg.get("upload_to_gcs", getattr(config, "CLOUD_UPLOAD_ENABLED", False))
        self.total_images = total_images

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Encabezado
        lbl_step = QLabel("CONFIGURACIÓN PRE-PROCESO")
        lbl_step.setObjectName("caption")
        layout.addWidget(lbl_step)

        lbl_title = QLabel("Parámetros del lote de imágenes")
        lbl_title.setObjectName("h1")
        layout.addWidget(lbl_title)

        subtitle_text = "Personaliza cómo se procesarán y distribuirán las imágenes."
        if self.total_images > 0:
            subtitle_text = f"Se aplicará a las {self.total_images} imágenes identificadas en el lote."
        lbl_subtitle = QLabel(subtitle_text)
        lbl_subtitle.setObjectName("body")
        layout.addWidget(lbl_subtitle)

        # ---------------- TARJETA 1: FONDO DE SALIDA ----------------
        card_bg = QFrame()
        card_bg.setObjectName("statBox")
        layout_bg = QVBoxLayout(card_bg)
        layout_bg.setSpacing(6)

        lbl_sec1 = QLabel("FONDO DE SALIDA")
        lbl_sec1.setObjectName("caption")
        layout_bg.addWidget(lbl_sec1)

        self.chk_white_bg = QCheckBox("Rellenar fondo blanco (Catálogo / E-commerce)")
        self.chk_white_bg.setChecked(self.white_bg_initial)
        self.chk_white_bg.setCursor(Qt.PointingHandCursor)
        layout_bg.addWidget(self.chk_white_bg)

        self.lbl_bg_desc = QLabel(
            "Desmarcado: Conserva transparencia pura (canal alfa WebP).\n"
            "Marcado: Rellena el lienzo con fondo blanco uniforme (#FFFFFF)."
        )
        self.lbl_bg_desc.setObjectName("caption")
        layout_bg.addWidget(self.lbl_bg_desc)
        layout.addWidget(card_bg)

        # ---------------- TARJETA 2: CALIDAD WEBP ----------------
        card_quality = QFrame()
        card_quality.setObjectName("statBox")
        layout_quality = QVBoxLayout(card_quality)
        layout_quality.setSpacing(8)

        lbl_sec2 = QLabel("CALIDAD Y OPTIMIZACIÓN WEBP")
        lbl_sec2.setObjectName("caption")
        layout_quality.addWidget(lbl_sec2)

        quality_row = QHBoxLayout()
        quality_row.setSpacing(12)

        lbl_q_title = QLabel("Calidad de compresión:")
        lbl_q_title.setObjectName("body")
        quality_row.addWidget(lbl_q_title)

        self.slider_quality = QSlider(Qt.Horizontal)
        self.slider_quality.setRange(50, 100)
        self.slider_quality.setValue(self.quality_initial)
        quality_row.addWidget(self.slider_quality)

        self.spin_quality = QSpinBox()
        self.spin_quality.setRange(50, 100)
        self.spin_quality.setValue(self.quality_initial)
        self.spin_quality.setSuffix("%")
        self.spin_quality.setFixedWidth(75)
        quality_row.addWidget(self.spin_quality)

        self.slider_quality.valueChanged.connect(self.spin_quality.setValue)
        self.spin_quality.valueChanged.connect(self.slider_quality.setValue)

        layout_quality.addLayout(quality_row)
        layout.addWidget(card_quality)

        # ---------------- TARJETA 3: MEDIDAS Y CENTRADO ----------------
        card_dims = QFrame()
        card_dims.setObjectName("statBox")
        layout_dims = QVBoxLayout(card_dims)
        layout_dims.setSpacing(8)

        lbl_sec3 = QLabel("DIMENSIONES Y CENTRADO")
        lbl_sec3.setObjectName("caption")
        layout_dims.addWidget(lbl_sec3)

        self.chk_resize = QCheckBox("Estandarizar dimensiones y centrar el objeto")
        self.chk_resize.setChecked(self.resize_enabled_initial)
        self.chk_resize.setCursor(Qt.PointingHandCursor)
        self.chk_resize.toggled.connect(self._toggle_resize_fields)
        layout_dims.addWidget(self.chk_resize)

        dims_row = QHBoxLayout()
        dims_row.setSpacing(8)

        dims_row.addWidget(QLabel("Preset:"))
        self.combo_presets = QComboBox()
        self.combo_presets.addItem("900 × 900 (Estándar Web)", (900, 900))
        self.combo_presets.addItem("1080 × 1080 (Cuadrado HD)", (1080, 1080))
        self.combo_presets.addItem("1200 × 1200 (Gran Formato)", (1200, 1200))
        self.combo_presets.addItem("Personalizado", None)
        self.combo_presets.currentIndexChanged.connect(self._on_preset_changed)
        dims_row.addWidget(self.combo_presets)

        dims_row.addWidget(QLabel("Ancho:"))
        self.spin_w = QSpinBox()
        self.spin_w.setRange(100, 6000)
        self.spin_w.setValue(self.target_width_initial)
        self.spin_w.setSuffix(" px")
        dims_row.addWidget(self.spin_w)

        dims_row.addWidget(QLabel("Alto:"))
        self.spin_h = QSpinBox()
        self.spin_h.setRange(100, 6000)
        self.spin_h.setValue(self.target_height_initial)
        self.spin_h.setSuffix(" px")
        dims_row.addWidget(self.spin_h)

        layout_dims.addLayout(dims_row)
        layout.addWidget(card_dims)

        # ---------------- TARJETA 4: SUBIDA A GCP Y VALIDACIÓN ----------------
        card_gcp = QFrame()
        card_gcp.setObjectName("statBox")
        layout_gcp = QVBoxLayout(card_gcp)
        layout_gcp.setSpacing(6)

        lbl_sec4 = QLabel("DESTINO EN LA NUBE (GOOGLE CLOUD)")
        lbl_sec4.setObjectName("caption")
        layout_gcp.addWidget(lbl_sec4)

        self.chk_upload_gcs = QCheckBox("Subir a Google Cloud Storage validando contra el Bucket")
        self.chk_upload_gcs.setChecked(self.upload_gcs_initial)
        self.chk_upload_gcs.setCursor(Qt.PointingHandCursor)
        layout_gcp.addWidget(self.chk_upload_gcs)

        lbl_gcp_hint = QLabel(
            "• Valida cada carpeta contra las existentes en GCP. Si coincide exactamente, aloja las imágenes dentro.\n"
            "• Si es imagen suelta, se almacena en la raíz de la ruta configurada.\n"
            "• Si una carpeta NO existe en el bucket, se bloquea su subida para proteger el catálogo."
        )
        lbl_gcp_hint.setObjectName("caption")
        layout_gcp.addWidget(lbl_gcp_hint)
        layout.addWidget(card_gcp)

        layout.addStretch()

        # ---------------- BOTONES DE CONFIRMACIÓN ----------------
        bottom_bar = QHBoxLayout()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        bottom_bar.addWidget(btn_cancel)

        bottom_bar.addStretch()

        btn_confirm = QPushButton("Confirmar configuración")
        btn_confirm.setObjectName("primaryBtn")
        btn_confirm.setCursor(Qt.PointingHandCursor)
        btn_confirm.clicked.connect(self.accept)
        bottom_bar.addWidget(btn_confirm)

        layout.addLayout(bottom_bar)

    def _toggle_resize_fields(self, enabled: bool):
        self.combo_presets.setEnabled(enabled)
        self.spin_w.setEnabled(enabled)
        self.spin_h.setEnabled(enabled)

    def _on_preset_changed(self, idx: int):
        data = self.combo_presets.currentData()
        if data:
            self.spin_w.setValue(data[0])
            self.spin_h.setValue(data[1])

    def get_config(self) -> dict:
        return {
            "white_bg": self.chk_white_bg.isChecked(),
            "quality": self.spin_quality.value(),
            "resize_enabled": self.chk_resize.isChecked(),
            "target_width": self.spin_w.value(),
            "target_height": self.spin_h.value(),
            "resize_mode": "contain",
            "upload_to_gcs": self.chk_upload_gcs.isChecked()
        }
