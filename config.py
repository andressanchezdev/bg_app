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

# ==============================================
# VARIABLES DE ENTORNO (.env) Y BASE DE DATOS
# ==============================================
ENV_FILE = BASE_DIR / ".env"
def load_env_defaults():
    if ENV_FILE.exists():
        try:
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip().strip('"').strip("'")
                        os.environ[k] = v
        except Exception:
            pass

load_env_defaults()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_DATABASE = os.getenv("DB_DATABASE", os.getenv("DB_NAME", "mysql"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password_123")
DB_TABLE = os.getenv("DB_TABLE", "productos")
DB_API_ENDPOINT = ""
DB_SYNC_MODE = "db"

# ==============================================================================
# GESTOR DE AJUSTES EN ARCHIVO JSON
# ==============================================================================
SETTINGS_FILE = BASE_DIR / "output" / "settings.json"

def load_settings():
    global THEME, GCS_BUCKET_NAME, GCS_BASE_FOLDER, CLOUD_UPLOAD_ENABLED
    global DB_HOST, DB_PORT, DB_DATABASE, DB_USER, DB_PASSWORD, DB_TABLE, DB_API_ENDPOINT, DB_SYNC_MODE
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                THEME = data.get("theme", THEME)
                GCS_BUCKET_NAME = data.get("gcs_bucket_name", GCS_BUCKET_NAME)
                GCS_BASE_FOLDER = data.get("gcs_base_folder", GCS_BASE_FOLDER)
                CLOUD_UPLOAD_ENABLED = data.get("cloud_upload_enabled", CLOUD_UPLOAD_ENABLED)
                DB_HOST = data.get("db_host", DB_HOST)
                DB_PORT = int(data.get("db_port", DB_PORT))
                DB_DATABASE = data.get("db_database", DB_DATABASE)
                DB_USER = data.get("db_user", DB_USER)
                DB_PASSWORD = data.get("db_password", DB_PASSWORD)
                DB_TABLE = data.get("db_table", DB_TABLE)
                DB_API_ENDPOINT = data.get("db_api_endpoint", DB_API_ENDPOINT)
                DB_SYNC_MODE = data.get("db_sync_mode", DB_SYNC_MODE)
        except Exception as e:
            print(f"[Config load warning]: {e}")

def save_settings(
    theme=None,
    bucket_name=None,
    base_folder=None,
    cloud_upload_enabled=None,
    db_host=None,
    db_port=None,
    db_database=None,
    db_user=None,
    db_password=None,
    db_table=None,
    db_api_endpoint=None,
    db_sync_mode=None
):
    global THEME, GCS_BUCKET_NAME, GCS_BASE_FOLDER, CLOUD_UPLOAD_ENABLED
    global DB_HOST, DB_PORT, DB_DATABASE, DB_USER, DB_PASSWORD, DB_TABLE, DB_API_ENDPOINT, DB_SYNC_MODE
    if theme is not None:
        THEME = theme
    if bucket_name is not None:
        GCS_BUCKET_NAME = bucket_name
    if base_folder is not None:
        GCS_BASE_FOLDER = base_folder
    if cloud_upload_enabled is not None:
        CLOUD_UPLOAD_ENABLED = cloud_upload_enabled
    if db_host is not None:
        DB_HOST = db_host
    if db_port is not None:
        DB_PORT = int(db_port)
    if db_database is not None:
        DB_DATABASE = db_database
    if db_user is not None:
        DB_USER = db_user
    if db_password is not None:
        DB_PASSWORD = db_password
    if db_table is not None:
        DB_TABLE = db_table
    if db_api_endpoint is not None:
        DB_API_ENDPOINT = db_api_endpoint
    if db_sync_mode is not None:
        DB_SYNC_MODE = db_sync_mode

    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = {
            "theme": THEME,
            "gcs_bucket_name": GCS_BUCKET_NAME,
            "gcs_base_folder": GCS_BASE_FOLDER,
            "cloud_upload_enabled": CLOUD_UPLOAD_ENABLED,
            "db_host": DB_HOST,
            "db_port": DB_PORT,
            "db_database": DB_DATABASE,
            "db_user": DB_USER,
            "db_password": DB_PASSWORD,
            "db_table": DB_TABLE,
            "db_api_endpoint": DB_API_ENDPOINT,
            "db_sync_mode": DB_SYNC_MODE
        }
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Config save warning]: {e}")

# Cargar ajustes guardados al iniciar módulo
load_settings()
