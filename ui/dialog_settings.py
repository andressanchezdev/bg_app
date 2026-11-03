import os
import shutil
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QMessageBox, QGroupBox, QGridLayout
)
from PySide6.QtCore import Qt

import config
from services.database import DatabaseService
from services.cloud_storage import CloudStorageService
from ui.theme import GLOBAL_THEME, COLOR_STATUS_OK, COLOR_STATUS_ERR


class SettingsDialog(QDialog):
    """
    Diálogo estandarizado de configuración:
    1. Conexión a Base de Datos PostgreSQL (pgAdmin 4).
    2. Credenciales y parámetros del servidor Google Cloud Storage (GCP).
    """

    def __init__(self, db_service: DatabaseService, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuración")
        self.resize(600, 560)
        self.setModal(True)
        self.setStyleSheet(GLOBAL_THEME)

        self.db_service = db_service
        self.gcp_key_path = os.path.join(os.getcwd(), "credentials", "gcp_key.json")
        self._init_ui()
        self._load_values()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(16)
        main_layout.setContentsMargins(24, 24, 24, 24)

        # Encabezado
        lbl_title = QLabel("Configuración del Sistema")
        lbl_title.setObjectName("h1")
        lbl_subtitle = QLabel("Parámetros de conexión a PostgreSQL (pgAdmin 4) y Google Cloud Storage")
        lbl_subtitle.setObjectName("body")
        main_layout.addWidget(lbl_title)
        main_layout.addWidget(lbl_subtitle)

        # -------------------------------------------------------------
        # 1. BASE DE DATOS POSTGRESQL (pgAdmin 4)
        # -------------------------------------------------------------
        group_pg = QGroupBox("Base de Datos PostgreSQL (pgAdmin 4)")
        layout_pg = QVBoxLayout(group_pg)
        layout_pg.setSpacing(10)

        grid_pg = QGridLayout()
        grid_pg.setSpacing(8)

        lbl_h = QLabel("Host:")
        lbl_h.setObjectName("caption")
        grid_pg.addWidget(lbl_h, 0, 0)
        self.txt_pg_host = QLineEdit()
        self.txt_pg_host.setPlaceholderText("localhost")
        grid_pg.addWidget(self.txt_pg_host, 0, 1)

        lbl_p = QLabel("Puerto:")
        lbl_p.setObjectName("caption")
        grid_pg.addWidget(lbl_p, 0, 2)
        self.txt_pg_port = QLineEdit()
        self.txt_pg_port.setPlaceholderText("5432")
        self.txt_pg_port.setFixedWidth(70)
        grid_pg.addWidget(self.txt_pg_port, 0, 3)

        lbl_db = QLabel("Base de datos:")
        lbl_db.setObjectName("caption")
        grid_pg.addWidget(lbl_db, 1, 0)
        self.txt_pg_db = QLineEdit()
        self.txt_pg_db.setPlaceholderText("Imagenes")
        grid_pg.addWidget(self.txt_pg_db, 1, 1)

        lbl_u = QLabel("Usuario:")
        lbl_u.setObjectName("caption")
        grid_pg.addWidget(lbl_u, 2, 0)
        self.txt_pg_user = QLineEdit()
        self.txt_pg_user.setPlaceholderText("postgres")
        grid_pg.addWidget(self.txt_pg_user, 2, 1)

        lbl_pass = QLabel("Contraseña:")
        lbl_pass.setObjectName("caption")
        grid_pg.addWidget(lbl_pass, 2, 2)
        self.txt_pg_pass = QLineEdit()
        self.txt_pg_pass.setEchoMode(QLineEdit.Password)
        self.txt_pg_pass.setPlaceholderText("••••••••")
        grid_pg.addWidget(self.txt_pg_pass, 2, 3)

        layout_pg.addLayout(grid_pg)

        pg_action_layout = QHBoxLayout()
        self.btn_test_pg = QPushButton("Probar conexión")
        self.btn_test_pg.clicked.connect(self._test_pg_connection)
        pg_action_layout.addWidget(self.btn_test_pg)

        self.lbl_pg_status = QLabel("Estado: Sin verificar")
        self.lbl_pg_status.setObjectName("caption")
        pg_action_layout.addWidget(self.lbl_pg_status)
        pg_action_layout.addStretch()
        layout_pg.addLayout(pg_action_layout)

        main_layout.addWidget(group_pg)

        # -------------------------------------------------------------
        # 2. SERVIDOR GOOGLE CLOUD STORAGE (GCP)
        # -------------------------------------------------------------
        group_gcp = QGroupBox("Servidor Google Cloud Storage (GCP)")
        layout_gcp = QVBoxLayout(group_gcp)
        layout_gcp.setSpacing(8)

        lbl_cred_head = QLabel("Clave de Cuenta de Servicio:")
        lbl_cred_head.setObjectName("caption")
        layout_gcp.addWidget(lbl_cred_head)

        cred_layout = QHBoxLayout()
        self.lbl_cred_path = QLabel()
        self.lbl_cred_path.setObjectName("caption")
        cred_layout.addWidget(self.lbl_cred_path)
        cred_layout.addStretch()

        self.btn_import_cred = QPushButton("Importar JSON...")
        self.btn_import_cred.clicked.connect(self._import_credentials_file)
        cred_layout.addWidget(self.btn_import_cred)
        layout_gcp.addLayout(cred_layout)

        lbl_b = QLabel("Bucket GCP:")
        lbl_b.setObjectName("caption")
        layout_gcp.addWidget(lbl_b)
        self.txt_bucket = QLineEdit()
        self.txt_bucket.setPlaceholderText("ej. importadorapremiumonline")
        layout_gcp.addWidget(self.txt_bucket)

        lbl_f = QLabel("Carpeta base / Prefijo:")
        lbl_f.setObjectName("caption")
        layout_gcp.addWidget(lbl_f)
        self.txt_base_folder = QLineEdit()
        self.txt_base_folder.setPlaceholderText("ej. dependencias/img/productos/")
        layout_gcp.addWidget(self.txt_base_folder)

        gcp_action_layout = QHBoxLayout()
        self.btn_test_gcp = QPushButton("Probar conexión GCP")
        self.btn_test_gcp.clicked.connect(self._test_gcp_connection)
        gcp_action_layout.addWidget(self.btn_test_gcp)

        self.lbl_gcp_status = QLabel("Estado: Sin verificar")
        self.lbl_gcp_status.setObjectName("caption")
        gcp_action_layout.addWidget(self.lbl_gcp_status)
        gcp_action_layout.addStretch()
        layout_gcp.addLayout(gcp_action_layout)

        main_layout.addWidget(group_gcp)

        # -------------------------------------------------------------
        # BOTONES INFERIORES
        # -------------------------------------------------------------
        main_layout.addStretch()
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.clicked.connect(self.reject)
        bottom_layout.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("Guardar configuración")
        self.btn_save.setObjectName("primaryBtn")
        self.btn_save.clicked.connect(self._save_settings)
        bottom_layout.addWidget(self.btn_save)

        main_layout.addLayout(bottom_layout)

    def _load_values(self):
        cfg = self.db_service.pg_config
        self.txt_pg_host.setText(str(cfg.get("host", "localhost")))
        self.txt_pg_port.setText(str(cfg.get("port", 5432)))
        self.txt_pg_db.setText(str(cfg.get("database", "Imagenes")))
        self.txt_pg_user.setText(str(cfg.get("user", "postgres")))
        self.txt_pg_pass.setText(str(cfg.get("password", "")))

        current_bucket = self.db_service.get_setting(
            "gcs_bucket_name",
            getattr(config, "GCS_BUCKET_NAME", "importadorapremiumonline")
        )
        current_folder = self.db_service.get_setting(
            "gcs_base_folder",
            getattr(config, "GCS_BASE_FOLDER", "dependencias/img/productos/")
        )
        self.txt_bucket.setText(current_bucket)
        self.txt_base_folder.setText(current_folder)

        self._refresh_cred_label()

    def _refresh_cred_label(self):
        if os.path.exists(self.gcp_key_path):
            self.lbl_cred_path.setText(f"Detectado ({self.gcp_key_path})")
            self.lbl_cred_path.setStyleSheet(f"color: {COLOR_STATUS_OK};")
        else:
            self.lbl_cred_path.setText("No configurado (credentials/gcp_key.json no existe)")
            self.lbl_cred_path.setStyleSheet(f"color: {COLOR_STATUS_ERR};")

    def _test_pg_connection(self):
        temp_cfg = {
            "host": self.txt_pg_host.text().strip() or "localhost",
            "port": int(self.txt_pg_port.text().strip() or 5432),
            "database": self.txt_pg_db.text().strip() or "Imagenes",
            "user": self.txt_pg_user.text().strip() or "postgres",
            "password": self.txt_pg_pass.text()
        }

        self.lbl_pg_status.setText("Conectando...")
        res = self.db_service.test_pg_connection(temp_cfg)

        if res["ok"]:
            self.lbl_pg_status.setText(f"Conectado a PostgreSQL ({res['images_count']} registros)")
            self.lbl_pg_status.setStyleSheet(f"color: {COLOR_STATUS_OK};")
            QMessageBox.information(self, "Conexión PostgreSQL Exitosa", res["message"])
        else:
            self.lbl_pg_status.setText("Fallo de conexión")
            self.lbl_pg_status.setStyleSheet(f"color: {COLOR_STATUS_ERR};")
            QMessageBox.warning(self, "Aviso de Base de Datos", res["message"])

    def _import_credentials_file(self):
        fpath, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar archivo JSON de credenciales de GCP",
            "",
            "JSON (*.json)"
        )
        if not fpath:
            return

        try:
            os.makedirs(os.path.dirname(self.gcp_key_path), exist_ok=True)
            shutil.copy2(fpath, self.gcp_key_path)
            self._refresh_cred_label()
            QMessageBox.information(
                self,
                "Credenciales Importadas",
                f"El archivo se guardó correctamente en:\n{self.gcp_key_path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo copiar el archivo:\n{e}")

    def _test_gcp_connection(self):
        bucket_val = self.txt_bucket.text().strip()
        folder_val = self.txt_base_folder.text().strip()

        if not os.path.exists(self.gcp_key_path):
            QMessageBox.warning(
                self,
                "Faltan credenciales",
                "Debes importar primero el archivo .json de credenciales de la cuenta de servicio."
            )
            return

        if not bucket_val:
            QMessageBox.warning(self, "Falta Bucket", "Ingresa el nombre del bucket de GCP.")
            return

        self.lbl_gcp_status.setText("Probando conexión...")
        gcp_service = CloudStorageService(
            bucket_name=bucket_val,
            credentials_path=self.gcp_key_path,
            base_folder=folder_val
        )
        res = gcp_service.test_connection()

        if res["ok"]:
            self.lbl_gcp_status.setText("Conexión exitosa")
            self.lbl_gcp_status.setStyleSheet(f"color: {COLOR_STATUS_OK};")
            QMessageBox.information(self, "Conexión GCP Exitosa", res["message"])
        else:
            self.lbl_gcp_status.setText("Fallo de verificación")
            self.lbl_gcp_status.setStyleSheet(f"color: {COLOR_STATUS_ERR};")
            QMessageBox.warning(self, "Aviso de Google Cloud Storage", res["message"])

    def _save_settings(self):
        pg_cfg = {
            "host": self.txt_pg_host.text().strip() or "localhost",
            "port": int(self.txt_pg_port.text().strip() or 5432),
            "database": self.txt_pg_db.text().strip() or "Imagenes",
            "user": self.txt_pg_user.text().strip() or "postgres",
            "password": self.txt_pg_pass.text()
        }
        self.db_service.save_pg_config(pg_cfg)

        new_bucket = self.txt_bucket.text().strip()
        new_folder = self.txt_base_folder.text().strip()
        self.db_service.set_setting("gcs_bucket_name", new_bucket)
        self.db_service.set_setting("gcs_base_folder", new_folder)

        config.GCS_BUCKET_NAME = new_bucket
        config.GCS_BASE_FOLDER = new_folder

        QMessageBox.information(self, "Configuración", "Los ajustes se han guardado con éxito.")
        self.accept()
