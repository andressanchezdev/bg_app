import os
import shutil
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QMessageBox, QGroupBox, QGridLayout,
    QComboBox, QWidget, QFrame, QTextEdit
)
from PySide6.QtCore import Qt, Signal

import config
from services.cloud_storage import CloudStorageService
from ui.theme import GLOBAL_THEME, COLOR_STATUS_OK, COLOR_STATUS_ERR


class SettingsDialog(QDialog):
    """
    Diálogo de configuración centrado en Google Cloud Storage y la experiencia visual:
    - Google Cloud Storage (Bucket, Carpeta base 'dependencias/img/productos/', Credenciales JSON).
    - Exploración y validación de carpetas existentes en el Bucket en tiempo real.
    - Tema visual (Oscuro / Claro).
    - Cero bases de datos locales: todo persiste en output/settings.json y config.py.
    """
    theme_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuración de Google Cloud y Sistema")
        self.resize(600, 600)
        self.setModal(True)
        self.setStyleSheet(GLOBAL_THEME)

        self.gcp_key_path = getattr(config, "GCS_CREDENTIALS_PATH", os.path.join(os.getcwd(), "credentials", "gcp_key.json"))
        self._init_ui()
        self._load_values()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(14)
        main_layout.setContentsMargins(22, 18, 22, 18)

        # Encabezado
        lbl_badge = QLabel("PANEL DE CONTROL")
        lbl_badge.setObjectName("caption")
        main_layout.addWidget(lbl_badge)

        lbl_title = QLabel("Configuración de Almacenamiento GCP")
        lbl_title.setObjectName("h1")
        lbl_subtitle = QLabel("Configura la conexión con Google Cloud Storage y valida las carpetas de destino.")
        lbl_subtitle.setObjectName("body")
        main_layout.addWidget(lbl_title)
        main_layout.addWidget(lbl_subtitle)

        # -------------------------------------------------------------
        # 1. GOOGLE CLOUD STORAGE
        # -------------------------------------------------------------
        group_gcp = QGroupBox("Google Cloud Storage (GCP)")
        layout_gcp = QVBoxLayout(group_gcp)
        layout_gcp.setSpacing(10)

        gcp_grid = QGridLayout()
        gcp_grid.setSpacing(8)

        # Bucket Name
        lbl_bucket = QLabel("Nombre del Bucket:")
        lbl_bucket.setObjectName("body")
        gcp_grid.addWidget(lbl_bucket, 0, 0)

        self.txt_bucket = QLineEdit()
        self.txt_bucket.setPlaceholderText("ej: importadorapremiumonline")
        gcp_grid.addWidget(self.txt_bucket, 0, 1)

        # Carpeta Base
        lbl_folder = QLabel("Carpeta Base de Destino:")
        lbl_folder.setObjectName("body")
        gcp_grid.addWidget(lbl_folder, 1, 0)

        self.txt_base_folder = QLineEdit()
        self.txt_base_folder.setPlaceholderText("ej: dependencias/img/productos/")
        gcp_grid.addWidget(self.txt_base_folder, 1, 1)

        # Archivo de Credenciales
        lbl_cred = QLabel("Clave JSON de Cuenta:")
        lbl_cred.setObjectName("body")
        gcp_grid.addWidget(lbl_cred, 2, 0)

        cred_row = QHBoxLayout()
        self.lbl_cred_path = QLabel()
        self.lbl_cred_path.setObjectName("caption")
        cred_row.addWidget(self.lbl_cred_path, stretch=1)

        self.btn_import_cred = QPushButton("Importar clave JSON...")
        self.btn_import_cred.clicked.connect(self._import_credentials_json)
        cred_row.addWidget(self.btn_import_cred)

        gcp_grid.addLayout(cred_row, 2, 1)
        layout_gcp.addLayout(gcp_grid)

        # Botón de prueba y listado de carpetas
        gcp_action_layout = QHBoxLayout()
        self.btn_test_gcp = QPushButton("🔍 Probar conexión y listar carpetas")
        self.btn_test_gcp.setCursor(Qt.PointingHandCursor)
        self.btn_test_gcp.clicked.connect(self._test_and_list_gcp_folders)
        gcp_action_layout.addWidget(self.btn_test_gcp)

        self.lbl_gcp_status = QLabel("")
        self.lbl_gcp_status.setObjectName("caption")
        gcp_action_layout.addWidget(self.lbl_gcp_status, stretch=1)
        layout_gcp.addLayout(gcp_action_layout)

        # Visor de carpetas existentes en el bucket
        self.txt_folders_preview = QTextEdit()
        self.txt_folders_preview.setReadOnly(True)
        self.txt_folders_preview.setFixedHeight(95)
        self.txt_folders_preview.setPlaceholderText("Presiona 'Probar conexión y listar carpetas' para ver qué carpetas existen en la ruta indicada...")
        layout_gcp.addWidget(self.txt_folders_preview)

        main_layout.addWidget(group_gcp)

        # -------------------------------------------------------------
        # 2. APARIENCIA
        # -------------------------------------------------------------
        group_ui = QGroupBox("Apariencia Visual")
        layout_ui = QHBoxLayout(group_ui)

        layout_ui.addWidget(QLabel("Tema de la Interfaz:"))
        self.combo_theme = QComboBox()
        self.combo_theme.addItem("Oscuro (Predeterminado)", "dark")
        self.combo_theme.addItem("Claro", "light")
        layout_ui.addWidget(self.combo_theme)
        layout_ui.addStretch()

        main_layout.addWidget(group_ui)

        main_layout.addStretch()

        # -------------------------------------------------------------
        # 3. ACCIONES DE PIE
        # -------------------------------------------------------------
        bottom_bar = QHBoxLayout()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        bottom_bar.addWidget(btn_cancel)

        bottom_bar.addStretch()

        self.btn_save_all = QPushButton("Guardar Cambios")
        self.btn_save_all.setObjectName("primaryBtn")
        self.btn_save_all.setCursor(Qt.PointingHandCursor)
        self.btn_save_all.clicked.connect(self._save_all_settings)
        bottom_bar.addWidget(self.btn_save_all)

        main_layout.addLayout(bottom_bar)

    def _load_values(self):
        self.txt_bucket.setText(getattr(config, "GCS_BUCKET_NAME", "importadorapremiumonline"))
        self.txt_base_folder.setText(getattr(config, "GCS_BASE_FOLDER", "dependencias/img/productos/"))
        
        current_theme = getattr(config, "THEME", "dark")
        idx = self.combo_theme.findData(current_theme)
        if idx != -1:
            self.combo_theme.setCurrentIndex(idx)

        self._refresh_cred_label()

    def _refresh_cred_label(self):
        if os.path.exists(self.gcp_key_path):
            self.lbl_cred_path.setText(f"Detectado ({os.path.basename(self.gcp_key_path)})")
            self.lbl_cred_path.setStyleSheet(f"color: {COLOR_STATUS_OK};")
        else:
            self.lbl_cred_path.setText("No encontrado (credentials/gcp_key.json)")
            self.lbl_cred_path.setStyleSheet(f"color: {COLOR_STATUS_ERR};")

    def _import_credentials_json(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar credencial de servicio Google Cloud (.json)",
            "",
            "Archivos JSON (*.json);;Todos los archivos (*)"
        )
        if not file_path:
            return

        dest_dir = os.path.dirname(self.gcp_key_path)
        os.makedirs(dest_dir, exist_ok=True)
        try:
            shutil.copy2(file_path, self.gcp_key_path)
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.gcp_key_path
            self._refresh_cred_label()
            QMessageBox.information(
                self,
                "Credenciales Importadas",
                f"El archivo JSON se importó exitosamente en:\n{self.gcp_key_path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Error al importar", f"No se pudo copiar el archivo:\n{e}")

    def _test_and_list_gcp_folders(self):
        bucket_val = self.txt_bucket.text().strip()
        folder_val = self.txt_base_folder.text().strip()

        if not os.path.exists(self.gcp_key_path):
            QMessageBox.warning(
                self,
                "Faltan credenciales",
                "Debes importar el archivo credentials/gcp_key.json antes de realizar la prueba."
            )
            return

        if not bucket_val:
            QMessageBox.warning(self, "Falta Bucket", "Ingresa el nombre del bucket de Google Cloud.")
            return

        gcp_service = CloudStorageService(
            bucket_name=bucket_val,
            credentials_path=self.gcp_key_path,
            base_folder=folder_val
        )
        res = gcp_service.test_connection()

        if res["ok"]:
            self.lbl_gcp_status.setText("Conexión exitosa")
            self.lbl_gcp_status.setStyleSheet(f"color: {COLOR_STATUS_OK}; font-weight: bold;")

            # Consultar carpetas existentes
            folders = gcp_service.get_existing_folders()
            if folders:
                limit = 50
                preview_list = folders[:limit]
                folder_list_str = "\n".join([f"📁 {f}/" for f in preview_list])
                more_txt = f"\n... y {len(folders) - limit} carpetas más." if len(folders) > limit else ""
                self.txt_folders_preview.setText(
                    f"Carpetas detectadas en '{folder_val}' (Total: {len(folders)}):\n{folder_list_str}{more_txt}"
                )
            else:
                self.txt_folders_preview.setText(
                    f"Conexión exitosa. No se encontraron subcarpetas bajo '{folder_val}'.\n"
                    "Por política de catálogo, ninguna imagen se almacenará en la raíz sin carpeta."
                )

            QMessageBox.information(
                self,
                "Conexión Exitosa con GCP",
                f"{res['message']}\n\n"
                f"• Subcarpetas identificadas en '{folder_val}': {len(folders)}"
            )
        else:
            self.lbl_gcp_status.setText("Error de conexión")
            self.lbl_gcp_status.setStyleSheet(f"color: {COLOR_STATUS_ERR}; font-weight: bold;")
            self.txt_folders_preview.setText(res["message"])
            QMessageBox.critical(
                self,
                "Fallo en Google Cloud Storage",
                res["message"]
            )

    def _save_all_settings(self):
        new_bucket = self.txt_bucket.text().strip()
        new_folder = self.txt_base_folder.text().strip()
        new_theme = self.combo_theme.currentData()

        # Guardar usando el helper JSON sin base de datos
        config.save_settings(
            theme=new_theme,
            bucket_name=new_bucket,
            base_folder=new_folder
        )

        self.theme_changed.emit(new_theme)

        QMessageBox.information(
            self,
            "Configuración Guardada",
            "Los ajustes de Google Cloud Storage y la interfaz se guardaron exitosamente."
        )
        self.accept()
