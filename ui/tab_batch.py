import os
import shutil
import tempfile
import config
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QFileDialog, QTableWidget, QTableWidgetItem, QProgressBar, 
    QGroupBox, QCheckBox, QSlider, QMessageBox, QHeaderView
)
from PySide6.QtCore import Qt, QThreadPool, Signal

from core.batch_worker import ImageBatchWorker
from services.image_indexer import ImageIndexer
from services.cloud_storage import CloudStorageService
from ui.resize_group import ResizeConfigGroup


class BatchTabWidget(QWidget):
    request_editor = Signal(str)

    def __init__(self, ai_session, thread_pool: QThreadPool, parent=None):
        super().__init__(parent)
        self.ai_session = ai_session
        self.thread_pool = thread_pool

        # Inicializar servicio de nube con los parámetros de config.py
        base_folder_gcs = getattr(config, "GCS_BASE_FOLDER", "")
        self.cloud_service = CloudStorageService(
            bucket_name=config.GCS_BUCKET_NAME,
            base_folder=base_folder_gcs
        )

        self.batch_file_list = []
        self.records_map = {}
        self.batch_output_dir = ""
        self.is_default_temp_output = False  # Bandera para saber si la salida temporal debe borrarse
        self.completed_count = 0
        self.json_map_path = ""

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)

        # ==================== GRUPO DE ACCIONES / SELECCIÓN ====================
        top_layout = QHBoxLayout()

        self.btn_select_files = QPushButton("Seleccionar Carpeta de Imágenes")
        self.btn_select_files.clicked.connect(self._select_input_folder)
        top_layout.addWidget(self.btn_select_files)

        self.btn_select_out_dir = QPushButton("Carpeta de Salida")
        self.btn_select_out_dir.clicked.connect(self._select_output_folder)
        top_layout.addWidget(self.btn_select_out_dir)

        main_layout.addLayout(top_layout)

        # ==================== CONFIGURACIÓN Y PARÁMETROS ====================
        config_layout = QHBoxLayout()

        # Parámetros del Lote
        param_group = QGroupBox("Parámetros del Lote")
        param_layout = QVBoxLayout(param_group)

        self.chk_remove_bg = QCheckBox("Eliminar fondo (IA)")
        self.chk_remove_bg.setChecked(True)
        param_layout.addWidget(self.chk_remove_bg)

        # Opción Fondo Blanco
        self.chk_white_bg = QCheckBox("Rellenar fondo blanco")
        self.chk_white_bg.setChecked(True)
        param_layout.addWidget(self.chk_white_bg)

        self.chk_upload_gcs = QCheckBox("Subir a Google Cloud Storage")
        self.chk_upload_gcs.setChecked(getattr(config, "CLOUD_UPLOAD_ENABLED", False))
        param_layout.addWidget(self.chk_upload_gcs)

        # Control de Calidad WebP
        quality_layout = QHBoxLayout()
        quality_layout.addWidget(QLabel("Calidad WebP:"))
        self.slider_quality = QSlider(Qt.Horizontal)
        self.slider_quality.setRange(10, 100)
        self.slider_quality.setValue(getattr(config, "DEFAULT_WEBP_QUALITY", 85))
        self.lbl_quality_val = QLabel(str(self.slider_quality.value()))
        self.slider_quality.valueChanged.connect(lambda v: self.lbl_quality_val.setText(str(v)))
        
        quality_layout.addWidget(self.slider_quality)
        quality_layout.addWidget(self.lbl_quality_val)
        param_layout.addLayout(quality_layout)

        config_layout.addWidget(param_group)

        # Widget de Redimensionamiento
        self.resize_group = ResizeConfigGroup(show_aspect_ratio=True)
        config_layout.addWidget(self.resize_group)

        main_layout.addLayout(config_layout)

        # ==================== TABLA DE PROGRESO / ESTADO ====================
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Carpeta", "Archivo", "Estado", "Progreso", "Cloud URL"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        main_layout.addWidget(self.table)

        # ==================== PROGRESO GENERAL Y BOTÓN START ====================
        bottom_layout = QHBoxLayout()

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        bottom_layout.addWidget(self.progress_bar)

        self.btn_start = QPushButton("Iniciar Procesamiento en Lote")
        self.btn_start.setStyleSheet("font-weight: bold; background-color: #2ecc71; color: white; padding: 6px;")
        self.btn_start.clicked.connect(self.start_processing)
        self.btn_start.setEnabled(False)
        bottom_layout.addWidget(self.btn_start)

        main_layout.addLayout(bottom_layout)

    def load_records(self, records: list):
        """Carga una lista de registros directamente (útil para restaurar estados o JSONs previos)."""
        try:
            self.batch_file_list = []
            self.records_map = {}

            for rec in records:
                fpath = rec.get("absolute_path")
                if fpath:
                    self.batch_file_list.append(fpath)
                    self.records_map[fpath] = rec

            self._populate_table()
            self.btn_start.setEnabled(len(self.batch_file_list) > 0)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudieron cargar los registros:\n{e}")

    def _select_input_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta de Imágenes")
        if folder:
            try:
                self.batch_file_list = []
                self.records_map = {}
                
                records = ImageIndexer.scan_folder(folder)
                
                # Si el usuario no eligió una carpeta de salida previamente, asignar output/processed
                if not self.batch_output_dir:
                    self.batch_output_dir = os.path.join(os.getcwd(), "output", "processed")
                    self.is_default_temp_output = False
                
                os.makedirs(self.batch_output_dir, exist_ok=True)
                self.json_map_path = os.path.join(self.batch_output_dir, "image_map.json")
                ImageIndexer.save_to_json(records, self.json_map_path)

                for rec in records:
                    fpath = rec["absolute_path"]
                    self.batch_file_list.append(fpath)
                    self.records_map[fpath] = rec

                self._populate_table()
                self.btn_start.setEnabled(len(self.batch_file_list) > 0)

            except Exception as e:
                QMessageBox.critical(self, "Error", f"No se pudo indexar la carpeta:\n{e}")

    def _select_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta de Salida")
        if folder:
            self.batch_output_dir = folder
            self.is_default_temp_output = False  # Si el usuario selecciona una manual, ya no es la temporal por defecto

    def _populate_table(self):
        self.table.setRowCount(len(self.batch_file_list))
        for row, fpath in enumerate(self.batch_file_list):
            rec = self.records_map.get(fpath, {})
            
            self.table.setItem(row, 0, QTableWidgetItem(rec.get("folder_name", "")))
            self.table.setItem(row, 1, QTableWidgetItem(rec.get("filename", "")))
            self.table.setItem(row, 2, QTableWidgetItem("Pendiente"))
            self.table.setItem(row, 3, QTableWidgetItem("0%"))
            self.table.setItem(row, 4, QTableWidgetItem("-"))

    def start_processing(self):
        if not self.batch_file_list or not self.batch_output_dir:
            QMessageBox.warning(self, "Advertencia", "Selecciona una carpeta de entrada y una de salida.")
            return

        self.btn_start.setEnabled(False)
        self.btn_select_files.setEnabled(False)
        self.btn_select_out_dir.setEnabled(False)

        self.completed_count = 0
        total = len(self.batch_file_list)
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(0)

        quality = self.slider_quality.value()
        resize_cfg = self.resize_group.get_config()
        remove_bg = self.chk_remove_bg.isChecked()
        white_bg = self.chk_white_bg.isChecked()
        upload_to_cloud = self.chk_upload_gcs.isChecked()

        existing_folders = []
        if upload_to_cloud and self.cloud_service:
            conn = self.cloud_service.test_connection()
            if conn.get('ok'):
                existing_folders = self.cloud_service.get_existing_folders()
            else:
                QMessageBox.warning(self, 'Aviso GCP', conn.get('message', ''))
                upload_to_cloud = False

        for fpath in self.batch_file_list:
            rec = self.records_map.get(fpath, {})
            folder_name = rec.get("folder_name", "")
            
            # Respetar subcarpeta local si existe
            target_dir = os.path.join(self.batch_output_dir, folder_name) if folder_name else self.batch_output_dir
            os.makedirs(target_dir, exist_ok=True)

            target_subfolder = ''
            can_upload_item = False
            if upload_to_cloud and self.cloud_service:
                val = self.cloud_service.validate_image_target(folder_name, rec.get('filename', ''), existing_folders)
                if val.get('valid'):
                    target_subfolder = val.get('target_subfolder', '')
                    can_upload_item = True

            worker = ImageBatchWorker(
                file_path=fpath,
                output_dir=target_dir,
                session=self.ai_session,
                quality=quality,
                remove_bg=remove_bg,
                white_bg=white_bg,
                resize_config=resize_cfg,
                upload_to_cloud=can_upload_item,
                cloud_service=self.cloud_service if can_upload_item else None,
                target_subfolder=target_subfolder
            )

            worker.signals.started.connect(self._on_item_started)
            worker.signals.progress.connect(self._on_item_progress)
            worker.signals.finished.connect(self._on_item_finished)
            worker.signals.error.connect(self._on_item_error)

            self.thread_pool.start(worker)

    def _find_row_by_path(self, file_path: str) -> int:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            if item:
                rec = self.records_map.get(file_path, {})
                if item.text() == rec.get("filename", ""):
                    return row
        return -1

    def _on_item_started(self, file_path: str):
        row = self._find_row_by_path(file_path)
        if row != -1:
            self.table.setItem(row, 2, QTableWidgetItem("Procesando"))

    def _on_item_progress(self, file_path: str, message: str):
        row = self._find_row_by_path(file_path)
        if row != -1:
            self.table.setItem(row, 3, QTableWidgetItem(message))

    def _on_item_finished(self, origin_path: str, local_webp_path: str, gcp_url: str):
        row = self._find_row_by_path(origin_path)
        if row != -1:
            self.table.setItem(row, 2, QTableWidgetItem("Completado"))
            self.table.setItem(row, 3, QTableWidgetItem("100%"))
            self.table.setItem(row, 4, QTableWidgetItem(gcp_url if gcp_url else "N/A"))

        # Actualizar el registro JSON de forma segura
        if self.json_map_path:
            try:
                ImageIndexer.update_json_record(
                    json_path=self.json_map_path,
                    absolute_path=origin_path,
                    processed_path=local_webp_path,
                    gcp_url=gcp_url,
                    processed=True
                )
            except Exception as e:
                print(f"Error al actualizar JSON: {e}")

        self.completed_count += 1
        self.progress_bar.setValue(self.completed_count)

        if self.completed_count >= len(self.batch_file_list):
            self._on_batch_completed()

    def _on_item_error(self, file_path: str, error_msg: str):
        row = self._find_row_by_path(file_path)
        if row != -1:
            self.table.setItem(row, 2, QTableWidgetItem("Error"))
            self.table.setItem(row, 3, QTableWidgetItem(error_msg[:30]))

        self.completed_count += 1
        self.progress_bar.setValue(self.completed_count)

        if self.completed_count >= len(self.batch_file_list):
            self._on_batch_completed()

    def _on_batch_completed(self):
        self.btn_start.setEnabled(True)
        self.btn_select_files.setEnabled(True)
        self.btn_select_out_dir.setEnabled(True)

        # Si se usó la ruta temporal por defecto (solo con subida a la nube), limpiarla
        if self.is_default_temp_output and self.batch_output_dir and os.path.exists(self.batch_output_dir):
            try:
                shutil.rmtree(self.batch_output_dir)
                print(f"[Limpieza]: Carpeta temporal de salida eliminada: {self.batch_output_dir}")
            except Exception as e:
                print(f"[Aviso Limpieza]: No se pudo eliminar la carpeta temporal: {e}")

        msg = f"El lote de imágenes se ha procesado por completo.\n\nDestino: {self.batch_output_dir}"
        QMessageBox.information(self, "Proceso Finalizado", msg)