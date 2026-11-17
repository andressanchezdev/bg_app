import os
import app_paths
import shutil
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QMessageBox, QGroupBox, QGridLayout,
    QComboBox, QWidget, QFrame, QTextEdit, QScrollArea, QSpinBox, QCheckBox, QApplication
)
from PySide6.QtCore import Qt, Signal
import secrets

from services import autostart

import config
from services.cloud_storage import CloudStorageService
from services.db_service import test_db_connection, test_api_endpoint, post_image_records, sync_from_json_manifest
from ui.theme import GLOBAL_THEME, COLOR_STATUS_OK, COLOR_STATUS_ERR, COLOR_BORDER_DEFAULT


class SettingsDialog(QDialog):
    """
    Diálogo de configuración central:
    - Google Cloud Storage (Bucket, Carpeta base, Credenciales JSON).
    - Conexión a Base de Datos (PostgreSQL reutilizando variables de .env y Endpoint REST API POST).
    - Apariencia Visual (Tema).
    """
    theme_changed = Signal(str)
    server_settings_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuración del Sistema y Almacenamiento")
        self.resize(680, 720)
        self.setModal(True)
        self.setStyleSheet(GLOBAL_THEME)

        self.gcp_key_path = config.resolve_credentials_path()
        self._init_ui()
        self._load_values()

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(16, 14, 16, 14)
        root_layout.setSpacing(10)

        # Encabezado
        lbl_badge = QLabel("PANEL DE CONTROL DE INTEGRACIONES")
        lbl_badge.setObjectName("caption")
        root_layout.addWidget(lbl_badge)

        lbl_title = QLabel("Configuración de Servicios y Base de Datos")
        lbl_title.setObjectName("h1")
        lbl_subtitle = QLabel("Gestiona la conexión con GCP, PostgreSQL y los endpoints para registro de URLs.")
        lbl_subtitle.setObjectName("body")
        root_layout.addWidget(lbl_title)
        root_layout.addWidget(lbl_subtitle)

        # Scroll Area para albergar cómodamente todos los paneles
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ border: none; background: transparent; }}")

        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setSpacing(14)
        main_layout.setContentsMargins(4, 4, 4, 4)

        # -------------------------------------------------------------
        # 1. GOOGLE CLOUD STORAGE
        # -------------------------------------------------------------
        group_gcp = QGroupBox("1. Google Cloud Storage (GCP)")
        layout_gcp = QVBoxLayout(group_gcp)
        layout_gcp.setSpacing(10)

        gcp_grid = QGridLayout()
        gcp_grid.setSpacing(8)

        lbl_bucket = QLabel("Bucket Name:")
        lbl_bucket.setObjectName("body")
        gcp_grid.addWidget(lbl_bucket, 0, 0)
        self.txt_bucket = QLineEdit()
        self.txt_bucket.setPlaceholderText("ej: importadorapremiumonline")
        gcp_grid.addWidget(self.txt_bucket, 0, 1)

        lbl_folder = QLabel("Base Folder:")
        lbl_folder.setObjectName("body")
        gcp_grid.addWidget(lbl_folder, 1, 0)
        self.txt_base_folder = QLineEdit()
        self.txt_base_folder.setPlaceholderText("ej: dependencias/img/productos/")
        gcp_grid.addWidget(self.txt_base_folder, 1, 1)

        lbl_public = QLabel("URL pública:")
        lbl_public.setObjectName("body")
        gcp_grid.addWidget(lbl_public, 3, 0)
        public_row = QHBoxLayout()
        self.txt_public_base_url = QLineEdit()
        self.txt_public_base_url.setPlaceholderText("vacío = https://storage.googleapis.com/<bucket>/")
        self.txt_public_base_url.setToolTip(
            "Dirección con la que se consumen las imágenes. La ruta guardada en la base es el nombre del objeto "
            "(carpeta base/código/archivo.webp); esta URL solo arma el enlace público.")
        public_row.addWidget(self.txt_public_base_url)
        self.btn_test_public_url = QPushButton("Probar URL")
        self.btn_test_public_url.setCursor(Qt.PointingHandCursor)
        self.btn_test_public_url.clicked.connect(self._test_public_url)
        public_row.addWidget(self.btn_test_public_url)
        gcp_grid.addLayout(public_row, 3, 1)

        lbl_cred = QLabel("Clave JSON:")
        lbl_cred.setObjectName("body")
        gcp_grid.addWidget(lbl_cred, 2, 0)

        cred_row = QHBoxLayout()
        self.lbl_cred_path = QLabel()
        self.lbl_cred_path.setObjectName("caption")
        cred_row.addWidget(self.lbl_cred_path, stretch=1)

        self.btn_import_cred = QPushButton("Importar JSON...")
        self.btn_import_cred.clicked.connect(self._import_credentials_json)
        cred_row.addWidget(self.btn_import_cred)

        gcp_grid.addLayout(cred_row, 2, 1)
        layout_gcp.addLayout(gcp_grid)

        # Botón de prueba GCP y listado
        gcp_action_layout = QHBoxLayout()
        self.btn_test_gcp = QPushButton("🔍 Probar conexión y listar carpetas GCP")
        self.btn_test_gcp.setCursor(Qt.PointingHandCursor)
        self.btn_test_gcp.clicked.connect(self._test_and_list_gcp_folders)
        gcp_action_layout.addWidget(self.btn_test_gcp)

        self.lbl_gcp_status = QLabel("")
        self.lbl_gcp_status.setObjectName("caption")
        gcp_action_layout.addWidget(self.lbl_gcp_status, stretch=1)
        layout_gcp.addLayout(gcp_action_layout)

        self.txt_folders_preview = QTextEdit()
        self.txt_folders_preview.setReadOnly(True)
        self.txt_folders_preview.setFixedHeight(85)
        self.txt_folders_preview.setPlaceholderText("Presiona 'Probar conexión' para ver qué carpetas existen en GCP...")
        layout_gcp.addWidget(self.txt_folders_preview)

        main_layout.addWidget(group_gcp)

        # -------------------------------------------------------------
        # 2. CONEXIÓN A BASE DE DATOS Y ENDPOINT POST
        # -------------------------------------------------------------
        group_db = QGroupBox("2. Conexión a Base de Datos / Endpoint POST")
        layout_db = QVBoxLayout(group_db)
        layout_db.setSpacing(10)

        db_grid = QGridLayout()
        db_grid.setSpacing(8)

        # Motor (fila 6, se agrega al final del grid) · el puerto se sugiere al cambiarlo
        self.combo_db_engine = QComboBox()
        self.combo_db_engine.addItem("MariaDB / MySQL (HeidiSQL)", "mysql")
        self.combo_db_engine.addItem("PostgreSQL", "postgres")
        self.combo_db_engine.currentIndexChanged.connect(self._on_engine_changed)
        self.txt_db_schema = QLineEdit()
        self.txt_db_schema.setPlaceholderText("public")
        self.txt_db_company = QLineEdit()
        self.txt_db_company.setPlaceholderText("opcional: id de la compañía")
        self.txt_db_company.setToolTip("Solo PostgreSQL. Vacío = busca el código en todas las compañías; "
                                       "si el código existe en varias, la imagen no se registra y se avisa.")

        # DB Host
        lbl_host = QLabel("DB Host:")
        lbl_host.setObjectName("body")
        db_grid.addWidget(lbl_host, 0, 0)
        self.txt_db_host = QLineEdit()
        self.txt_db_host.setPlaceholderText("localhost o 127.0.0.1")
        db_grid.addWidget(self.txt_db_host, 0, 1)

        # DB Port
        lbl_port = QLabel("DB Port:")
        lbl_port.setObjectName("body")
        db_grid.addWidget(lbl_port, 0, 2)
        self.spin_db_port = QSpinBox()
        self.spin_db_port.setRange(1, 65535)
        self.spin_db_port.setValue(5432)
        db_grid.addWidget(self.spin_db_port, 0, 3)

        # DB Name
        lbl_dbname = QLabel("DB Name:")
        lbl_dbname.setObjectName("body")
        db_grid.addWidget(lbl_dbname, 1, 0)
        self.txt_db_name = QLineEdit()
        self.txt_db_name.setPlaceholderText("ej: Images o Imagenes")
        db_grid.addWidget(self.txt_db_name, 1, 1)

        # DB Table
        lbl_tbl = QLabel("DB Table:")
        lbl_tbl.setObjectName("body")
        db_grid.addWidget(lbl_tbl, 1, 2)
        self.txt_db_table = QLineEdit()
        self.txt_db_table.setPlaceholderText("ej: images o productos")
        db_grid.addWidget(self.txt_db_table, 1, 3)

        # DB User
        lbl_user = QLabel("DB User:")
        lbl_user.setObjectName("body")
        db_grid.addWidget(lbl_user, 2, 0)
        self.txt_db_user = QLineEdit()
        self.txt_db_user.setPlaceholderText("postgres")
        db_grid.addWidget(self.txt_db_user, 2, 1)

        # DB Password
        lbl_pass = QLabel("DB Password:")
        lbl_pass.setObjectName("body")
        db_grid.addWidget(lbl_pass, 2, 2)
        self.txt_db_pass = QLineEdit()
        self.txt_db_pass.setEchoMode(QLineEdit.Password)
        self.txt_db_pass.setPlaceholderText("••••••••")
        db_grid.addWidget(self.txt_db_pass, 2, 3)

        # Base URL (Endpoint API)
        lbl_api = QLabel("Endpoint API (POST):")
        lbl_api.setObjectName("body")
        db_grid.addWidget(lbl_api, 3, 0)
        self.txt_api_endpoint = QLineEdit()
        self.txt_api_endpoint.setPlaceholderText("ej: http://tuservidor.com/api/productos/imagenes (POST de registros, no la URL del bucket)")
        db_grid.addWidget(self.txt_api_endpoint, 3, 1, 1, 3)

        # Columna Código (Búsqueda)
        lbl_col_code = QLabel("Col. Código:")
        lbl_col_code.setObjectName("body")
        db_grid.addWidget(lbl_col_code, 4, 0)
        self.txt_db_code_col = QLineEdit()
        self.txt_db_code_col.setPlaceholderText("codigo")
        db_grid.addWidget(self.txt_db_code_col, 4, 1)

        # Columna Imágenes (Array / Ruta)
        lbl_col_img = QLabel("Col. Imágenes:")
        lbl_col_img.setObjectName("body")
        db_grid.addWidget(lbl_col_img, 4, 2)
        self.txt_db_img_col = QLineEdit()
        self.txt_db_img_col.setPlaceholderText("imagenArray")
        db_grid.addWidget(self.txt_db_img_col, 4, 3)

        # Modo de integración
        lbl_mode = QLabel("Modo de Envío:")
        lbl_mode.setObjectName("body")
        db_grid.addWidget(lbl_mode, 5, 0)
        self.combo_sync_mode = QComboBox()
        self.combo_sync_mode.addItem("Solo Base de Datos Directa (MySQL/PostgreSQL)", "db")
        self.combo_sync_mode.addItem("Solo Endpoint REST API (HTTP POST)", "api")
        self.combo_sync_mode.addItem("Ambos (Base de Datos + Endpoint API)", "both")
        db_grid.addWidget(self.combo_sync_mode, 5, 1, 1, 3)

        lbl_engine = QLabel("Motor:")
        lbl_engine.setObjectName("body")
        db_grid.addWidget(lbl_engine, 6, 0)
        db_grid.addWidget(self.combo_db_engine, 6, 1)
        self.lbl_db_schema = QLabel("Esquema:")
        self.lbl_db_schema.setObjectName("body")
        db_grid.addWidget(self.lbl_db_schema, 6, 2)
        db_grid.addWidget(self.txt_db_schema, 6, 3)
        self.lbl_db_company = QLabel("Compañía:")
        self.lbl_db_company.setObjectName("body")
        db_grid.addWidget(self.lbl_db_company, 7, 0)
        db_grid.addWidget(self.txt_db_company, 7, 1)

        layout_db.addLayout(db_grid)

        # Botones de prueba y sincronización
        db_btn_row = QHBoxLayout()
        self.btn_test_db = QPushButton("🔍 Probar conexión DB")
        self.btn_test_db.setCursor(Qt.PointingHandCursor)
        self.btn_test_db.clicked.connect(self._test_db_connection)
        db_btn_row.addWidget(self.btn_test_db)

        self.btn_test_api = QPushButton("🌐 Probar Endpoint API")
        self.btn_test_api.setCursor(Qt.PointingHandCursor)
        self.btn_test_api.clicked.connect(self._test_api_endpoint)
        db_btn_row.addWidget(self.btn_test_api)

        self.btn_sync_json = QPushButton("📥 Sincronizar último JSON")
        self.btn_sync_json.setToolTip("Lee 'image_map.json' y envía las URLs a la base de datos de inmediato")
        self.btn_sync_json.setCursor(Qt.PointingHandCursor)
        self.btn_sync_json.clicked.connect(self._sync_last_json)
        db_btn_row.addWidget(self.btn_sync_json)

        layout_db.addLayout(db_btn_row)

        self.lbl_db_status = QLabel("")
        self.lbl_db_status.setObjectName("caption")
        self.lbl_db_status.setWordWrap(True)
        layout_db.addWidget(self.lbl_db_status)

        main_layout.addWidget(group_db)

        # -------------------------------------------------------------
        # 3. APARIENCIA VISUAL
        # -------------------------------------------------------------
        group_ui = QGroupBox("3. Apariencia Visual")
        layout_ui = QHBoxLayout(group_ui)
        layout_ui.addWidget(QLabel("Tema de la Interfaz:"))
        self.combo_theme = QComboBox()
        self.combo_theme.addItem("Oscuro (Predeterminado)", "dark")
        self.combo_theme.addItem("Claro", "light")
        layout_ui.addWidget(self.combo_theme)
        layout_ui.addStretch()
        main_layout.addWidget(group_ui)

        # -------------------------------------------------------------
        # 4. SERVIDOR DE RED LOCAL (v2)
        # -------------------------------------------------------------
        group_srv = QGroupBox("4. Servidor de Red Local y Segundo Plano")
        layout_srv = QVBoxLayout(group_srv)
        layout_srv.setSpacing(8)

        self.chk_server_enabled = QCheckBox("Escuchar peticiones de la red local (API HTTP)")
        layout_srv.addWidget(self.chk_server_enabled)

        srv_grid = QGridLayout()
        srv_grid.setSpacing(8)
        lbl_port = QLabel("Puerto:")
        lbl_port.setObjectName("body")
        srv_grid.addWidget(lbl_port, 0, 0)
        self.spin_server_port = QSpinBox()
        self.spin_server_port.setRange(1024, 65535)
        srv_grid.addWidget(self.spin_server_port, 0, 1)

        lbl_key = QLabel("API Key:")
        lbl_key.setObjectName("body")
        srv_grid.addWidget(lbl_key, 1, 0)
        key_row = QHBoxLayout()
        self.txt_api_key = QLineEdit()
        self.txt_api_key.setReadOnly(True)
        key_row.addWidget(self.txt_api_key, stretch=1)
        btn_copy_key = QPushButton("Copiar")
        btn_copy_key.clicked.connect(lambda: QApplication.clipboard().setText(self.txt_api_key.text()))
        key_row.addWidget(btn_copy_key)
        btn_regen_key = QPushButton("Regenerar")
        btn_regen_key.clicked.connect(lambda: self.txt_api_key.setText(secrets.token_urlsafe(24)))
        key_row.addWidget(btn_regen_key)
        srv_grid.addLayout(key_row, 1, 1)
        layout_srv.addLayout(srv_grid)

        self.lbl_server_urls = QLabel("")
        self.lbl_server_urls.setObjectName("caption")
        self.lbl_server_urls.setWordWrap(True)
        self.lbl_server_urls.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout_srv.addWidget(self.lbl_server_urls)

        self.chk_autostart = QCheckBox("Iniciar automáticamente con Windows (en segundo plano)")
        self.chk_autostart.setEnabled(autostart.is_supported())
        if not autostart.is_supported():
            self.chk_autostart.setToolTip("Disponible solo en la aplicación instalada.")
        layout_srv.addWidget(self.chk_autostart)

        main_layout.addWidget(group_srv)

        scroll.setWidget(container)
        root_layout.addWidget(scroll)

        # -------------------------------------------------------------
        # 4. ACCIONES DE PIE
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

        root_layout.addLayout(bottom_bar)

    def _load_values(self):
        # GCP
        self.txt_bucket.setText(getattr(config, "GCS_BUCKET_NAME", "importadorapremiumonline"))
        self.txt_base_folder.setText(getattr(config, "GCS_BASE_FOLDER", "dependencias/img/productos/"))
        self.txt_public_base_url.setText(getattr(config, "GCS_PUBLIC_BASE_URL", ""))

        # DB / Endpoint
        self.txt_db_host.setText(getattr(config, "DB_HOST", "localhost"))
        self.spin_db_port.setValue(int(getattr(config, "DB_PORT", 3306)))
        self.txt_db_name.setText(getattr(config, "DB_DATABASE", "mysql"))
        self.txt_db_table.setText(getattr(config, "DB_TABLE", "productos"))
        self.txt_db_code_col.setText(getattr(config, "DB_CODE_COLUMN", "codigo"))
        self.txt_db_img_col.setText(getattr(config, "DB_IMAGE_COLUMN", "imagenArray"))
        self.txt_db_user.setText(getattr(config, "DB_USER", "root"))
        self.txt_db_pass.setText(getattr(config, "DB_PASSWORD", "password_123"))
        self.txt_api_endpoint.setText(getattr(config, "DB_API_ENDPOINT", ""))

        engine = getattr(config, "DB_ENGINE", "") or ("mysql" if int(getattr(config, "DB_PORT", 3306)) in (3306, 3307, 3308) else "postgres")
        self._loading_engine = True
        idx_engine = self.combo_db_engine.findData(engine)
        self.combo_db_engine.setCurrentIndex(idx_engine if idx_engine != -1 else 0)
        self._loading_engine = False
        self.txt_db_schema.setText(getattr(config, "DB_SCHEMA", "public") or "public")
        self.txt_db_company.setText(str(getattr(config, "DB_COMPANY_ID", "") or ""))
        self._toggle_pg_fields()

        sync_mode = getattr(config, "DB_SYNC_MODE", "db")
        idx_mode = self.combo_sync_mode.findData(sync_mode)
        if idx_mode != -1:
            self.combo_sync_mode.setCurrentIndex(idx_mode)

        # Tema
        current_theme = getattr(config, "THEME", "dark")
        idx = self.combo_theme.findData(current_theme)
        if idx != -1:
            self.combo_theme.setCurrentIndex(idx)

        # Servidor
        self.chk_server_enabled.setChecked(bool(getattr(config, "SERVER_ENABLED", True)))
        self.spin_server_port.setValue(int(getattr(config, "SERVER_PORT", 8765)))
        self.txt_api_key.setText(getattr(config, "SERVER_API_KEY", ""))
        self.chk_autostart.setChecked(autostart.is_enabled())
        self._refresh_server_urls()

        self._refresh_cred_label()

    def _toggle_pg_fields(self):
        is_pg = (self.combo_db_engine.currentData() or "mysql") == "postgres"
        for widget in (self.lbl_db_schema, self.txt_db_schema, self.lbl_db_company, self.txt_db_company):
            widget.setVisible(is_pg)

    def _on_engine_changed(self, _index):
        self._toggle_pg_fields()
        if getattr(self, "_loading_engine", False):
            return
        engine = self.combo_db_engine.currentData()
        port = self.spin_db_port.value()
        # solo cambia el puerto si tenía el del otro motor
        if engine == "postgres" and port in (3306, 3307, 3308):
            self.spin_db_port.setValue(5432)
        elif engine == "mysql" and port == 5432:
            self.spin_db_port.setValue(3306)

    def _test_public_url(self):
        import urllib.request
        base = self.txt_public_base_url.text().strip() or f"https://storage.googleapis.com/{self.txt_bucket.text().strip()}/"
        url = base.rstrip("/") + "/"
        try:
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "BgApp-Client/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                code = resp.getcode()
        except urllib.error.HTTPError as e:
            code = e.code
        except Exception as e:
            QMessageBox.critical(self, "URL pública", f"No se pudo alcanzar {url}:\n{e}")
            return
        # el bucket responde aunque la raíz no se pueda listar (403/404 = el servidor existe)
        if code < 500:
            QMessageBox.information(self, "URL pública",
                                    f"El servidor respondió (HTTP {code}).\n\nLas imágenes quedarán en:\n{url}<carpeta base>/<código>/<archivo>.webp")
        else:
            QMessageBox.critical(self, "URL pública", f"El servidor respondió con error HTTP {code}.")

    def _refresh_server_urls(self):
        from server.api_server import lan_addresses
        port = self.spin_server_port.value()
        urls = [f"http://{ip}:{port}" for ip in lan_addresses()] or [f"http://localhost:{port}"]
        self.lbl_server_urls.setText("Direcciones en la red: " + "   ".join(urls) + "   (GET /health, POST /jobs)")

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

        # Siempre en la carpeta de datos del usuario (la carpeta de instalación es de solo lectura)
        self.gcp_key_path = str(app_paths.user_data_dir() / "credentials" / "gcp_key.json")
        dest_dir = os.path.dirname(self.gcp_key_path)
        os.makedirs(dest_dir, exist_ok=True)
        try:
            shutil.copy2(file_path, self.gcp_key_path)
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.gcp_key_path
            config.GCS_CREDENTIALS_PATH = self.gcp_key_path
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
            QMessageBox.critical(self, "Fallo en Google Cloud Storage", res["message"])

    def _get_current_db_dialog_cfg(self):
        return {
            "host": self.txt_db_host.text().strip() or "localhost",
            "port": self.spin_db_port.value(),
            "database": self.txt_db_name.text().strip() or "mysql",
            "user": self.txt_db_user.text().strip() or "root",
            "password": self.txt_db_pass.text(),
            "table": self.txt_db_table.text().strip() or "productos",
            "code_column": self.txt_db_code_col.text().strip() or "codigo",
            "image_column": self.txt_db_img_col.text().strip() or "imagenArray",
            "api_endpoint": self.txt_api_endpoint.text().strip(),
            "sync_mode": self.combo_sync_mode.currentData() or "db",
            "engine": self.combo_db_engine.currentData() or "mysql",
            "schema": self.txt_db_schema.text().strip() or "public",
            "company_id": self.txt_db_company.text().strip()
        }

    def _test_db_connection(self):
        cfg = self._get_current_db_dialog_cfg()
        res = test_db_connection(cfg)
        if res["ok"]:
            self.lbl_db_status.setText(res["message"].replace("\n", " · "))
            self.lbl_db_status.setStyleSheet(f"color: {COLOR_STATUS_OK}; font-weight: bold;")
            QMessageBox.information(self, "Conexión a Base de Datos", res["message"])
        else:
            engine_label = "PostgreSQL" if cfg["engine"] == "postgres" else "MySQL / MariaDB"
            self.lbl_db_status.setText(f"Error al conectar a {engine_label}")
            self.lbl_db_status.setStyleSheet(f"color: {COLOR_STATUS_ERR}; font-weight: bold;")
            QMessageBox.critical(self, f"Fallo en {engine_label}", res["message"])

    def _test_api_endpoint(self):
        endpoint = self.txt_api_endpoint.text().strip()
        if not endpoint:
            QMessageBox.warning(self, "Falta Endpoint", "Por favor ingresa la URL del Endpoint API (ej: http://localhost:5000/api/productos).")
            return

        if "storage.googleapis.com" in endpoint:
            QMessageBox.warning(
                self, "Endpoint API",
                "Esta dirección es del bucket de imágenes, no de una API: el endpoint recibe un POST con los registros.\n\n"
                "La URL de las imágenes va en 'URL pública' (Google Cloud Storage).")
            return
        res = test_api_endpoint(endpoint)
        if res["ok"]:
            self.lbl_db_status.setText("Endpoint API respondió exitosamente.")
            self.lbl_db_status.setStyleSheet(f"color: {COLOR_STATUS_OK}; font-weight: bold;")
            QMessageBox.information(self, "Prueba de Endpoint", res["message"])
        else:
            self.lbl_db_status.setText("Error en Endpoint API")
            self.lbl_db_status.setStyleSheet(f"color: {COLOR_STATUS_ERR}; font-weight: bold;")
            QMessageBox.critical(self, "Fallo en Endpoint API", res["message"])

    def _sync_last_json(self):
        json_path = str(app_paths.processed_dir() / "image_map.json")
        if not os.path.exists(json_path):
            QMessageBox.warning(self, "Sin Manifiesto", f"No se encontró el archivo de manifiesto:\n{json_path}\n\nPrimero procesa o sube un lote a GCP.")
            return

        cfg = self._get_current_db_dialog_cfg()
        res = sync_from_json_manifest(json_path, cfg=cfg)
        if res["ok"]:
            self.lbl_db_status.setText(f"Sincronización completada: {res['total_items']} registros enviados.")
            self.lbl_db_status.setStyleSheet(f"color: {COLOR_STATUS_OK}; font-weight: bold;")
            QMessageBox.information(self, "Sincronización Exitosa", res["message"])
        else:
            self.lbl_db_status.setText("Fallo en sincronización")
            self.lbl_db_status.setStyleSheet(f"color: {COLOR_STATUS_ERR}; font-weight: bold;")
            QMessageBox.critical(self, "Error al sincronizar", res["message"])

    def _save_all_settings(self):
        new_bucket = self.txt_bucket.text().strip()
        new_folder = self.txt_base_folder.text().strip()
        new_theme = self.combo_theme.currentData()

        # Configuración DB
        cfg = self._get_current_db_dialog_cfg()
        if cfg["company_id"] and not cfg["company_id"].isdigit():
            QMessageBox.warning(self, "Compañía", "El id de la compañía debe ser un número (o déjelo vacío).")
            return
        if cfg["sync_mode"] in ("api", "both") and "storage.googleapis.com" in cfg["api_endpoint"]:
            QMessageBox.warning(self, "Endpoint API",
                                "El endpoint API tiene la dirección del bucket. Con el modo de envío elegido se haría un POST al bucket.\n\n"
                                "Corrija el endpoint o use el modo 'Solo Base de Datos'.")
            return

        config.save_settings(
            theme=new_theme,
            bucket_name=new_bucket,
            base_folder=new_folder,
            db_host=cfg["host"],
            db_port=cfg["port"],
            db_database=cfg["database"],
            db_user=cfg["user"],
            db_password=cfg["password"],
            db_table=cfg["table"],
            db_code_column=cfg["code_column"],
            db_image_column=cfg["image_column"],
            db_api_endpoint=cfg["api_endpoint"],
            db_sync_mode=cfg["sync_mode"],
            server_enabled=self.chk_server_enabled.isChecked(),
            server_port=self.spin_server_port.value(),
            server_api_key=self.txt_api_key.text().strip(),
            db_engine=cfg["engine"],
            db_schema=cfg["schema"],
            db_company_id=cfg["company_id"],
            public_base_url=self.txt_public_base_url.text().strip()
        )

        if autostart.is_supported():
            try:
                autostart.set_enabled(self.chk_autostart.isChecked())
            except OSError as e:
                QMessageBox.warning(self, "Inicio con Windows", f"No se pudo actualizar el inicio automático:\n{e}")

        self.theme_changed.emit(new_theme)
        self.server_settings_changed.emit()

        QMessageBox.information(
            self,
            "Configuración Guardada",
            "Los ajustes de Google Cloud Storage, Base de Datos, API y servidor de red se guardaron exitosamente."
        )
        self.accept()
