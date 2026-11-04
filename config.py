import os
import sys
import json
from pathlib import Path

# Ruta base del proyecto (compatible con ejecutable congelado PyInstaller)
if getattr(sys, "frozen", False):
    BASE_DIR = Path(os.path.dirname(sys.executable))
else:
    BASE_DIR = Path(__file__).resolve().parent

# ==============================================================================
# CONFIGURACIÓN DE REDIMENSIONAMIENTO Y CALIDAD DE SALIDA
# ==============================================================================
DEFAULT_RESIZE_ENABLED = False     # Redimensionar por defecto
DEFAULT_OUTPUT_WIDTH = 900        # Ancho estándar
DEFAULT_OUTPUT_HEIGHT = 900       # Alto estándar
DEFAULT_RESIZE_MODE = "contain"

DEFAULT_WEBP_QUALITY = 90
DEFAULT_AI_MODEL = "u2net"

# ==============================================================================
# APARIENCIA E INTERFAZ
# ==============================================================================
THEME = "dark"  # Opciones: "dark" / "light"

# ==============================================================================
# INTEGRACIÓN CON GOOGLE CLOUD STORAGE (GCP)
# ==============================================================================
CLOUD_UPLOAD_ENABLED = False

GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "importadorapremiumonline")
GCS_BASE_FOLDER = os.getenv("GCS_BASE_FOLDER", "dependencias/img/productos/")

GCP_KEY_PATH = "credentials/gcp_key.json"

def resolve_credentials_path() -> str:
    """Busca el archivo gcp_key.json en todas las ubicaciones posibles."""
    env_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if env_path and os.path.exists(env_path):
        return env_path

    candidates = [
        BASE_DIR / GCP_KEY_PATH,
        BASE_DIR / "_internal" / GCP_KEY_PATH,
        Path(os.getcwd()) / GCP_KEY_PATH,
        Path(getattr(sys, "_MEIPASS", "")) / GCP_KEY_PATH if getattr(sys, "_MEIPASS", None) else None,
        Path.home() / "Desktop" / "gcp_key.json",
        Path("C:/Users/Usuario/Desktop/gcp_key.json")
    ]
    for c in candidates:
        if c and os.path.exists(str(c)):
            return str(c.resolve())
    return str(BASE_DIR / GCP_KEY_PATH)

GCS_CREDENTIALS_PATH = resolve_credentials_path()

if os.path.exists(GCS_CREDENTIALS_PATH):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = GCS_CREDENTIALS_PATH

GCS_MAKE_PUBLIC = True

# ==============================================================================
# GESTOR DE AJUSTES EN ARCHIVO JSON (SIN BASE DE DATOS)
# ==============================================================================
SETTINGS_FILE = BASE_DIR / "output" / "settings.json"

def load_settings():
    global THEME, GCS_BUCKET_NAME, GCS_BASE_FOLDER, CLOUD_UPLOAD_ENABLED
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                THEME = data.get("theme", THEME)
                GCS_BUCKET_NAME = data.get("gcs_bucket_name", GCS_BUCKET_NAME)
                GCS_BASE_FOLDER = data.get("gcs_base_folder", GCS_BASE_FOLDER)
                CLOUD_UPLOAD_ENABLED = data.get("cloud_upload_enabled", CLOUD_UPLOAD_ENABLED)
        except Exception as e:
            print(f"[Config load warning]: {e}")

def save_settings(theme=None, bucket_name=None, base_folder=None, cloud_upload_enabled=None):
    global THEME, GCS_BUCKET_NAME, GCS_BASE_FOLDER, CLOUD_UPLOAD_ENABLED
    if theme is not None:
        THEME = theme
    if bucket_name is not None:
        GCS_BUCKET_NAME = bucket_name
    if base_folder is not None:
        GCS_BASE_FOLDER = base_folder
    if cloud_upload_enabled is not None:
        CLOUD_UPLOAD_ENABLED = cloud_upload_enabled

    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = {
            "theme": THEME,
            "gcs_bucket_name": GCS_BUCKET_NAME,
            "gcs_base_folder": GCS_BASE_FOLDER,
            "cloud_upload_enabled": CLOUD_UPLOAD_ENABLED
        }
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Config save warning]: {e}")

# Cargar ajustes guardados al iniciar módulo
load_settings()
