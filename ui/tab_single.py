import os
import config
from PIL import Image

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIF_AVAILABLE = True
except ImportError:
    HEIF_AVAILABLE = False

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QFileDialog,
    QSlider, QLabel, QGroupBox, QMessageBox, QRadioButton, QButtonGroup,
    QCheckBox, QLineEdit, QApplication
)
from PySide6.QtCore import Qt

from ui.canvas import MaskEditableCanvas
from ui.resize_group import ResizeConfigGroup
from core.bg_remover import AIRemoverWorker
from core.image_processor import export_to_webp
from services.cloud_storage import CloudStorageService


class SingleTabWidget(QWidget):
    def __init__(self, ai_session, parent=None):
        super().__init__(parent)
        self.ai_session = ai_session
        self.current_pil_image = None
        self.current_file_path = None  # Para rastrear la ruta y extraer la carpeta origen

        # Inicializar el servicio de nube con los parámetros de config.py
        base_folder_gcs = getattr(config, "GCS_BASE_FOLDER", "")
        self.cloud_service = CloudStorageService(
            bucket_name=config.GCS_BUCKET_NAME,
            base_folder=base_folder_gcs
        )

        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)

        # Panel Izquierdo
        control_panel = QVBoxLayout()
        control_panel.setAlignment(Qt.AlignTop)

        self.btn_load = QPushButton("📁 Cargar Imagen")
        self.btn_load.clicked.connect(self.load_image)
        control_panel.addWidget(self.btn_load)

        self.btn_ai = QPushButton("✨ Eliminar Fondo (IA)")
        self.btn_ai.setEnabled(False)
        self.btn_ai.clicked.connect(self.process_ai)
        control_panel.addWidget(self.btn_ai)

        # Pinceles
        tool_group = QGroupBox("Herramientas de Edición")
        tool_layout = QVBoxLayout(tool_group)
        self.rb_nav = QRadioButton("🖐️ Navegar / Zoom")
        self.rb_erase = QRadioButton("🧹 Pincel Borrador")
        self.rb_restore = QRadioButton("🖌️ Pincel Restaurador")
        self.rb_nav.setChecked(True)

        self.btn_tool_group = QButtonGroup(self)
        self.btn_tool_group.addButton(self.rb_nav, 0)
        self.btn_tool_group.addButton(self.rb_erase, 1)
        self.btn_tool_group.addButton(self.rb_restore, 2)
        self.btn_tool_group.idClicked.connect(self._change_tool_mode)

        tool_layout.addWidget(self.rb_nav)
        tool_layout.addWidget(self.rb_erase)
        tool_layout.addWidget(self.rb_restore)

        tool_layout.addWidget(QLabel("Tamaño del Pincel:"))
        self.slider_brush = QSlider(Qt.Horizontal)
        self.slider_brush.setRange(5, 200)
        self.slider_brush.setValue(30)
        self.slider_brush.valueChanged.connect(self._update_brush_size)
        tool_layout.addWidget(self.slider_brush)

        self.lbl_brush_size = QLabel("30 px")
        tool_layout.addWidget(self.lbl_brush_size)
        control_panel.addWidget(tool_group)

        # Grupo Redimensionar
        self.resize_group = ResizeConfigGroup(show_aspect_ratio=True)
        control_panel.addWidget(self.resize_group)

        # Exportar WebP y GCP
        webp_group = QGroupBox("Exportación y Cloud")
        webp_layout = QVBoxLayout(webp_group)

        # Checkbox Fondo Blanco
        self.chk_white_bg = QCheckBox("Rellenar fondo blanco")
        self.chk_white_bg.setChecked(True)
        webp_layout.addWidget(self.chk_white_bg)

        # Checkbox Subir a GCP
        self.chk_upload_gcs = QCheckBox("Subir a Google Cloud Storage")
        self.chk_upload_gcs.setChecked(getattr(config, "CLOUD_UPLOAD_ENABLED", False))
        webp_layout.addWidget(self.chk_upload_gcs)

        webp_layout.addWidget(QLabel("Calidad (1 - 100):"))
        self.slider_quality = QSlider(Qt.Horizontal)
        self.slider_quality.setRange(1, 100)
        self.slider_quality.setValue(getattr(config, "DEFAULT_WEBP_QUALITY", 85))
        self.slider_quality.valueChanged.connect(
            lambda v: self.lbl_quality.setText(f"Calidad: {v}")
        )
        webp_layout.addWidget(self.slider_quality)

        self.lbl_quality = QLabel(f"Calidad: {getattr(config, 'DEFAULT_WEBP_QUALITY', 85)}")
        webp_layout.addWidget(self.lbl_quality)

        # Campo Cloud URL
        webp_layout.addWidget(QLabel("Cloud URL:"))
        url_layout = QHBoxLayout()
        self.txt_cloud_url = QLineEdit()
        self.txt_cloud_url.setReadOnly(True)
        self.txt_cloud_url.setPlaceholderText("URL de GCP aparecerá aquí...")
        url_layout.addWidget(self.txt_cloud_url)

        self.btn_copy_url = QPushButton("📋")
        self.btn_copy_url.setFixedWidth(30)
        self.btn_copy_url.setToolTip("Copiar URL")
        self.btn_copy_url.clicked.connect(self._copy_cloud_url)
        url_layout.addWidget(self.btn_copy_url)
        webp_layout.addLayout(url_layout)

        self.btn_export = QPushButton("💾 Exportar a .WebP")
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self.export_webp)
        webp_layout.addWidget(self.btn_export)

        control_panel.addWidget(webp_group)

        self.lbl_status = QLabel("Estado: Esperando imagen.")
        control_panel.addWidget(self.lbl_status)

        control_container = QWidget()
        control_container.setLayout(control_panel)
        control_container.setFixedWidth(320)
        layout.addWidget(control_container)

        # Canvas
        self.canvas = MaskEditableCanvas()
        layout.addWidget(self.canvas)

    def load_image(self, file_path: str = None):
        if not file_path:
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Seleccionar Imagen",
                "",
                "Imágenes (*.png *.jpg *.jpeg *.bmp *.webp *.heic *.HEIC *.heif *.HEIF)",
            )

        if not file_path or not os.path.exists(file_path):
            return

        # Validar si el usuario seleccionó HEIC pero falta la librería
        is_heic = file_path.lower().endswith((".heic", ".heif"))
        if is_heic and not HEIF_AVAILABLE:
            QMessageBox.warning(
                self,
                "Formato no soportado",
                "Para abrir archivos HEIC necesitas instalar el módulo:\n\n"
                "python -m pip install pillow-heif",
            )
            return

        try:
            self.current_file_path = file_path
            self.current_pil_image = Image.open(file_path).convert("RGBA")

            w, h = self.current_pil_image.size
            self.resize_group.set_original_dimensions(w, h)

            self.canvas.load_from_pil(self.current_pil_image)
            self.btn_ai.setEnabled(True)
            self.btn_export.setEnabled(True)
            self.txt_cloud_url.clear()
            self.lbl_status.setText(f"Cargada: {os.path.basename(file_path)}")

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error al cargar imagen",
                f"No se pudo abrir el archivo:\n{e}",
            )

    def process_ai(self):
        if not self.current_pil_image:
            return

        self.lbl_status.setText("Procesando con IA...")
        self.btn_ai.setEnabled(False)

        self.worker = AIRemoverWorker(self.current_pil_image, self.ai_session)
        self.worker.finished.connect(self._on_ai_success)
        self.worker.error.connect(self._on_ai_error)
        self.worker.start()

    def _on_ai_success(self, output_pil):
        self.canvas.load_from_pil(output_pil)
        self.lbl_status.setText("Fondo eliminado. Retoque disponible.")
        self.btn_ai.setEnabled(True)

    def _on_ai_error(self, err_msg):
        QMessageBox.critical(self, "Error", f"Error de IA: {err_msg}")
        self.lbl_status.setText("Error en procesamiento.")
        self.btn_ai.setEnabled(True)

    def _change_tool_mode(self, button_id):
        modes = {0: "NAVIGATE", 1: "ERASE", 2: "RESTORE"}
        self.canvas.set_brush_mode(modes[button_id])

    def _update_brush_size(self, val):
        self.lbl_brush_size.setText(f"{val} px")
        self.canvas.set_brush_size(val)

    def _copy_cloud_url(self):
        url_text = self.txt_cloud_url.text().strip()
        if url_text and url_text != "N/A":
            clipboard = QApplication.clipboard()
            clipboard.setText(url_text)
            QMessageBox.information(self, "Copiado", "URL copiada al portapapeles.")

    def export_webp(self):
        final_pil = self.canvas.get_final_pil_image()
        if not final_pil:
            return

        # Aplicar fondo blanco si está marcado y la imagen posee transparencia
        if self.chk_white_bg.isChecked() and final_pil.mode in ("RGBA", "LA"):
            background = Image.new("RGB", final_pil.size, (255, 255, 255))
            background.paste(final_pil, mask=final_pil.split()[3])
            final_pil = background

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Guardar como WebP", "resultado.webp", "WebP (*.webp)"
        )
        if file_path:
            try:
                export_to_webp(
                    final_pil,
                    file_path,
                    quality=self.slider_quality.value(),
                    resize_config=self.resize_group.get_config()
                )

                cloud_url = "N/A"
                # Subir a Google Cloud Storage si está activo el checkbox
                if self.chk_upload_gcs.isChecked() and self.cloud_service:
                    self.lbl_status.setText("Subiendo a GCS...")
                    
                    # Extraer el nombre de la carpeta contenedora origen si existe (foldername/photoname)
                    folder_name = ""
                    if self.current_file_path:
                        parent_dir = os.path.dirname(self.current_file_path)
                        folder_name = os.path.basename(parent_dir)
                    
                    filename = os.path.basename(file_path)
                    
                    # Construir destination_blob_name respetando foldername/photoname
                    destination_blob_name = filename
                    
                    res_url = self.cloud_service.upload_file(
                        file_path,
                        destination_blob_name=destination_blob_name,
                        make_public=True
                    )
                    if res_url:
                        cloud_url = res_url
                        self.txt_cloud_url.setText(cloud_url)

                self.lbl_status.setText("Exportación completada con éxito.")
                QMessageBox.information(
                    self, "Éxito", 
                    f"Imagen guardada localmente en:\n{file_path}\n\nCloud URL: {cloud_url}"
                )
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Ocurrió un error al exportar o subir:\n{e}")
                self.lbl_status.setText("Error en exportación.")