import os
from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout, 
    QHBoxLayout, QPushButton, QFileDialog, QMessageBox
)
from PySide6.QtCore import QThreadPool

import config
from core.bg_remover import get_ai_session
from ui.tab_single import SingleTabWidget
from ui.tab_batch import BatchTabWidget
from ui.tab_settings import SettingsTabWidget
from services.image_indexer import ImageIndexer

# =========================================================================
# HOJAS DE ESTILO (TEMAS OSCURO Y CLARO)
# =========================================================================
DARK_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #1e1e1e;
    color: #e0e0e0;
}
QGroupBox {
    border: 1px solid #3a3a3a;
    border-radius: 6px;
    margin-top: 10px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
}
QPushButton {
    background-color: #2d2d2d;
    border: 1px solid #4a4a4a;
    border-radius: 4px;
    padding: 6px 12px;
    color: #ffffff;
}
QPushButton:hover {
    background-color: #3d3d3d;
}
QPushButton:disabled {
    background-color: #1a1a1a;
    color: #555555;
}
QLineEdit, QSpinBox, QComboBox {
    background-color: #2a2a2a;
    border: 1px solid #444444;
    border-radius: 4px;
    padding: 4px;
    color: #ffffff;
}
QTableWidget {
    background-color: #252525;
    gridline-color: #3a3a3a;
}
QHeaderView::section {
    background-color: #2d2d2d;
    color: #ffffff;
    padding: 4px;
    border: 1px solid #3a3a3a;
}
"""

LIGHT_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #f5f5f5;
    color: #222222;
}
QGroupBox {
    border: 1px solid #cccccc;
    border-radius: 6px;
    margin-top: 10px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
}
QPushButton {
    background-color: #e0e0e0;
    border: 1px solid #b0b0b0;
    border-radius: 4px;
    padding: 6px 12px;
    color: #000000;
}
QPushButton:hover {
    background-color: #d0d0d0;
}
QPushButton:disabled {
    background-color: #f0f0f0;
    color: #aaaaaa;
}
QLineEdit, QSpinBox, QComboBox {
    background-color: #ffffff;
    border: 1px solid #cccccc;
    border-radius: 4px;
    padding: 4px;
    color: #000000;
}
QTableWidget {
    background-color: #ffffff;
    gridline-color: #e0e0e0;
}
QHeaderView::section {
    background-color: #e8e8e8;
    color: #000000;
    padding: 4px;
    border: 1px solid #cccccc;
}
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("IA Background Remover, Editor & Batch Converter")
        self.resize(1280, 850)

        self.json_map_path = os.path.join(os.getcwd(), "output", "image_map.json")

        # 1. Inicialización de servicios globales/compartidos
        self.ai_session = get_ai_session()
        self.thread_pool = QThreadPool.globalInstance()
        self.thread_pool.setMaxThreadCount(2)

        # 2. Construcción de la interfaz
        self._init_ui()

        # 3. Aplicar tema inicial desde la configuración
        initial_theme = getattr(config, "THEME", "dark")
        self.apply_theme(initial_theme)

    def _init_ui(self):
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # Barra superior rápida
        top_bar = QHBoxLayout()
        self.btn_load_folder = QPushButton("📂 Cargar Carpeta (Mapeo JSON)")
        self.btn_load_folder.setStyleSheet("font-weight: bold;")
        self.btn_load_folder.clicked.connect(self.load_folder_and_index)
        top_bar.addWidget(self.btn_load_folder)
        top_bar.addStretch()

        main_layout.addLayout(top_bar)

        # Contenedor central con pestañas
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        self.setCentralWidget(central_widget)

        # Instanciar cada vista/pestaña desacoplada
        self.tab_single = SingleTabWidget(ai_session=self.ai_session)
        self.tab_batch = BatchTabWidget(
            ai_session=self.ai_session,
            thread_pool=self.thread_pool
        )
        self.tab_settings = SettingsTabWidget()

        # Conexión de señales inter-módulos
        self.tab_batch.request_editor.connect(self.open_file_in_editor)
        self.tab_settings.theme_changed.connect(self.apply_theme)

        # Ensamblar las 3 pestañas
        self.tabs.addTab(self.tab_single, "🎨 Edición Individual & Pincel")
        self.tabs.addTab(self.tab_batch, "⚡ Procesamiento en Lote (Tandas)")
        self.tabs.addTab(self.tab_settings, "⚙️ Configuración")

    def load_folder_and_index(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta Raíz", "")
        if not folder:
            return

        try:
            records = ImageIndexer.scan_folder(folder)
            if not records:
                QMessageBox.warning(self, "Sin imágenes", "No se encontraron imágenes válidas en la carpeta.")
                return

            out_json = ImageIndexer.save_to_json(records, self.json_map_path)
            self.tab_batch.load_records(records)
            self.tabs.setCurrentIndex(1)

            QMessageBox.information(
                self,
                "Mapeo Exitoso",
                f"Se registraron {len(records)} imágenes en el mapa.\n\nJSON guardado en:\n{out_json}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Error de Mapeo", f"Ocurrió un error al leer la carpeta:\n{str(e)}")

    def open_file_in_editor(self, file_path: str):
        """Transfiere una imagen de la lista del Batch al Canvas de Edición Individual."""
        self.tab_single.load_image(file_path)
        self.tabs.setCurrentIndex(0)

    def apply_theme(self, theme_name: str):
        """Cambia dinámicamente la hoja de estilo de la aplicación."""
        if theme_name == "dark":
            self.setStyleSheet(DARK_STYLESHEET)
        else:
            self.setStyleSheet(LIGHT_STYLESHEET)