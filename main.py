import sys
import os
from PySide6.QtWidgets import QApplication, QSplashScreen
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QColor, QPainter, QFont

from ui.theme import (
    COLOR_BG_ROOT, COLOR_BORDER_DEFAULT,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY
)


def create_splash_pixmap() -> QPixmap:
    """Crea un gráfico limpio y estandarizado para la pantalla de carga inicial."""
    pixmap = QPixmap(420, 200)
    pixmap.fill(QColor(COLOR_BG_ROOT))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    # Borde sutil estándar
    painter.setPen(QColor(COLOR_BORDER_DEFAULT))
    painter.drawRect(0, 0, 419, 199)

    # Título principal
    painter.setPen(QColor(COLOR_TEXT_PRIMARY))
    font_title = QFont("Segoe UI", 16, QFont.DemiBold)
    painter.setFont(font_title)
    painter.drawText(24, 75, "IA Background Remover")

    # Subtítulo técnico
    painter.setPen(QColor(COLOR_TEXT_SECONDARY))
    font_sub = QFont("Segoe UI", 11)
    painter.setFont(font_sub)
    painter.drawText(24, 115, "Iniciando motor de IA y base de datos...")

    painter.end()
    return pixmap


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("IA Background Remover")

    # 1. Mostrar Splash Screen / Loader inmediatamente
    splash = QSplashScreen(create_splash_pixmap(), Qt.WindowStaysOnTopHint)
    splash.show()
    app.processEvents()

    # 2. Inicialización de módulos
    splash.showMessage(
        "Inicializando módulos de interfaz...",
        Qt.AlignBottom | Qt.AlignLeft,
        QColor(COLOR_TEXT_SECONDARY)
    )
    app.processEvents()

    from ui.main_window import MainWindow

    splash.showMessage(
        "Verificando servicios y base de datos...",
        Qt.AlignBottom | Qt.AlignLeft,
        QColor(COLOR_TEXT_SECONDARY)
    )
    app.processEvents()

    # Instanciar ventana principal
    window = MainWindow()

    # 3. Mostrar ventana y finalizar splash
    window.show()
    splash.finish(window)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
