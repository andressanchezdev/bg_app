from PySide6.QtWidgets import QWidget, QPushButton, QFileDialog, QMessageBox, QVBoxLayout
from services.image_indexer import ImageIndexer


class ProcessingTabWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_mapping = []
        self.json_map_path = "output/image_map.json"

    def select_folder_and_index(self):
        """Abre un diálogo para seleccionar carpeta y mapear su contenido."""
        folder_selected = QFileDialog.getExistingDirectory(
            self, 
            "Seleccionar Carpeta con Imágenes",
            ""
        )

        if not folder_selected:
            return

        try:
            # 1. Escanear y mapear imágenes
            self.current_mapping = ImageIndexer.scan_folder(folder_selected)

            if not self.current_mapping:
                QMessageBox.warning(
                    self, 
                    "Sin imágenes", 
                    "No se encontraron imágenes válidas (.jpg, .png, .webp) en la carpeta seleccionada."
                )
                return

            # 2. Guardar el mapa inicial en JSON
            json_file = ImageIndexer.save_to_json(self.current_mapping, self.json_map_path)

            QMessageBox.information(
                self,
                "Mapeo Exitoso",
                f"Se mapearon {len(self.current_mapping)} imágenes.\n\n"
                f"El mapa se guardó en:\n{json_file}"
            )

            # 3. Cargar las rutas absolutas en la lista de trabajo de la UI
            file_paths = [item["absolute_path"] for item in self.current_mapping]
            # self.load_files_into_table(file_paths)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al procesar la carpeta:\n{str(e)}")