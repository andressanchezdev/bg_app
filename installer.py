import sys
import os
import shutil
import zipfile
import subprocess
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QWizard, QWizardPage, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QProgressBar,
    QFileDialog, QMessageBox, QFrame
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon, QFont

APP_NAME = "IA Background Remover"
APP_EXE_NAME = "IABackgroundRemover.exe"
DEFAULT_INSTALL_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "Programs",
    "IABackgroundRemover"
)

INSTALLER_STYLE = """
QWizard, QWizardPage, QWidget {
    background-color: #0e0e11;
    color: #f4f4f5;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 12px;
}
QFrame#card {
    background-color: #16161a;
    border: 1px solid #25252e;
    border-radius: 8px;
}
QLabel#h1 {
    font-size: 18px;
    font-weight: 600;
    color: #ffffff;
}
QLabel#body {
    font-size: 12px;
    color: #9e9ea8;
}
QLabel#caption {
    font-size: 11px;
    color: #71717a;
}
QLineEdit {
    background-color: #16161a;
    border: 1px solid #25252e;
    border-radius: 6px;
    padding: 6px 10px;
    color: #ffffff;
}
QPushButton {
    background-color: #16161a;
    color: #f4f4f5;
    border: 1px solid #25252e;
    border-radius: 6px;
    padding: 6px 16px;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #1c1c22;
    border-color: #3e3e4a;
}
QPushButton#primaryBtn {
    background-color: #ffffff;
    color: #0e0e11;
    font-weight: 600;
}
QPushButton#primaryBtn:hover {
    background-color: #e4e4e7;
}
QProgressBar {
    background-color: #16161a;
    border: 1px solid #25252e;
    border-radius: 4px;
    height: 8px;
    text-align: center;
}
QProgressBar::chunk {
    background-color: #4ade80;
    border-radius: 3px;
}
"""


def create_windows_shortcut(target_exe: str, shortcut_path: str, description: str = ""):
    """Crea un acceso directo .lnk en Windows utilizando WScript.Shell de Windows nativo."""
    try:
        vbs_script = f"""
Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = "{shortcut_path}"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "{target_exe}"
oLink.WorkingDirectory = "{os.path.dirname(target_exe)}"
oLink.Description = "{description}"
oLink.Save
"""
        temp_vbs = os.path.join(os.environ.get("TEMP", os.getcwd()), "create_lnk.vbs")
        with open(temp_vbs, "w", encoding="utf-8") as f:
            f.write(vbs_script)
        subprocess.run(["cscript", "//nologo", temp_vbs], check=True, creationflags=0x08000000)
        if os.path.exists(temp_vbs):
            os.remove(temp_vbs)
    except Exception as e:
        print(f"[Error creando shortcut]: {e}")


