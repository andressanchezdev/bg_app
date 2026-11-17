"""
Ejecución en segundo plano: icono en la bandeja del sistema y control del servidor de red.
"""
import logging

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

import app_paths
import config
from server.api_server import ApiServer

log = logging.getLogger(__name__)


def app_icon() -> QIcon:
    found = app_paths.find_resource("assets/app.ico")
    if found:
        return QIcon(str(found))
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#4ade80"))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(4, 4, 56, 56, 12, 12)
    p.setPen(QColor("#0e0e11"))
    p.setFont(QFont("Segoe UI", 22, QFont.Bold))
    p.drawText(pix.rect(), Qt.AlignCenter, "IA")
    p.end()
    return QIcon(pix)


class BackgroundController(QObject):
    """Une ventana principal, bandeja del sistema y servidor HTTP."""

    def __init__(self, app: QApplication, window_factory, parent=None):
        super().__init__(parent)
        self.app = app
        self._window_factory = window_factory
        self.window = None
        self.server = ApiServer()
        self._tray_hint_shown = False

        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip(config.APP_NAME)
        self.tray.activated.connect(self._on_tray_activated)
        self._build_menu()
        self.tray.show()

        self.apply_server_settings()

    # -- servidor -------------------------------------------------------------------------
    def apply_server_settings(self) -> None:
        if config.SERVER_ENABLED:
            if not self.server.start(config.SERVER_PORT):
                self.tray.showMessage("Servidor de red", self.server.last_error, QSystemTrayIcon.Warning, 8000)
        else:
            self.server.stop()
        self._refresh_menu()

    def toggle_server(self) -> None:
        config.save_settings(server_enabled=not self.server.is_running)
        self.apply_server_settings()

    # -- ventana --------------------------------------------------------------------------
    def ensure_window(self):
        if self.window is None:
            self.window = self._window_factory()
            self.window.hidden_to_tray.connect(self._on_hidden_to_tray)
            self.window.server_settings_changed.connect(self.apply_server_settings)
        return self.window

    def show_window(self) -> None:
        win = self.ensure_window()
        win.showNormal()
        win.raise_()
        win.activateWindow()

    def _on_hidden_to_tray(self) -> None:
        if not self._tray_hint_shown:
            self._tray_hint_shown = True
            self.tray.showMessage(
                "Sigue en segundo plano",
                "La aplicación continúa escuchando en la red. Use el icono de la bandeja para abrirla o salir.",
                QSystemTrayIcon.Information, 5000,
            )

    def quit(self) -> None:
        if self.window is not None and not self.window.confirm_quit():
            return
        self.server.stop()
        self.tray.hide()
        if self.window is not None:
            self.window.allow_close = True
            self.window.close()
        self.app.quit()

    # -- menú -----------------------------------------------------------------------------
    def _build_menu(self) -> None:
        self.menu = QMenu()
        act_open = QAction(f"Abrir {config.APP_NAME}", self.menu)
        act_open.triggered.connect(self.show_window)
        self.menu.addAction(act_open)
        self.menu.addSeparator()

        self.act_status = QAction("", self.menu)
        self.act_status.setToolTip("Copiar dirección")
        self.act_status.triggered.connect(self._copy_url)
        self.menu.addAction(self.act_status)

        self.act_toggle = QAction("", self.menu)
        self.act_toggle.triggered.connect(self.toggle_server)
        self.menu.addAction(self.act_toggle)
        self.menu.addSeparator()

        act_quit = QAction("Salir", self.menu)
        act_quit.triggered.connect(self.quit)
        self.menu.addAction(act_quit)
        self.tray.setContextMenu(self.menu)

    def _refresh_menu(self) -> None:
        if self.server.is_running:
            url = self.server.urls()[0]
            self.act_status.setText(f"Servidor activo: {url}  (copiar)")
            self.act_status.setEnabled(True)
            self.act_toggle.setText("Detener servidor de red")
            self.tray.setToolTip(f"{config.APP_NAME}\nEscuchando en {url}")
        else:
            reason = self.server.last_error or "Servidor de red detenido"
            self.act_status.setText(reason[:80])
            self.act_status.setEnabled(False)
            self.act_toggle.setText("Iniciar servidor de red")
            self.tray.setToolTip(f"{config.APP_NAME}\nServidor detenido")

    def _copy_url(self) -> None:
        if self.server.is_running:
            QApplication.clipboard().setText(self.server.urls()[0])

    def _on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger):
            self.show_window()
