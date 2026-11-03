from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QLabel,
    QCheckBox, QSpinBox, QComboBox
)
import config


class ResizeConfigGroup(QGroupBox):
    def __init__(self, title="Estandarizar Tamaño de Salida", show_aspect_ratio=False, parent=None):
        super().__init__(title, parent)
        self.show_aspect_ratio = show_aspect_ratio
        self.original_aspect_ratio = 1.0
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Checkbox activar/desactivar
        self.chk_enable = QCheckBox("Activar redimensionamiento")
        self.chk_enable.setChecked(config.DEFAULT_RESIZE_ENABLED)
        self.chk_enable.toggled.connect(self._toggle_inputs)
        layout.addWidget(self.chk_enable)

        # Dimensiones (Ancho x Alto)
        dims_layout = QHBoxLayout()
        dims_layout.addWidget(QLabel("Ancho:"))
        self.spin_w = QSpinBox()
        self.spin_w.setRange(1, 10000)
        self.spin_w.setValue(config.DEFAULT_OUTPUT_WIDTH)
        dims_layout.addWidget(self.spin_w)

        dims_layout.addWidget(QLabel("Alto:"))
        self.spin_h = QSpinBox()
        self.spin_h.setRange(1, 10000)
        self.spin_h.setValue(config.DEFAULT_OUTPUT_HEIGHT)
        dims_layout.addWidget(self.spin_h)
        layout.addLayout(dims_layout)

        # Mantener relación de aspecto (opcional)
        self.chk_aspect = None
        if self.show_aspect_ratio:
            self.chk_aspect = QCheckBox("Mantener Relación de Aspecto")
            self.chk_aspect.setChecked(True)
            layout.addWidget(self.chk_aspect)

            self.spin_w.valueChanged.connect(self._on_width_changed)
            self.spin_h.valueChanged.connect(self._on_height_changed)

        # Modo de ajuste
        layout.addWidget(QLabel("Modo de Ajuste:"))
        self.combo_mode = QComboBox()
        self.combo_mode.addItem("Centrar con Lienzo (Contain)", "contain")
        self.combo_mode.addItem("Recortar para Llenar (Cover)", "cover")
        self.combo_mode.addItem("Estirar / Deformar (Stretch)", "stretch")
        layout.addWidget(self.combo_mode)

        self._toggle_inputs(self.chk_enable.isChecked())

    def _toggle_inputs(self, enabled):
        self.spin_w.setEnabled(enabled)
        self.spin_h.setEnabled(enabled)
        if self.chk_aspect:
            self.chk_aspect.setEnabled(enabled)
        self.combo_mode.setEnabled(enabled)

    def set_original_dimensions(self, width: int, height: int):
        self.original_aspect_ratio = width / height if height != 0 else 1.0
        self.spin_w.blockSignals(True)
        self.spin_h.blockSignals(True)
        self.spin_w.setValue(width)
        self.spin_h.setValue(height)
        self.spin_w.blockSignals(False)
        self.spin_h.blockSignals(False)

    def _on_width_changed(self, width):
        if self.chk_aspect and self.chk_aspect.isChecked() and self.original_aspect_ratio > 0:
            new_h = max(1, int(width / self.original_aspect_ratio))
            self.spin_h.blockSignals(True)
            self.spin_h.setValue(new_h)
            self.spin_h.blockSignals(False)

    def _on_height_changed(self, height):
        if self.chk_aspect and self.chk_aspect.isChecked() and self.original_aspect_ratio > 0:
            new_w = max(1, int(height * self.original_aspect_ratio))
            self.spin_w.blockSignals(True)
            self.spin_w.setValue(new_w)
            self.spin_w.blockSignals(False)

    def get_config(self) -> dict:
        return {
            "enabled": self.chk_enable.isChecked(),
            "width": self.spin_w.value(),
            "height": self.spin_h.value(),
            "mode": self.combo_mode.currentData()
        }