class InstallWorker(QThread):
    progress = Signal(int, str)
    finished_install = Signal(bool, str)

    def __init__(self, target_dir: str, create_desktop: bool, create_startmenu: bool, source_dir: str):
        super().__init__()
        self.target_dir = target_dir
        self.create_desktop = create_desktop
        self.create_startmenu = create_startmenu
        self.source_dir = source_dir

    def run(self):
        try:
            self.progress.emit(10, "Creando directorio de destino...")
            os.makedirs(self.target_dir, exist_ok=True)

            # 1. Copiar archivos del programa
            self.progress.emit(25, "Copiando binarios y motor neuronal U2-Net...")
            payload_zip = os.path.join(self.source_dir, "app_payload.zip")

            if os.path.exists(payload_zip):
                with zipfile.ZipFile(payload_zip, 'r') as zf:
                    total_files = len(zf.namelist())
                    for idx, member in enumerate(zf.namelist()):
                        zf.extract(member, self.target_dir)
                        if idx % 10 == 0:
                            pct = 25 + int((idx / total_files) * 50)
                            self.progress.emit(pct, f"Extrayendo: {os.path.basename(member)}")
            elif os.path.exists(os.path.join(self.source_dir, "IABackgroundRemover")):
                src_app = os.path.join(self.source_dir, "IABackgroundRemover")
                for root, dirs, files in os.walk(src_app):
                    rel = os.path.relpath(root, src_app)
                    dest_dir = os.path.join(self.target_dir, rel) if rel != "." else self.target_dir
                    os.makedirs(dest_dir, exist_ok=True)
                    for f in files:
                        shutil.copy2(os.path.join(root, f), os.path.join(dest_dir, f))
            else:
                raise FileNotFoundError("No se encontró el paquete de la aplicación para instalar.")

            # 2. Configurar desinstalador
            self.progress.emit(80, "Generando desinstalador...")
            exe_installed = os.path.join(self.target_dir, APP_EXE_NAME)
            uninstall_bat = os.path.join(self.target_dir, "uninstall.bat")
            with open(uninstall_bat, "w", encoding="utf-8") as f:
                f.write(f"""@echo off
echo Desinstalando {APP_NAME}...
taskkill /F /IM {APP_EXE_NAME} >nul 2>&1
timeout /t 1 >nul
rmdir /s /q "{self.target_dir}"
echo {APP_NAME} ha sido desinstalado de su equipo.
pause
""")

            # 3. Accesos directos
            if self.create_desktop:
                self.progress.emit(88, "Creando acceso directo en el Escritorio...")
                desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")
                shortcut_desktop = os.path.join(desktop_dir, f"{APP_NAME}.lnk")
                create_windows_shortcut(exe_installed, shortcut_desktop, APP_NAME)

            if self.create_startmenu:
                self.progress.emit(94, "Creando acceso directo en el Menú Inicio...")
                startmenu_dir = os.path.join(
                    os.environ.get("APPDATA", os.path.expanduser("~")),
                    "Microsoft", "Windows", "Start Menu", "Programs", APP_NAME
                )
                os.makedirs(startmenu_dir, exist_ok=True)
                shortcut_start = os.path.join(startmenu_dir, f"{APP_NAME}.lnk")
                create_windows_shortcut(exe_installed, shortcut_start, APP_NAME)

            self.progress.emit(100, "Instalación completada exitosamente.")
            self.finished_install.emit(True, exe_installed)

        except Exception as e:
            self.finished_install.emit(False, str(e))


