import argparse
import logging
import os
import sys
import traceback
from logging.handlers import RotatingFileHandler

import app_paths

LOG_FILE = app_paths.logs_dir() / "app.log"


def setup_logging() -> None:
    handlers = [RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8")]
    # En el ejecutable sin consola sys.stdout/sys.stderr son None
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler(sys.stderr))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def install_excepthook() -> None:
    def handle(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        logging.critical("Excepción no controlada", exc_info=(exc_type, exc, tb))
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
            if QApplication.instance() is not None:
                QMessageBox.critical(
                    None, "Error inesperado",
                    f"{exc_type.__name__}: {exc}\n\nDetalle registrado en:\n{LOG_FILE}",
                )
        except Exception:
            pass

    sys.excepthook = handle


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="RemoverBackgroundIP", add_help=False)
    parser.add_argument("--background", action="store_true", help="Iniciar oculto en la bandeja")
    parser.add_argument("--self-test", action="store_true", help="Verificar el empaquetado y salir")
    args, _unknown = parser.parse_known_args(argv)
    return args


def run_self_test() -> int:
    """Valida el ejecutable empaquetado: módulos, modelo, rutas escribibles y servidor."""
    log = logging.getLogger("self-test")
    try:
        import json
        import urllib.request
        from PIL import Image

        import config
        import ui.main_window  # noqa: F401  (verifica que toda la interfaz importa)
        from core.bg_remover import get_model_path, process_remove_background
        from server.api_server import ApiServer

        model = get_model_path()
        assert model, "No se encontró models/u2net.onnx en el paquete"
        log.info("Modelo: %s", model)

        out = process_remove_background(Image.new("RGB", (64, 64), (255, 255, 255)))
        assert out.mode == "RGBA", "La inferencia no devolvió RGBA"

        probe = app_paths.output_dir() / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()

        srv = ApiServer()
        assert srv.start(port=0, host="127.0.0.1"), srv.last_error
        with urllib.request.urlopen(f"http://127.0.0.1:{srv.port}/health", timeout=10) as r:
            health = json.loads(r.read().decode("utf-8"))
        srv.stop()
        assert health.get("status") == "ok", health
        log.info("SELF-TEST OK v%s (datos en %s)", config.APP_VERSION, app_paths.user_data_dir())
        return 0
    except Exception:
        log.error("SELF-TEST FALLÓ\n%s", traceback.format_exc())
        return 1


def create_splash():
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
    from PySide6.QtWidgets import QSplashScreen
    from ui.theme import COLOR_BG_ROOT, COLOR_BORDER_DEFAULT, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY

    pixmap = QPixmap(420, 200)
    pixmap.fill(QColor(COLOR_BG_ROOT))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QColor(COLOR_BORDER_DEFAULT))
    painter.drawRect(0, 0, 419, 199)
    painter.setPen(QColor(COLOR_TEXT_PRIMARY))
    painter.setFont(QFont("Segoe UI", 16, QFont.DemiBold))
    painter.drawText(24, 75, "Remover Background IP")
    painter.setPen(QColor(COLOR_TEXT_SECONDARY))
    painter.setFont(QFont("Segoe UI", 11))
    painter.drawText(24, 115, "Iniciando motor de IA y base de datos...")
    painter.end()
    return QSplashScreen(pixmap, Qt.WindowStaysOnTopHint)


def main() -> int:
    setup_logging()
    install_excepthook()
    args = parse_args(sys.argv[1:])
    log = logging.getLogger("main")

    if args.self_test:
        return run_self_test()

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    import config
    app.setApplicationName(config.APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    # Tema oscuro para toda la app, independiente del modo claro/oscuro de Windows
    from ui.theme import apply_app_theme
    apply_app_theme(app)

    from single_instance import SingleInstance
    instance = SingleInstance()
    if instance.notify_running_instance():
        log.info("Ya hay una instancia en ejecución; se le pidió mostrarse.")
        return 0

    log.info("Iniciando v%s (background=%s, datos=%s)", config.APP_VERSION, args.background, app_paths.user_data_dir())

    splash = None
    if not args.background:
        splash = create_splash()
        splash.show()
        app.processEvents()

    from ui.main_window import MainWindow
    from ui.tray import BackgroundController, app_icon

    app.setWindowIcon(app_icon())
    controller = BackgroundController(app, MainWindow)
    instance.acquire(on_show=controller.show_window)

    if args.background:
        # Precarga del modelo para que la API responda rápido desde la primera petición
        from core.bg_remover import get_ai_session
        get_ai_session()
    else:
        controller.show_window()
        splash.finish(controller.window)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
