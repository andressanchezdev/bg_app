import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame
)
from PySide6.QtCore import Qt
from ui.theme import GLOBAL_THEME, COLOR_STATUS_ERR, COLOR_BORDER_DEFAULT


class SettingsLoginDialog(QDialog):
    """
    Modal de autenticación ligero para proteger el acceso a las configuraciones del sistema.
    Valida credenciales contra variables de entorno (.env: USER=USER, PASSWORD=123456).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Acceso Restringido - Configuración")
        self.resize(420, 310)
        self.setFixedSize(420, 310)
        self.setModal(True)
        self.setStyleSheet(GLOBAL_THEME)

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Encabezado
        lbl_badge = QLabel("SEGURIDAD DEL SISTEMA")
        lbl_badge.setObjectName("caption")
        layout.addWidget(lbl_badge)

        lbl_title = QLabel("Acceso a Configuración")
        lbl_title.setObjectName("h1")
        layout.addWidget(lbl_title)

        lbl_sub = QLabel("Ingresa tus credenciales de administrador para gestionar las configuraciones de GCP y la interfaz.")
        lbl_sub.setObjectName("body")
        lbl_sub.setWordWrap(True)
        layout.addWidget(lbl_sub)

        # Formulario
        form_card = QFrame()
        form_card.setObjectName("card")
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(14, 12, 14, 12)
        form_layout.setSpacing(10)

        # Campo Usuario
        row_user = QVBoxLayout()
        row_user.setSpacing(4)
        lbl_u = QLabel("Usuario:")
        lbl_u.setObjectName("caption")
        row_user.addWidget(lbl_u)
        self.txt_user = QLineEdit()
        self.txt_user.setPlaceholderText("Usuario (ej: USER)")
        self.txt_user.setText("USER")
        self.txt_user.returnPressed.connect(self._do_login)
        row_user.addWidget(self.txt_user)
        form_layout.addLayout(row_user)

        # Campo Contraseña
        row_pass = QVBoxLayout()
        row_pass.setSpacing(4)
        lbl_p = QLabel("Contraseña:")
        lbl_p.setObjectName("caption")
        row_pass.addWidget(lbl_p)
        self.txt_pass = QLineEdit()
        self.txt_pass.setEchoMode(QLineEdit.Password)
        self.txt_pass.setPlaceholderText("••••••••")
        self.txt_pass.returnPressed.connect(self._do_login)
        row_pass.addWidget(self.txt_pass)
        form_layout.addLayout(row_pass)

        # Mensaje de error
        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("caption")
        self.lbl_error.setStyleSheet(f"color: {COLOR_STATUS_ERR}; font-weight: bold;")
        self.lbl_error.setVisible(False)
        form_layout.addWidget(self.lbl_error)

        layout.addWidget(form_card)

        # Botones de pie
        bottom_layout = QHBoxLayout()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        bottom_layout.addWidget(btn_cancel)

        bottom_layout.addStretch()

        self.btn_login = QPushButton("Ingresar")
        self.btn_login.setObjectName("primaryBtn")
        self.btn_login.setCursor(Qt.PointingHandCursor)
        self.btn_login.clicked.connect(self._do_login)
        bottom_layout.addWidget(self.btn_login)

        layout.addLayout(bottom_layout)

        # Foco inicial en la contraseña
        self.txt_pass.setFocus()

    def _do_login(self):
        user = self.txt_user.text().strip()
        pwd = self.txt_pass.text().strip()

        if not user or not pwd:
            self.lbl_error.setText("Por favor ingresa usuario y contraseña.")
            self.lbl_error.setVisible(True)
            return

        expected_user = os.getenv("USER", "USER")
        expected_pwd = os.getenv("PASSWORD", "123456")

        if user == expected_user and pwd == expected_pwd:
            self.lbl_error.setVisible(False)
            self.accept()
        else:
            self.lbl_error.setText("Credenciales incorrectas. Verifica el usuario o contraseña.")
            self.lbl_error.setVisible(True)
            self.txt_pass.selectAll()
            self.txt_pass.setFocus()