class PageWelcome(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Bienvenido")
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        lbl_head = QLabel("INSTALADOR DE ESCRITORIO")
        lbl_head.setObjectName("caption")
        layout.addWidget(lbl_head)

        lbl_title = QLabel(f"{APP_NAME}")
        lbl_title.setObjectName("h1")
        layout.addWidget(lbl_title)

        lbl_desc = QLabel(
            "Este asistente instalará IA Background Remover & WebP Optimizer en su equipo.\n\n"
            "Incluye:\n"
            "• Red neuronal U2-Net offline de alta precisión para remoción de fondos.\n"
            "• Optimizador y renderizador nativo WebP.\n"
            "• Integración y distribución directa con catálogo en Google Cloud Storage.\n"
            "• Editor interactivo de retoque manual con pincel y borrador.\n\n"
            "Haga clic en 'Siguiente' para comenzar."
        )
        lbl_desc.setObjectName("body")
        lbl_desc.setWordWrap(True)
        layout.addWidget(lbl_desc)
        layout.addStretch()


class PageDirectory(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Carpeta de Destino")
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        lbl_head = QLabel("UBICACIÓN DEL PROGRAMA")
        lbl_head.setObjectName("caption")
        layout.addWidget(lbl_head)

        lbl_title = QLabel("Seleccione la carpeta de instalación")
        lbl_title.setObjectName("h1")
        layout.addWidget(lbl_title)

        lbl_sub = QLabel("El programa se instalará en la siguiente ruta:")
        lbl_sub.setObjectName("body")
        layout.addWidget(lbl_sub)

        row_dir = QHBoxLayout()
        self.txt_dir = QLineEdit(DEFAULT_INSTALL_DIR)
        row_dir.addWidget(self.txt_dir)

        btn_browse = QPushButton("Examinar...")
        btn_browse.clicked.connect(self._browse)
        row_dir.addWidget(btn_browse)
        layout.addLayout(row_dir)

        layout.addSpacing(10)
        self.chk_desktop = QCheckBox("Crear acceso directo en el Escritorio")
        self.chk_desktop.setChecked(True)
        layout.addWidget(self.chk_desktop)

        self.chk_startmenu = QCheckBox("Crear acceso directo en el Menú Inicio")
        self.chk_startmenu.setChecked(True)
        layout.addWidget(self.chk_startmenu)

        layout.addStretch()

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta", self.txt_dir.text())
        if folder:
            self.txt_dir.setText(os.path.join(folder, "IABackgroundRemover"))


class PageInstall(QWizardPage):
    def __init__(self, wizard):
        super().__init__()
        self.wizard_parent = wizard
        self.setTitle("Instalando")
        self.is_done = False

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        lbl_head = QLabel("PROCESO DE INSTALACIÓN")
        lbl_head.setObjectName("caption")
        layout.addWidget(lbl_head)

        lbl_title = QLabel("Instalando componentes...")
        lbl_title.setObjectName("h1")
        layout.addWidget(lbl_title)

        self.lbl_status = QLabel("Iniciando copia de archivos...")
        self.lbl_status.setObjectName("body")
        layout.addWidget(self.lbl_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        layout.addStretch()

    def initializePage(self):
        target = self.wizard_parent.page_dir.txt_dir.text()
        desktop = self.wizard_parent.page_dir.chk_desktop.isChecked()
        startmenu = self.wizard_parent.page_dir.chk_startmenu.isChecked()

        base_src = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        # Si source_dir/dist/IABackgroundRemover existe
        if os.path.exists(os.path.join(base_src, "dist")):
            src_dir = os.path.join(base_src, "dist")
        else:
            src_dir = base_src

        self.worker = InstallWorker(target, desktop, startmenu, src_dir)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_install.connect(self._on_finished)
        self.worker.start()

    def _on_progress(self, val: int, msg: str):
        self.progress_bar.setValue(val)
        self.lbl_status.setText(msg)

    def _on_finished(self, success: bool, res: str):
        self.is_done = True
        self.wizard_parent.installed_exe = res if success else ""
        self.completeChanged.emit()
        if success:
            self.wizard_parent.next()
        else:
            QMessageBox.critical(self, "Error de instalación", f"Ocurrió un error:\n{res}")

    def isComplete(self):
        return self.is_done


class PageFinished(QWizardPage):
    def __init__(self, wizard):
        super().__init__()
        self.wizard_parent = wizard
        self.setTitle("Instalación Completa")
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        lbl_head = QLabel("INSTALACIÓN EXITOSA")
        lbl_head.setObjectName("caption")
        layout.addWidget(lbl_head)

        lbl_title = QLabel("¡Instalación Finalizada!")
        lbl_title.setObjectName("h1")
        layout.addWidget(lbl_title)

        lbl_desc = QLabel(
            f"{APP_NAME} se ha instalado correctamente en su equipo.\n"
            "Puede ejecutar el programa desde los accesos directos creados."
        )
        lbl_desc.setObjectName("body")
        layout.addWidget(lbl_desc)

        layout.addSpacing(12)
        self.chk_launch = QCheckBox("Iniciar IA Background Remover ahora")
        self.chk_launch.setChecked(True)
        layout.addWidget(self.chk_launch)

        layout.addStretch()


class SetupWizard(QWizard):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Instalador - {APP_NAME}")
        self.resize(540, 420)
        self.setStyleSheet(INSTALLER_STYLE)
        self.installed_exe = ""

        self.page_welcome = PageWelcome()
        self.page_dir = PageDirectory()
        self.page_install = PageInstall(self)
        self.page_finished = PageFinished(self)

        self.addPage(self.page_welcome)
        self.addPage(self.page_dir)
        self.addPage(self.page_install)
        self.addPage(self.page_finished)

        self.button(QWizard.NextButton).setObjectName("primaryBtn")
        self.button(QWizard.FinishButton).setObjectName("primaryBtn")

    def accept(self):
        if self.page_finished.chk_launch.isChecked() and self.installed_exe and os.path.exists(self.installed_exe):
            subprocess.Popen([self.installed_exe], cwd=os.path.dirname(self.installed_exe))
        super().accept()


def main():
    app = QApplication(sys.argv)
    wizard = SetupWizard()
    wizard.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

