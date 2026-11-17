"""
Resolución centralizada de rutas para desarrollo y ejecutable empaquetado (PyInstaller).

- resource_dir(): archivos de solo lectura incluidos en el paquete (models/, .env, credentials/).
- install_dir():  carpeta donde está el .exe instalado (o la raíz del repo en desarrollo).
- user_data_dir(): carpeta escribible del usuario (ajustes, salidas, logs, trabajos de la API).

Nunca se escribe en install_dir() en modo empaquetado: puede estar en "Program Files"
(solo lectura) y el directorio de trabajo puede ser System32 cuando arranca con Windows.
"""
import os
import sys
import shutil
from pathlib import Path

APP_DIR_NAME = "RemoverBackgroundIP"
LEGACY_APP_DIR_NAMES = ("IABackgroundRemover",)
REPO_DIR = Path(__file__).resolve().parent


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def install_dir() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return REPO_DIR


def resource_dir() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return REPO_DIR


def resource_candidates() -> list:
    """Ubicaciones posibles para recursos empaquetados, en orden de prioridad."""
    seen, result = set(), []
    for p in (resource_dir(), install_dir(), install_dir() / "_internal", REPO_DIR):
        key = str(p).lower()
        if key not in seen:
            seen.add(key)
            result.append(p)
    return result


def find_resource(relative: str):
    """Retorna la primera ruta existente del recurso o None."""
    for base in resource_candidates():
        p = base / relative
        if p.exists():
            return p
    return None


def user_data_dir() -> Path:
    if is_frozen():
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        path = base / APP_DIR_NAME
    else:
        path = REPO_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def output_dir() -> Path:
    p = user_data_dir() / "output"
    p.mkdir(parents=True, exist_ok=True)
    return p


def processed_dir() -> Path:
    p = output_dir() / "processed"
    p.mkdir(parents=True, exist_ok=True)
    return p


def logs_dir() -> Path:
    p = user_data_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def jobs_dir() -> Path:
    p = user_data_dir() / "jobs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def migrate_legacy_files() -> None:
    """
    Copia ajustes de versiones anteriores a la carpeta de datos actual (solo si aún no existen):
    - v1: guardados junto al .exe (install_dir()/output).
    - v2.0: carpeta IABackgroundRemover en LOCALAPPDATA (antes del cambio de nombre).
    """
    if not is_frozen():
        return
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    sources = [local / name for name in LEGACY_APP_DIR_NAMES] + [install_dir()]
    for base in sources:
        for rel in ("output/settings.json", "output/db_config.json", ".env", "credentials/gcp_key.json"):
            src, dst = base / rel, user_data_dir() / rel
            if src.exists() and not dst.exists():
                try:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                except OSError:
                    pass
