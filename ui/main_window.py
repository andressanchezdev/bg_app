import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Dict, Any
from PIL import Image

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QMessageBox, QStackedWidget,
    QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView,
    QFrame, QApplication, QSpinBox, QComboBox, QProgressDialog,
    QDialog, QTextEdit
)
from PySide6.QtCore import Qt, QThreadPool, QThread, Signal

import config
from core.bg_remover import get_ai_session
from core.batch_worker import ImageBatchWorker
from core.image_processor import resize_existing_webp_file
from services.image_indexer import ImageIndexer
from services.cloud_storage import CloudStorageService
from services.db_service import post_image_records
from ui.dialog_settings import SettingsDialog
from ui.dialog_login import SettingsLoginDialog
from ui.dialog_preview import ImagePreviewDialog
from ui.dialog_batch_config import BatchProcessConfigDialog
from ui.dialog_touchup import ImageTouchupDialog
from ui.theme import GLOBAL_THEME


class GcpUploadSummaryDialog(QDialog):
    """
    Modal de informe tras la subida a GCP que permite seleccionar
    y copiar todo el texto y las rutas generadas al portapapeles.
    """
    def __init__(self, summary_text: str, gcp_paths: List[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Resultado de Subida a Google Cloud")
        self.resize(680, 520)
        self.setMinimumSize(550, 400)
        self.gcp_paths = gcp_paths

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        lbl_title = QLabel("Resumen de Almacenamiento en Google Cloud")
        lbl_title.setObjectName("h2")
        layout.addWidget(lbl_title)

        lbl_desc = QLabel("Puedes seleccionar cualquier parte del texto o copiar la lista completa:")
        lbl_desc.setObjectName("caption")
        layout.addWidget(lbl_desc)

        self.txt_content = QTextEdit()
        self.txt_content.setReadOnly(True)
        self.txt_content.setPlainText(summary_text)
        self.txt_content.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        layout.addWidget(self.txt_content)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_copy_all = QPushButton("📋 Copiar Todo")
        btn_copy_all.clicked.connect(self._copy_all)
        btn_row.addWidget(btn_copy_all)

        if self.gcp_paths:
            btn_copy_paths = QPushButton("📁 Copiar solo rutas GCP")
            btn_copy_paths.clicked.connect(self._copy_paths_only)
            btn_row.addWidget(btn_copy_paths)

        btn_row.addStretch()

        btn_close = QPushButton("Cerrar")
        btn_close.setObjectName("primaryBtn")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)

        layout.addLayout(btn_row)

    def _copy_all(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.txt_content.toPlainText())
        QMessageBox.information(self, "Copiado", "Se copió todo el informe al portapapeles.")

    def _copy_paths_only(self):
        if self.gcp_paths:
            clipboard = QApplication.clipboard()
            clipboard.setText("\n".join(self.gcp_paths))
            QMessageBox.information(self, "Copiado", f"Se copiaron {len(self.gcp_paths)} rutas de GCP al portapapeles.")


class GcpUploadThread(QThread):
    progress = Signal(int, int, str)       # current, total, filename
    finished = Signal(dict)               # results dict
    error = Signal(str)                   # error message

    def __init__(self, gcp_service, processed_files, current_records, base_folder, timeout_per_file=15):
        super().__init__()
        self.gcp_service = gcp_service
        self.processed_files = list(processed_files)
        self.current_records = current_records
        self.base_folder = base_folder
        self.timeout_per_file = timeout_per_file
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    def run(self):
        try:
            # 1. Test de conexion rápido
            conn_test = self.gcp_service.test_connection()
            if not conn_test.get("ok"):
                self.error.emit(conn_test.get("message", "Error de conexión con GCP."))
                return

            if self.is_cancelled:
                return

            # 2. Obtener carpetas existentes
            self.progress.emit(0, len(self.processed_files), "Consultando carpetas en Google Cloud...")
            existing_folders = self.gcp_service.get_existing_folders()

            uploaded_urls = []
            errors_list = []
            total = len(self.processed_files)

            for idx, fpath in enumerate(self.processed_files, 1):
                if self.is_cancelled:
                    break

                fname_curr = os.path.basename(fpath)
                self.progress.emit(idx, total, f"Subiendo: {fname_curr}")

                base_stem = Path(fpath).stem
                rec_found = None
                for orig in self.current_records:
                    if Path(orig.get("filename", "")).stem == base_stem:
                        rec_found = orig
                        break

                try:
                    folder_candidate = rec_found.get("folder_name", "") if rec_found else ""
                    val = self.gcp_service.resolve_product_folder(
                        filename=fname_curr,
                        existing_folders=existing_folders,
                        folder_candidate=folder_candidate
                    )
                    target_sub = val["target_subfolder"]
                    blob_name = fname_curr

                    url = self.gcp_service.upload_file(
                        fpath,
                        destination_blob_name=blob_name,
                        subfolder=target_sub,
                        make_public=True,
                        avoid_overwrite=True
                    )
                    if url:
                        uploaded_urls.append(url)
                        actual_uploaded_name = url.split("?")[0].rstrip("/").split("/")[-1]
                        if rec_found:
                            rec_found["cloud_url"] = url
                            rec_found["folder_name"] = target_sub
                            rec_found["uploaded_filename"] = actual_uploaded_name
                            rec_found["processed"] = True
                    else:
                        errors_list.append(f"{fname_curr}: Fallo de red o permiso al subir.")
                except Exception as ex:
                    errors_list.append(f"{fname_curr}: {str(ex)}")

            self.finished.emit({
                "uploaded_urls": uploaded_urls,
                "errors_list": errors_list,
                "cancelled": self.is_cancelled
            })

        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("IA Background Remover & WebP Optimizer")
        self.resize(980, 700)
        self.setMinimumSize(850, 600)
        self.setAcceptDrops(True)
        self.setStyleSheet(GLOBAL_THEME)

        # 1. Servicios del Sistema (Sin Base de Datos Local)
        self.ai_session = get_ai_session()
        self.thread_pool = QThreadPool.globalInstance()
        self.thread_pool.setMaxThreadCount(2)

        # 2. Variables de Estado del Flujo
        self.current_records: List[Dict[str, Any]] = []
        self.current_summary: Dict[str, Any] = {}
        self.current_input_root: str = ""
        self.current_output_dir: str = os.path.join(os.getcwd(), "output", "processed")
        self.current_batch_id: int = 0
        self.completed_count: int = 0
        self.processed_files: List[str] = []
        self.batch_config: Dict[str, Any] = {
            "white_bg": False,
            "quality": getattr(config, "DEFAULT_WEBP_QUALITY", 90),
            "resize_enabled": True,
            "target_width": 900,
            "target_height": 900,
            "resize_mode": "contain"
        }

        self._init_ui()

    def _init_ui(self):
        central_widget = QWidget()
        central_widget.setObjectName("centralWidget")
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(24, 16, 24, 16)
        main_layout.setSpacing(16)

        # ---------------- Barra Superior Minimalista ----------------
        top_bar = QHBoxLayout()

        btn_home = QPushButton("⌂ Inicio")
        btn_home.setObjectName("homeBtn")
        btn_home.setToolTip("Volver al inicio y reiniciar proceso en memoria")
        btn_home.setCursor(Qt.PointingHandCursor)
        btn_home.clicked.connect(lambda: self._handle_home(confirm_if_running=True))
        top_bar.addWidget(btn_home)

        top_bar.addSpacing(10)

        lbl_app = QLabel("PROCESADOR DE FONDOS Y OPTIMIZACIÓN WEBP")
        lbl_app.setObjectName("caption")
        top_bar.addWidget(lbl_app)

        top_bar.addStretch()

        btn_settings = QPushButton("Configuración")
        btn_settings.clicked.connect(self._open_settings_dialog)
        top_bar.addWidget(btn_settings)

        main_layout.addLayout(top_bar)

        # ---------------- Contenedor por Estados (Wizard) ----------------
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)

        self._build_step1_welcome()
        self._build_step2_summary()
        self._build_step3_processing()
        self._build_step4_delivery()

        self.setCentralWidget(central_widget)
        self.stack.setCurrentIndex(0)

    # =========================================================================
    # EVENTOS DRAG & DROP NATIVOS
    # =========================================================================
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if not urls:
            return
        first_path = urls[0].toLocalFile()
        if os.path.isdir(first_path):
            self.load_directory(first_path)
        elif os.path.isfile(first_path):
            self.load_single_file(first_path)

    # =========================================================================
    # PANTALLA 1: BIENVENIDA Y CARGA (DISEÑO ESTANDARIZADO)
    # =========================================================================
    def _build_step1_welcome(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(28)

        # Textos de Bienvenida
        header_layout = QVBoxLayout()
        header_layout.setAlignment(Qt.AlignCenter)
        header_layout.setSpacing(6)

        lbl_title = QLabel("Aislamiento de producto y optimización")
        lbl_title.setObjectName("h1")
        lbl_title.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(lbl_title)

        lbl_desc = QLabel(
            "Elimina el fondo de tus imágenes preservando el objeto principal con transparencia limpia.\n"
            "Selecciona o arrastra el contenido para comenzar."
        )
        lbl_desc.setObjectName("body")
        lbl_desc.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(lbl_desc)

        layout.addLayout(header_layout)

        # Dos Tarjetas de Entrada Homogéneas
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(20)
        cards_layout.setAlignment(Qt.AlignCenter)

        # Tarjeta 1: Carpeta / Lote masivo
        card_dir = QFrame()
        card_dir.setObjectName("card")
        card_dir.setFixedSize(320, 180)
        card_dir_layout = QVBoxLayout(card_dir)
        card_dir_layout.setContentsMargins(18, 18, 18, 18)
        card_dir_layout.setSpacing(8)

        lbl_type_dir = QLabel("LOTE MASIVO")
        lbl_type_dir.setObjectName("caption")
        card_dir_layout.addWidget(lbl_type_dir)

        lbl_title_dir = QLabel("Directorio con subcarpetas")
        lbl_title_dir.setObjectName("h2")
        card_dir_layout.addWidget(lbl_title_dir)

        lbl_sub_dir = QLabel("Arrastra una carpeta completa o explora para procesar todo el árbol de imágenes.")
        lbl_sub_dir.setObjectName("body")
        lbl_sub_dir.setWordWrap(True)
        card_dir_layout.addWidget(lbl_sub_dir)

        card_dir_layout.addStretch()

        btn_pick_dir = QPushButton("Explorar carpeta")
        btn_pick_dir.clicked.connect(self._browse_directory)
        card_dir_layout.addWidget(btn_pick_dir)

        cards_layout.addWidget(card_dir)

        # Tarjeta 2: Archivo único
        card_file = QFrame()
        card_file.setObjectName("card")
        card_file.setFixedSize(320, 180)
        card_file_layout = QVBoxLayout(card_file)
        card_file_layout.setContentsMargins(18, 18, 18, 18)
        card_file_layout.setSpacing(8)

        lbl_type_file = QLabel("INDIVIDUAL")
        lbl_type_file.setObjectName("caption")
        card_file_layout.addWidget(lbl_type_file)

        lbl_title_file = QLabel("Imagen directa")
        lbl_title_file.setObjectName("h2")
        card_file_layout.addWidget(lbl_title_file)

        lbl_sub_file = QLabel("Arrastra o selecciona un archivo de imagen único para aislar su fondo.")
        lbl_sub_file.setObjectName("body")
        lbl_sub_file.setWordWrap(True)
        card_file_layout.addWidget(lbl_sub_file)

        card_file_layout.addStretch()

        btn_pick_file = QPushButton("Seleccionar imagen")
        btn_pick_file.clicked.connect(self._browse_file)
        card_file_layout.addWidget(btn_pick_file)

        cards_layout.addWidget(card_file)

        layout.addLayout(cards_layout)

        # Formatos admitidos
        lbl_formats = QLabel("Formatos compatibles: JPG · PNG · WEBP · BMP · HEIC")
        lbl_formats.setObjectName("caption")
        lbl_formats.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl_formats)

        self.stack.addWidget(page)

    # =========================================================================
    # PANTALLA 2: RESUMEN Y MAPEO
    # =========================================================================
    def _build_step2_summary(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(16)

        # Encabezado
        lbl_step = QLabel("PASO 2 / MAPEO")
        lbl_step.setObjectName("caption")
        layout.addWidget(lbl_step)

        lbl_title = QLabel("Resumen de contenido identificado")
        lbl_title.setObjectName("h1")
        layout.addWidget(lbl_title)

        self.lbl_origin_path = QLabel("Ruta: -")
        self.lbl_origin_path.setObjectName("caption")
        layout.addWidget(self.lbl_origin_path)

        # Métricas principales
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(12)

        self.box_total = self._create_metric_box("Total de imágenes", "0 archivos")
        self.box_subfolders = self._create_metric_box("Subdirectorios", "0 carpetas")
        self.box_mode = self._create_metric_box("Fondo de salida", "WebP transparente")
        self.box_quality = self._create_metric_box("Calidad WebP", "90%")

        stats_layout.addWidget(self.box_total)
        stats_layout.addWidget(self.box_subfolders)
        stats_layout.addWidget(self.box_mode)
        stats_layout.addWidget(self.box_quality)
        layout.addLayout(stats_layout)

        # Desglose de extensiones
        lbl_breakdown_title = QLabel("Formatos detectados en el árbol:")
        lbl_breakdown_title.setObjectName("body")
        layout.addWidget(lbl_breakdown_title)

        self.lbl_format_breakdown = QLabel("-")
        self.lbl_format_breakdown.setObjectName("caption")
        layout.addWidget(self.lbl_format_breakdown)

        lbl_notice = QLabel("Los archivos resultantes mantendrán su nombre original exacto y la misma taxonomía de carpetas.")
        lbl_notice.setObjectName("caption")
        layout.addWidget(lbl_notice)

        layout.addStretch()

        # Botones de Acción
        actions_layout = QHBoxLayout()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self._reset_to_step1)
        actions_layout.addWidget(btn_cancel)

        actions_layout.addStretch()

        btn_config = QPushButton("⚙ Opciones de procesamiento")
        btn_config.setToolTip("Configurar fondo blanco, calidad WebP y medidas")
        btn_config.setCursor(Qt.PointingHandCursor)
        btn_config.clicked.connect(self._open_batch_config_dialog)
        actions_layout.addWidget(btn_config)

        btn_start = QPushButton("Retirar fondo")
        btn_start.setObjectName("primaryBtn")
        btn_start.clicked.connect(self._start_processing)
        actions_layout.addWidget(btn_start)

        layout.addLayout(actions_layout)
        self.stack.addWidget(page)

    def _open_batch_config_dialog(self):
        total = len(self.current_records) if self.current_records else 0
        dlg = BatchProcessConfigDialog(
            initial_config=self.batch_config,
            total_images=total,
            parent=self
        )
        if dlg.exec():
            self.batch_config = dlg.get_config()
            self._update_step2_config_ui()

    def _update_step2_config_ui(self):
        if hasattr(self, "box_mode") and hasattr(self.box_mode, "val_label"):
            mode_text = "Fondo blanco (#FFF)" if self.batch_config.get("white_bg", False) else "WebP transparente"
            self.box_mode.val_label.setText(mode_text)
        if hasattr(self, "box_quality") and hasattr(self.box_quality, "val_label"):
            self.box_quality.val_label.setText(f"{self.batch_config.get('quality', 90)}%")

    def _create_metric_box(self, label_text: str, value_text: str) -> QFrame:
        box = QFrame()
        box.setObjectName("statBox")
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(12, 10, 12, 10)
        box_layout.setSpacing(2)

        lbl_metric_title = QLabel(label_text)
        lbl_metric_title.setObjectName("metricTitle")
        box_layout.addWidget(lbl_metric_title)

        lbl_metric_val = QLabel(value_text)
        lbl_metric_val.setObjectName("metricValue")
        box_layout.addWidget(lbl_metric_val)
        box.val_label = lbl_metric_val
        return box

    # =========================================================================
    # PANTALLA 3: PROCESAMIENTO ACTIVO
    # =========================================================================
    def _build_step3_processing(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(14)

        lbl_step = QLabel("PASO 3 / EJECUCIÓN")
        lbl_step.setObjectName("caption")
        layout.addWidget(lbl_step)

        header_layout = QHBoxLayout()
        lbl_title = QLabel("Procesando lote de imágenes")
        lbl_title.setObjectName("h1")
        header_layout.addWidget(lbl_title)

        self.lbl_progress_counter = QLabel("0 de 0 (0%)")
        self.lbl_progress_counter.setObjectName("caption")
        header_layout.addWidget(self.lbl_progress_counter)
        layout.addLayout(header_layout)

        # Barra de progreso minimalista
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # Tabla en tiempo real
        self.table_process = QTableWidget()
        self.table_process.setColumnCount(4)
        self.table_process.setHorizontalHeaderLabels(["Subcarpeta", "Entrada", "Salida", "Estado"])
        self.table_process.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_process.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_process.verticalHeader().setVisible(False)
        layout.addWidget(self.table_process)

        self.stack.addWidget(page)

    # =========================================================================
    # PANTALLA 4: ENTREGA, CONFIRMACIÓN DE MEDIDAS Y VISUALIZADOR
    # =========================================================================
    def _build_step4_delivery(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(14)

        # Encabezado
        header_layout = QHBoxLayout()
        title_sub_layout = QVBoxLayout()
        lbl_step = QLabel("PASO 4 / REVISIÓN Y SALIDA")
        lbl_step.setObjectName("caption")
        title_sub_layout.addWidget(lbl_step)

        lbl_title = QLabel("Proceso finalizado con éxito")
        lbl_title.setObjectName("h1")
        title_sub_layout.addWidget(lbl_title)

        self.lbl_delivery_desc = QLabel("Fondos removidos. Puedes confirmar o personalizar las medidas y ver cada resultado.")
        self.lbl_delivery_desc.setObjectName("body")
        title_sub_layout.addWidget(self.lbl_delivery_desc)
        header_layout.addLayout(title_sub_layout)

        header_layout.addStretch()

        btn_restart = QPushButton("Nuevo lote")
        btn_restart.setObjectName("flatBtn")
        btn_restart.clicked.connect(self._reset_to_step1)
        header_layout.addWidget(btn_restart)
        layout.addLayout(header_layout)

        # ---------------- PANEL DE CONFIRMACIÓN DE MEDIDAS Y DISTRIBUCIÓN ----------------
        panel_dims = QFrame()
        panel_dims.setObjectName("controlPanel")
        layout_dims = QVBoxLayout(panel_dims)
        layout_dims.setSpacing(8)

        lbl_panel_title = QLabel("ESTANDARIZAR MEDIDAS Y CENTRADO DEL CONTENIDO")
        lbl_panel_title.setObjectName("caption")
        layout_dims.addWidget(lbl_panel_title)

        controls_row = QHBoxLayout()
        controls_row.setSpacing(10)

        # Preset
        controls_row.addWidget(QLabel("Preset:"))
        self.combo_presets = QComboBox()
        self.combo_presets.addItem("900 × 900 (Estándar Catálogo Web)", (900, 900))
        self.combo_presets.addItem("1080 × 1080 (Cuadrado HD)", (1080, 1080))
        self.combo_presets.addItem("1200 × 1200 (Gran Formato)", (1200, 1200))
        self.combo_presets.addItem("Personalizado", None)
        self.combo_presets.currentIndexChanged.connect(self._on_preset_changed)
        controls_row.addWidget(self.combo_presets)

        # Spinboxes
        controls_row.addWidget(QLabel("Ancho:"))
        self.spin_width = QSpinBox()
        self.spin_width.setRange(100, 8000)
        self.spin_width.setValue(900)
        self.spin_width.setSuffix(" px")
        controls_row.addWidget(self.spin_width)

        controls_row.addWidget(QLabel("Alto:"))
        self.spin_height = QSpinBox()
        self.spin_height.setRange(100, 8000)
        self.spin_height.setValue(900)
        self.spin_height.setSuffix(" px")
        controls_row.addWidget(self.spin_height)

        # Distribución
        controls_row.addWidget(QLabel("Distribución:"))
        self.combo_mode = QComboBox()
        self.combo_mode.addItem("Centrar en lienzo transparente (Contain)", "contain")
        self.combo_mode.addItem("Recortar para llenar (Cover)", "cover")
        self.combo_mode.addItem("Estirar / Deformar (Stretch)", "stretch")
        controls_row.addWidget(self.combo_mode)

        controls_row.addStretch()

        self.btn_apply_dims = QPushButton("Aplicar medidas y centrado")
        self.btn_apply_dims.clicked.connect(self._apply_dimensions_to_batch)
        controls_row.addWidget(self.btn_apply_dims)

        layout_dims.addLayout(controls_row)
        layout.addWidget(panel_dims)

        # ---------------- TABLA DE IMÁGENES PROCESADAS ----------------
        self.table_delivery = QTableWidget()
        self.table_delivery.setColumnCount(5)
        self.table_delivery.setHorizontalHeaderLabels([
            "Subcarpeta", "Archivo Salida", "Medidas", "Peso", "Acciones"
        ])
        self.table_delivery.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_delivery.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_delivery.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_delivery.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_delivery.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table_delivery.verticalHeader().setVisible(False)
        layout.addWidget(self.table_delivery)

        # ---------------- BOTONES DE DECISIÓN FINAL ----------------
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(12)

        lbl_dest_note = QLabel("Selecciona el destino para las imágenes procesadas:")
        lbl_dest_note.setObjectName("caption")
        bottom_bar.addWidget(lbl_dest_note)

        bottom_bar.addStretch()

        btn_download_local = QPushButton("Guardar en disco")
        btn_download_local.clicked.connect(self._handle_local_download)
        bottom_bar.addWidget(btn_download_local)

        btn_post_db = QPushButton("Guardar en Base de Datos")
        btn_post_db.clicked.connect(self._handle_post_to_db)
        bottom_bar.addWidget(btn_post_db)

        btn_upload_gcp = QPushButton("Subir a Google Cloud")
        btn_upload_gcp.setObjectName("primaryBtn")
        btn_upload_gcp.clicked.connect(self._handle_gcp_upload)
        bottom_bar.addWidget(btn_upload_gcp)

        layout.addLayout(bottom_bar)
        self.stack.addWidget(page)

    # =========================================================================
    # LÓGICA DE CONTROL Y NAVEGACIÓN
    # =========================================================================
    def _open_settings_dialog(self):
        login_dlg = SettingsLoginDialog(parent=self)
        if login_dlg.exec():
            dlg = SettingsDialog(parent=self)
            dlg.exec()

    def _browse_directory(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar Directorio de Imágenes")
        if folder:
            self.load_directory(folder)

    def _browse_file(self):
        fpath, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar Imagen Directa",
            "",
            "Imágenes (*.jpg *.jpeg *.png *.webp *.bmp *.heic *.heif)"
        )
        if fpath:
            self.load_single_file(fpath)

    def load_directory(self, folder_path: str):
        try:
            records = ImageIndexer.scan_folder(folder_path)
            if not records:
                QMessageBox.warning(self, "Sin imágenes", "No se encontraron imágenes válidas en el directorio.")
                return
            self.current_input_root = folder_path
            self._set_records_and_go_summary(records, f"Directorio: {folder_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error de Lectura", f"No se pudo indexar el directorio:\n{e}")

    def load_single_file(self, file_path: str):
        try:
            records = ImageIndexer.scan_single_file(file_path)
            self.current_input_root = os.path.dirname(file_path)
            self._set_records_and_go_summary(records, f"Archivo: {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error de Archivo", f"No se pudo cargar la imagen:\n{e}")

    def _set_records_and_go_summary(self, records: List[Dict[str, Any]], origin_label: str):
        MAX_BATCH_LIMIT = 100
        if len(records) > MAX_BATCH_LIMIT:
            QMessageBox.warning(
                self,
                "Límite de Procesamiento (Máx. 100 imágenes)",
                f"El directorio seleccionado contiene {len(records)} imágenes.\n\n"
                f"Por rendimiento y estabilidad de la memoria, el límite por lote es de {MAX_BATCH_LIMIT} imágenes.\n"
                f"Se procesarán las primeras {MAX_BATCH_LIMIT} imágenes. Para las restantes, procesa un nuevo lote posteriormente."
            )
            records = records[:MAX_BATCH_LIMIT]

        self.current_records = records
        self.current_summary = ImageIndexer.get_summary(records)

        # Actualizar vista del Paso 2
        self.lbl_origin_path.setText(origin_label)
        self.box_total.val_label.setText(f"{self.current_summary['total_images']} archivos")
        self.box_subfolders.val_label.setText(f"{self.current_summary['subfolders_count']} carpetas")
        self._update_step2_config_ui()

        breakdown_parts = [f"{k}: {v}" for k, v in self.current_summary["format_counts"].items()]
        self.lbl_format_breakdown.setText(" · ".join(breakdown_parts))

        self.stack.setCurrentIndex(1)

        # Abrir modal de configuración pre-procesamiento para que el usuario elija sus opciones
        self._open_batch_config_dialog()

    def _handle_home(self, confirm_if_running=True):
        """
        Retorna a la pantalla inicial limpia, liberando y limpiando
        el estado en memoria del proceso actual.
        """
        if confirm_if_running and self.stack.currentIndex() == 2 and self.current_records and self.completed_count < len(self.current_records):
            reply = QMessageBox.question(
                self,
                "Confirmar retorno al inicio",
                "Hay un proceso de imágenes en curso.\n¿Deseas cancelarlo y regresar al inicio perdiendo el progreso en memoria?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        # 1. Limpiar cola de tareas pendientes en el pool
        self.thread_pool.clear()

        # 2. Reiniciar todas las variables de memoria
        self.current_records.clear()
        self.current_summary.clear()
        self.current_input_root = ""
        self.current_batch_id = 0
        self.completed_count = 0
        self.processed_files.clear()
        self.batch_config = {
            "white_bg": False,
            "quality": getattr(config, "DEFAULT_WEBP_QUALITY", 90),
            "resize_enabled": True,
            "target_width": 900,
            "target_height": 900,
            "resize_mode": "contain"
        }

        # 3. Limpiar tablas e indicadores visuales
        self.table_process.setRowCount(0)
        self.table_delivery.setRowCount(0)
        self.progress_bar.setValue(0)
        self.lbl_progress_counter.setText("0 de 0 (0%)")

        # 4. Limpiar vistas previas y métricas de paso 2
        if hasattr(self, "lbl_origin_path"):
            self.lbl_origin_path.setText("Ruta: -")
        if hasattr(self, "box_total") and hasattr(self.box_total, "val_label"):
            self.box_total.val_label.setText("0 archivos")
        if hasattr(self, "box_subfolders") and hasattr(self.box_subfolders, "val_label"):
            self.box_subfolders.val_label.setText("0 carpetas")
        if hasattr(self, "lbl_format_breakdown"):
            self.lbl_format_breakdown.setText("-")

        # 5. Volver a pantalla 1 (Bienvenida/Carga)
        self.stack.setCurrentIndex(0)

    def _reset_to_step1(self):
        self._handle_home(confirm_if_running=False)

    # =========================================================================
    # INICIO DE PROCESAMIENTO (PASO 3)
    # =========================================================================
    def _start_processing(self):
        if not self.current_records:
            return

        total = len(self.current_records)
        self.completed_count = 0
        self.processed_files = []
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(0)
        self.lbl_progress_counter.setText(f"0 de {total} (0%)")

        # Preparar directorio de salida por defecto
        self.current_output_dir = os.path.join(os.getcwd(), "output", "processed")
        os.makedirs(self.current_output_dir, exist_ok=True)

        # Inicializar manifiesto JSON de mapeo y rutas (Consumo GCP)
        ImageIndexer.save_to_json(
            self.current_records,
            os.path.join(self.current_output_dir, "image_map.json")
        )

        # Poblado inicial de la tabla de ejecución
        self.table_process.setRowCount(total)
        for row, rec in enumerate(self.current_records):
            stem = Path(rec["filename"]).stem
            self.table_process.setItem(row, 0, QTableWidgetItem(rec.get("folder_name", "")))
            self.table_process.setItem(row, 1, QTableWidgetItem(rec.get("filename", "")))
            self.table_process.setItem(row, 2, QTableWidgetItem(f"{stem}.webp"))
            self.table_process.setItem(row, 3, QTableWidgetItem("En espera"))

        self.stack.setCurrentIndex(2)

        # Validar destino en GCP si se activó subida durante el proceso
        upload_to_gcs = self.batch_config.get("upload_to_gcs", False)
        gcp_service = None
        existing_folders = []

        if upload_to_gcs:
            gcp_key = getattr(config, "GCS_CREDENTIALS_PATH", "")
            if not gcp_key or not os.path.exists(gcp_key):
                gcp_key = config.resolve_credentials_path()

            bucket_name = getattr(config, "GCS_BUCKET_NAME", "importadorapremiumonline")
            base_folder = getattr(config, "GCS_BASE_FOLDER", "dependencias/img/productos/")

            if os.path.exists(gcp_key) and bucket_name:
                gcp_service = CloudStorageService(
                    bucket_name=bucket_name,
                    credentials_path=gcp_key,
                    base_folder=base_folder
                )
                conn = gcp_service.test_connection()
                if conn["ok"]:
                    existing_folders = gcp_service.get_existing_folders()
                else:
                    QMessageBox.warning(self, "Error de Conexión GCP", f"No se pudo conectar a Google Cloud Storage:\n\n{conn.get('message', '')}\n\nLas imágenes se procesarán únicamente de forma local.")
                    upload_to_gcs = False
                    gcp_service = None
            else:
                QMessageBox.warning(self, "Credenciales no encontradas", "No se encontró el archivo 'gcp_key.json' de Google Cloud Storage.\n\nVerifica que esté en tu Escritorio o en la carpeta 'credentials/'.\nLas imágenes se procesarán únicamente de forma local.")
                upload_to_gcs = False

        # Despachar workers al ThreadPool con la configuración elegida por el usuario
        white_bg = self.batch_config.get("white_bg", False)
        quality = self.batch_config.get("quality", 90)
        resize_cfg = {
            "enabled": self.batch_config.get("resize_enabled", True),
            "width": self.batch_config.get("target_width", 900),
            "height": self.batch_config.get("target_height", 900),
            "mode": self.batch_config.get("resize_mode", "contain")
        }

        rejected_folders = set()

        for rec in self.current_records:
            fpath = rec["absolute_path"]
            fname = rec.get("filename", "")

            target_subfolder = ""
            can_upload_item = False

            if upload_to_gcs and gcp_service:
                folder_candidate = rec.get("folder_name", "")
                val = gcp_service.resolve_product_folder(
                    filename=fname,
                    existing_folders=existing_folders,
                    folder_candidate=folder_candidate
                )
                target_subfolder = val["target_subfolder"]
                can_upload_item = True

            rec["target_subfolder"] = target_subfolder
            rec["folder_name"] = target_subfolder
            target_out_dir = self.current_output_dir

            worker = ImageBatchWorker(
                file_path=fpath,
                output_dir=target_out_dir,
                session=self.ai_session,
                quality=quality,
                remove_bg=True,
                white_bg=white_bg,
                resize_config=resize_cfg,
                upload_to_cloud=can_upload_item,
                cloud_service=gcp_service if can_upload_item else None,
                target_subfolder=target_subfolder
            )

            worker.signals.started.connect(self._on_worker_started)
            worker.signals.progress.connect(self._on_worker_progress)
            worker.signals.finished.connect(self._on_worker_finished)
            worker.signals.error.connect(self._on_worker_error)

            self.thread_pool.start(worker)

        if rejected_folders:
            base_folder = getattr(config, "GCS_BASE_FOLDER", "dependencias/img/productos/")
            QMessageBox.warning(
                self,
                "Control de Contenido GCP",
                f"Las siguientes carpetas no existen en '{base_folder}':\n"
                f"{(', '.join(list(rejected_folders)[:15]) + '... (' + str(len(rejected_folders)) + ' en total)') if len(rejected_folders) > 15 else ', '.join(rejected_folders)}\n\n"
                f"Sus imágenes se procesarán localmente pero NO se subirán a GCP para evitar crear carpetas no autorizadas."
            )

    def _find_process_row(self, file_path: str) -> int:
        fname = os.path.basename(file_path)
        for row in range(self.table_process.rowCount()):
            item = self.table_process.item(row, 1)
            if item and item.text() == fname:
                return row
        return -1

    def _on_worker_started(self, file_path: str):
        if not self.current_records:
            return
        row = self._find_process_row(file_path)
        if row != -1:
            self.table_process.setItem(row, 3, QTableWidgetItem("Procesando..."))

    def _on_worker_progress(self, file_path: str, msg: str):
        if not self.current_records:
            return
        row = self._find_process_row(file_path)
        if row != -1:
            self.table_process.setItem(row, 3, QTableWidgetItem(msg))

    def _on_worker_finished(self, origin_path: str, output_webp_path: str, cloud_url: str):
        if not self.current_records:
            return
        row = self._find_process_row(origin_path)
        if row != -1:
            self.table_process.setItem(row, 3, QTableWidgetItem("Completado"))

        self.processed_files.append(output_webp_path)
        self.completed_count += 1
        total = len(self.current_records)
        pct = int((self.completed_count / total) * 100) if total else 0

        # Actualizar registro y manifiesto JSON
        base_stem = Path(origin_path).stem
        for r in self.current_records:
            if Path(r["filename"]).stem == base_stem:
                r["processed"] = True
                r["processed_path"] = output_webp_path
                if cloud_url:
                    r["cloud_url"] = cloud_url
                break

        out_json_path = os.path.join(self.current_output_dir, "image_map.json")
        ImageIndexer.update_json_record(
            json_path=out_json_path,
            absolute_path=origin_path,
            processed_path=output_webp_path,
            cloud_url=cloud_url if cloud_url else None,
            processed=True
        )

        self.progress_bar.setValue(self.completed_count)
        self.lbl_progress_counter.setText(f"{self.completed_count} de {total} ({pct}%)")

        if self.completed_count >= total:
            self._populate_delivery_view()
            self.stack.setCurrentIndex(3)

    def _on_worker_error(self, file_path: str, err_msg: str):
        if not self.current_records:
            return
        row = self._find_process_row(file_path)
        if row != -1:
            self.table_process.setItem(row, 3, QTableWidgetItem(f"Error: {err_msg[:25]}"))

        self.completed_count += 1
        total = len(self.current_records)
        pct = int((self.completed_count / total) * 100) if total else 0

        self.progress_bar.setValue(self.completed_count)
        self.lbl_progress_counter.setText(f"{self.completed_count} de {total} ({pct}%)")

        if self.completed_count >= total:
            self._populate_delivery_view()
            self.stack.setCurrentIndex(3)

    # =========================================================================
    # PASO 4: REVISIÓN DE MEDIDAS Y VISTA PREVIA
    # =========================================================================
    def _populate_delivery_view(self):
        total = len(self.current_records)
        count = len(self.processed_files)
        bg_desc = "fondo blanco" if self.batch_config.get("white_bg", False) else "fondo transparente"
        self.lbl_delivery_desc.setText(
            f"{count} de {total} imágenes listas con {bg_desc}.\n"
            "Acciones: Vista previa (👁) · Retocar / Re-procesar con pincel o IA (🔄) · Retirar (🗑)"
        )

        self.table_delivery.setRowCount(count)

        for row, out_path in enumerate(self.processed_files):
            folder_name = Path(out_path).parent.name
            if folder_name == "processed":
                folder_name = "-"

            fname = os.path.basename(out_path)
            w, h, size_kb = self._get_file_info(out_path)

            self.table_delivery.setItem(row, 0, QTableWidgetItem(folder_name))
            self.table_delivery.setItem(row, 1, QTableWidgetItem(fname))
            self.table_delivery.setItem(row, 2, QTableWidgetItem(f"{w} × {h} px"))
            self.table_delivery.setItem(row, 3, QTableWidgetItem(f"{size_kb:.1f} KB"))

            # Contenedor de 3 botones de acción estandarizados
            cell_widget = QWidget()
            cell_layout = QHBoxLayout(cell_widget)
            cell_layout.setContentsMargins(4, 2, 4, 2)
            cell_layout.setSpacing(6)
            cell_layout.setAlignment(Qt.AlignCenter)

            btn_eye = QPushButton("👁")
            btn_eye.setObjectName("actionEye")
            btn_eye.setToolTip("Vista previa con transparencia")
            btn_eye.setCursor(Qt.PointingHandCursor)
            btn_eye.clicked.connect(lambda checked=False, p=out_path: self._show_preview_dialog(p))

            btn_reload = QPushButton("🔄")
            btn_reload.setObjectName("actionReload")
            btn_reload.setToolTip("Retocar y re-procesar (pincel, borrador, IA)")
            btn_reload.setCursor(Qt.PointingHandCursor)
            btn_reload.clicked.connect(lambda checked=False, p=out_path: self._show_touchup_dialog(p))

            btn_delete = QPushButton("🗑")
            btn_delete.setObjectName("actionDelete")
            btn_delete.setToolTip("Retirar de la lista de procesadas")
            btn_delete.setCursor(Qt.PointingHandCursor)
            btn_delete.clicked.connect(lambda checked=False, p=out_path: self._handle_remove_item(p))

            cell_layout.addWidget(btn_eye)
            cell_layout.addWidget(btn_reload)
            cell_layout.addWidget(btn_delete)
            self.table_delivery.setCellWidget(row, 4, cell_widget)

    def _show_touchup_dialog(self, out_path: str):
        base_stem = Path(out_path).stem
        orig_path = None
        for rec in self.current_records:
            if Path(rec["filename"]).stem == base_stem:
                orig_path = rec["absolute_path"]
                break

        dlg = ImageTouchupDialog(
            processed_path=out_path,
            original_path=orig_path,
            ai_session=self.ai_session,
            white_bg=self.batch_config.get("white_bg", False),
            quality=self.batch_config.get("quality", 90),
            target_w=self.spin_width.value(),
            target_h=self.spin_height.value(),
            resize_mode=self.combo_mode.currentData() or "contain",
            parent=self
        )
        if dlg.exec():
            self._populate_delivery_view()

    def _handle_remove_item(self, out_path: str):
        fname = os.path.basename(out_path)
        reply = QMessageBox.question(
            self,
            "Retirar Imagen",
            f"¿Deseas retirar '{fname}' de la lista de procesadas?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            if out_path in self.processed_files:
                self.processed_files.remove(out_path)
            self._populate_delivery_view()

    def _get_file_info(self, file_path: str):
        w, h, size_kb = 0, 0, 0.0
        if os.path.exists(file_path):
            size_kb = os.path.getsize(file_path) / 1024.0
            try:
                with Image.open(file_path) as im:
                    w, h = im.size
            except Exception:
                pass
        return w, h, size_kb

    def _show_preview_dialog(self, image_path: str):
        dlg = ImagePreviewDialog(image_path=image_path, parent=self)
        dlg.exec()

    def _on_preset_changed(self, index: int):
        data = self.combo_presets.currentData()
        if data:
            self.spin_width.setValue(data[0])
            self.spin_height.setValue(data[1])

    def _apply_dimensions_to_batch(self):
        """
        Aplica las medidas seleccionadas (ej. 900x900) y centra el objeto
        en todas las imágenes procesadas del lote.
        """
        if not self.processed_files:
            return

        w = self.spin_width.value()
        h = self.spin_height.value()
        mode = self.combo_mode.currentData() or "contain"
        white_bg = self.batch_config.get("white_bg", False)
        quality = self.batch_config.get("quality", 90)

        count = 0
        for out_path in self.processed_files:
            try:
                resize_existing_webp_file(
                    out_path,
                    target_width=w,
                    target_height=h,
                    mode=mode,
                    quality=quality,
                    white_bg=white_bg
                )
                count += 1
            except Exception as e:
                print(f"[Error redimensionando {out_path}]: {e}")

        # Refrescar tabla visual de entrega
        self._populate_delivery_view()

        QMessageBox.information(
            self,
            "Medidas Aplicadas",
            f"Se aplicaron las medidas de {w} × {h} px con centrado a {count} imágenes.\n"
            "Puedes verificar el resultado haciendo clic en el icono 👁."
        )

    # =========================================================================
    # ACCIONES DE SALIDA (LOCAL VS GCP)
    # =========================================================================
    def _handle_local_download(self):
        dest_folder = QFileDialog.getExistingDirectory(
            self,
            "Seleccionar Carpeta para Guardar Archivos Procesados"
        )
        if not dest_folder:
            if os.path.exists(self.current_output_dir):
                subprocess.Popen(f'explorer "{self.current_output_dir}"')
            return

        try:
            for item in os.listdir(self.current_output_dir):
                s = os.path.join(self.current_output_dir, item)
                d = os.path.join(dest_folder, item)
                if os.path.isdir(s):
                    shutil.copytree(s, d, dirs_exist_ok=True)
                else:
                    shutil.copy2(s, d)

            QMessageBox.information(
                self,
                "Descarga Local Completada",
                f"Las imágenes procesadas se guardaron correctamente en:\n{dest_folder}"
            )
            subprocess.Popen(f'explorer "{dest_folder}"')

        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudieron copiar los archivos:\n{e}")

    def _handle_gcp_upload(self):
        if not self.processed_files:
            QMessageBox.warning(self, "Sin Imágenes", "No hay imágenes procesadas en el lote para subir a Google Cloud.")
            return

        gcp_key = getattr(config, "GCS_CREDENTIALS_PATH", os.path.join(os.getcwd(), "credentials", "gcp_key.json"))
        if not os.path.exists(gcp_key):
            candidate = os.path.join(os.path.dirname(sys.executable), "credentials", "gcp_key.json")
            if os.path.exists(candidate):
                gcp_key = candidate

        if not os.path.exists(gcp_key):
            reply = QMessageBox.question(
                self,
                "Credenciales GCP Faltantes",
                "No se encontró el archivo de credenciales de Google Cloud ('credentials/gcp_key.json').\n\n"
                "¿Deseas abrir la Configuración para importar las credenciales ahora?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self._open_settings_dialog()
            return

        bucket_name = getattr(config, "GCS_BUCKET_NAME", "importadorapremiumonline")
        base_folder = getattr(config, "GCS_BASE_FOLDER", "dependencias/img/productos/")

        if not bucket_name:
            QMessageBox.warning(self, "Bucket no configurado", "Debes definir el nombre del bucket en Configuración.")
            self._open_settings_dialog()
            return

        gcp_service = CloudStorageService(
            bucket_name=bucket_name,
            credentials_path=gcp_key,
            base_folder=base_folder
        )

        total_files = len(self.processed_files)

        # ---------------- MODAL DE PROGRESO CON TIMEOUT Y CANCELACIÓN ----------------
        progress_dialog = QProgressDialog(
            "Conectando con Google Cloud Storage...",
            "Cancelar",
            0,
            total_files,
            self
        )
        progress_dialog.setWindowTitle("Subiendo a Google Cloud")
        progress_dialog.setWindowModality(Qt.WindowModal)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setValue(0)
        progress_dialog.setAutoClose(False)
        progress_dialog.setAutoReset(False)

        # Iniciar hilo de subida en segundo plano (para no congelar la UI)
        upload_thread = GcpUploadThread(
            gcp_service=gcp_service,
            processed_files=self.processed_files,
            current_records=self.current_records,
            base_folder=base_folder
        )

        progress_dialog.canceled.connect(upload_thread.cancel)

        def on_thread_progress(cur, tot, text):
            progress_dialog.setLabelText(text)
            progress_dialog.setValue(cur)

        def on_thread_error(err_msg):
            progress_dialog.close()
            QMessageBox.critical(
                self,
                "Error en Google Cloud Storage",
                f"Ocurrió un error durante la comunicación con Google Cloud:\n\n{err_msg}"
            )

        def on_thread_finished(res):
            progress_dialog.close()
            uploaded_urls = res.get("uploaded_urls", [])
            errors_list = res.get("errors_list", [])
            cancelled = res.get("cancelled", False)

            # 3. Guardar manifiesto JSON con ÚNICAMENTE información de la subida a GCP (sin rutas locales)
            cloud_manifest = ImageIndexer.build_cloud_manifest(
                self.current_records,
                base_folder=base_folder
            )
            out_json = ImageIndexer.save_to_json(
                cloud_manifest,
                os.path.join(self.current_output_dir, "image_map.json")
            )

            # 4. Registro automático en Base de Datos / Endpoint POST
            db_report = ""
            if uploaded_urls:
                try:
                    db_res = post_image_records(self.current_records)
                    if db_res.get("ok"):
                        db_report = f"\n\n🗄️ Base de Datos:\n{db_res.get('message', '')}"
                    else:
                        db_report = f"\n\n⚠️ Base de Datos:\n{db_res.get('message', '')}"
                except Exception as e:
                    db_report = f"\n\n⚠️ Base de Datos: {e}"

            # 5. Mensaje con informe completo de validación y subida
            if cancelled:
                msg_parts = [f"⚠️ Subida cancelada por el usuario. Se subieron {len(uploaded_urls)} de {total_files} imágenes."]
            else:
                msg_parts = [f"✅ Se subieron {len(uploaded_urls)} de {total_files} imágenes a Google Cloud Storage."]

            # Listado detallado de rutas relativas en GCP donde quedaron guardadas
            gcp_paths = [item.get("ruta_relativa_gcp") for item in cloud_manifest if item.get("ruta_relativa_gcp") and item.get("url_publica_gcp")]
            if gcp_paths:
                msg_parts.append("\n📁 Rutas de almacenamiento en GCP:")
                for p in gcp_paths:
                    msg_parts.append(f" • {p}")

            if errors_list:
                msg_parts.append(f"\n❌ Errores ({len(errors_list)}):")
                for err in errors_list:
                    msg_parts.append(f" • {err}")

            msg_parts.append(f"\n\nManifiesto de rutas generado en:\n{out_json}")
            if db_report:
                msg_parts.append(db_report)

            # Mostrar el modal interactivo con texto seleccionable y botones de copiado
            summary_dialog = GcpUploadSummaryDialog(
                summary_text="\n".join(msg_parts),
                gcp_paths=gcp_paths,
                parent=self
            )
            summary_dialog.exec()

        upload_thread.progress.connect(on_thread_progress)
        upload_thread.error.connect(on_thread_error)
        upload_thread.finished.connect(on_thread_finished)

        # Guardar referencia para evitar recolección por Garbage Collector
        self._active_upload_thread = upload_thread
        self._active_progress_dialog = progress_dialog

        upload_thread.start()
        progress_dialog.show()

    def _handle_post_to_db(self):
        """Envía manualmente los registros del lote a la base de datos o Endpoint API."""
        if not self.current_records:
            QMessageBox.warning(self, "Sin Imágenes", "No hay imágenes en el lote actual para registrar en la base de datos.")
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            res = post_image_records(self.current_records)
            QApplication.restoreOverrideCursor()
            if res["ok"]:
                QMessageBox.information(self, "Registro en Base de Datos", res["message"])
            else:
                QMessageBox.critical(self, "Error en Base de Datos", res["message"])
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Error en Base de Datos", f"No se pudo completar el registro:\n{e}")
