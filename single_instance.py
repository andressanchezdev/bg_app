"""
Instancia única de la aplicación.

- Mutex con nombre de Windows: lo usa Inno Setup (AppMutex) para detectar/cerrar la app
  durante una actualización o desinstalación.
- QLocalServer: si se abre un segundo proceso (p. ej. desde el acceso directo mientras la app
  corre en la bandeja), avisa al primero para que muestre su ventana y termina.
"""
import sys
from typing import Callable, Optional

from PySide6.QtCore import QObject
from PySide6.QtNetwork import QLocalServer, QLocalSocket

MUTEX_NAME = "RemoverBackgroundIP_Mutex"
SOCKET_NAME = "RemoverBackgroundIP_Instance"
SHOW_COMMAND = b"show"


class SingleInstance(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._server: Optional[QLocalServer] = None
        self._mutex_handle = None
        self._on_show: Optional[Callable[[], None]] = None

    def notify_running_instance(self) -> bool:
        """True si ya hay otra instancia (y se le pidió mostrarse)."""
        sock = QLocalSocket()
        sock.connectToServer(SOCKET_NAME)
        if sock.waitForConnected(500):
            sock.write(SHOW_COMMAND)
            sock.waitForBytesWritten(500)
            sock.disconnectFromServer()
            return True
        return False

    def acquire(self, on_show: Callable[[], None]) -> None:
        self._on_show = on_show
        self._create_mutex()
        QLocalServer.removeServer(SOCKET_NAME)  # limpia un socket huérfano tras un cierre abrupto
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._handle_connection)
        self._server.listen(SOCKET_NAME)

    def _handle_connection(self) -> None:
        conn = self._server.nextPendingConnection()
        if conn is None:
            return
        conn.waitForReadyRead(500)
        if conn.readAll().data().startswith(SHOW_COMMAND) and self._on_show:
            self._on_show()
        conn.disconnectFromServer()

    def _create_mutex(self) -> None:
        if sys.platform != "win32":
            return
        try:
            import ctypes
            self._mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
        except Exception:
            self._mutex_handle = None
