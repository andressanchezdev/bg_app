import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
    QCheckBox, QLabel, QLineEdit, QComboBox, QPushButton, QMessageBox
)
from PySide6.QtCore import Signal
import config

class SettingsTabWidget(QWidget):
    # Señal para notificar a MainWindow cuando se cambie el tema visual
    theme_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.gcp_key_path = os.path.join(os.getcwd(), "credentials", "gcp_key.json")
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # -----------------------------------------------------------------
        # 1. CONFIGURACIÓN DE TEMA VISUAL
        # -----------------------------------------------------------------
        group_theme = QGroupBox("Apariencia de la Aplicación")
        theme_layout = QHBoxLayout(group_theme)
        
        lbl_theme = QLabel("Tema Visual:")
        self.combo_theme = QComboBox()
        self.combo_theme.addItems(["Oscuro", "Claro"])
        
        # Seleccionar valor actual de config
        current_theme = getattr(config, "THEME", "dark")
        self.combo_theme.setCurrentText("Oscuro" if current_theme == "dark" else "Claro")
        self.combo_theme.currentTextChanged.connect(self._on_theme_changed)

        theme_layout.addWidget(lbl_theme)
        theme_layout.addWidget(self.combo_theme)
        theme_layout.addStretch()

        # -----------------------------------------------------------------
        # 2. CONFIGURACIÓN EXCLUSIVA DE GOOGLE CLOUD STORAGE (GCP)
        # -----------------------------------------------------------------
        group_gcp = QGroupBox("Integración con Google Cloud Storage (GCP)")
        gcp_layout = QVBoxLayout(group_gcp)

        # Habilitar subida a la nube
        self.chk_cloud_enabled = QCheckBox("Subir imágenes procesadas a la nube automáticamente")
        self.chk_cloud_enabled.setChecked(getattr(config, "CLOUD_UPLOAD_ENABLED", False))
        self.chk_cloud_enabled.toggled.connect(self._toggle_gcp_inputs)

        # Nombre del Bucket
        bucket_layout = QHBoxLayout()
        lbl_bucket = QLabel("Nombre del Bucket GCP:")
        self.txt_bucket_name = QLineEdit()
        self.txt_bucket_name.setPlaceholderText("ejemplo: mi-bucket-imagenes")
        current_bucket = getattr(config, "GCS_BUCKET_NAME", getattr(config, "GCP_BUCKET_NAME", ""))
        self.txt_bucket_name.setText(current_bucket)
        bucket_layout.addWidget(lbl_bucket)
        bucket_layout.addWidget(self.txt_bucket_name)

        # Verificación del archivo de credenciales JSON
        cred_layout = QHBoxLayout()
        lbl_cred_status_title = QLabel("Credenciales GCP:")
        self.lbl_cred_status = QLabel()
        
        cred_layout.addWidget(lbl_cred_status_title)
        cred_layout.addWidget(self.lbl_cred_status)
        cred_layout.addStretch()

        gcp_layout.addWidget(self.chk_cloud_enabled)
        gcp_layout.addLayout(bucket_layout)
        gcp_layout.addLayout(cred_layout)

        # Botón Guardar
        self.btn_save = QPushButton("💾 Guardar Ajustes")
        self.btn_save.clicked.connect(self._save_settings)

        # Ensamblar interfaz
        layout.addWidget(group_theme)
        layout.addWidget(group_gcp)
        layout.addWidget(self.btn_save)
        layout.addStretch()

        # Estado inicial del formulario y credenciales
        self._toggle_gcp_inputs(self.chk_cloud_enabled.isChecked())
        self._check_gcp_credentials()

    def _check_gcp_credentials(self):
        """Verifica la presencia física del archivo credentials/gcp_key.json."""
        if os.path.exists(self.gcp_key_path):
            self.lbl_cred_status.setText("🟢 Detectado (credentials/gcp_key.json)")
            self.lbl_cred_status.setStyleSheet("color: #4CAF50; font-weight: bold;")
        else:
            self.lbl_cred_status.setText("🔴 Faltante (No se encontró credentials/gcp_key.json)")
            self.lbl_cred_status.setStyleSheet("color: #F44336; font-weight: bold;")

    def _toggle_gcp_inputs(self, enabled: bool):
        """Activa/desactiva las entradas del bucket según la casilla."""
        self.txt_bucket_name.setEnabled(enabled)

    def _on_theme_changed(self, text: str):
        theme_key = "dark" if text == "Oscuro" else "light"
        config.THEME = theme_key
        self.theme_changed.emit(theme_key)

    def _save_settings(self):
        """Guarda las configuraciones en el módulo de runtime config."""
        config.CLOUD_UPLOAD_ENABLED = self.chk_cloud_enabled.isChecked()
        bucket_val = self.txt_bucket_name.text().strip()
        config.GCS_BUCKET_NAME = bucket_val
        config.GCP_BUCKET_NAME = bucket_val

        if config.CLOUD_UPLOAD_ENABLED and not os.path.exists(self.gcp_key_path):
            QMessageBox.warning(
                self,
                "Advertencia de Credenciales",
                "Has activado la subida a GCP, pero el archivo 'credentials/gcp_key.json' no existe.\n\n"
                "Asegúrate de colocar la llave JSON en esa ruta para que la subida funcione correctamente."
            )
        else:
            QMessageBox.information(self, "Configuración", "Ajustes guardados correctamente.")