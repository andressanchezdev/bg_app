import sys
import os
from PySide6.QtWidgets import QApplication, QSplashScreen
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QColor, QPainter, QFont


def create_splash_pixmap() -> QPixmap:
    """Crea un gráfico limpio para la pantalla de carga inicial."""
    pixmap = QPixmap(420, 220)
    pixmap.fill(QColor("#1e1e1e"))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    # Borde y título
    painter.setPen(QColor("#3a3a3a"))
    painter.drawRect(0, 0, 419, 219)

    # Texto del título
    painter.setPen(QColor("#ffffff"))
    font_title = QFont("Arial", 16, QFont.Bold)
    painter.setFont(font_title)
    painter.drawText(20, 80, "IA Background Remover")

    # Subtexto / Estado
    painter.setPen(QColor("#a0a0a0"))
    font_sub = QFont("Arial", 10)
    painter.setFont(font_sub)
    painter.drawText(20, 130, "Cargando modelos de IA y módulos de interfaz...")

    painter.end()
    return pixmap


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("IA Background Remover")

    # 1. Mostrar Splash Screen / Loader inmediatamente
    splash = QSplashScreen(create_splash_pixmap(), Qt.WindowStaysOnTopHint)
    splash.show()
    app.processEvents()

    # 2. Importar MainWindow e inicializar componentes pesados mientras se muestra el loader
    splash.showMessage(
        "Inicializando módulos de UI...",
        Qt.AlignBottom | Qt.AlignLeft,
        QColor("#e0e0e0")
    )
    app.processEvents()

    from ui.main_window import MainWindow

    splash.showMessage(
        "Cargando motor de IA...",
        Qt.AlignBottom | Qt.AlignLeft,
        QColor("#e0e0e0")
    )
    app.processEvents()

    # Instanciar la ventana principal (carga sesión ONNX/rembg)
    window = MainWindow()

    # 3. Mostrar la ventana principal y ocultar el splash screen
    window.show()
    splash.finish(window)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()