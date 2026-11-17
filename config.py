import os
import sys
import json
import secrets
from pathlib import Path

import app_paths

APP_NAME = "Remover Background IP"
APP_VERSION = "2.1.0"

# Ruta base del programa (solo lectura en modo empaquetado)
BASE_DIR = app_paths.install_dir()
# Carpeta escribible del usuario (%LOCALAPPDATA%\RemoverBackgroundIP en modo empaquetado)
USER_DATA_DIR = app_paths.user_data_dir()
app_paths.migrate_legacy_files()

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
# URL pública con la que se consumen las imágenes; vacía = https://storage.googleapis.com/<bucket>/
GCS_PUBLIC_BASE_URL = ""

GCP_KEY_PATH = "credentials/gcp_key.json"

def resolve_credentials_path() -> str:
    """Busca el archivo gcp_key.json en todas las ubicaciones posibles."""
    env_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if env_path and os.path.exists(env_path):
        return env_path

    candidates = [USER_DATA_DIR / GCP_KEY_PATH]
    candidates += [base / GCP_KEY_PATH for base in app_paths.resource_candidates()]
    candidates.append(Path.home() / "Desktop" / "gcp_key.json")
    for c in candidates:
        if c and os.path.exists(str(c)):
            return str(c.resolve())
    return str(USER_DATA_DIR / GCP_KEY_PATH)

GCS_CREDENTIALS_PATH = resolve_credentials_path()

if os.path.exists(GCS_CREDENTIALS_PATH):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = GCS_CREDENTIALS_PATH

GCS_MAKE_PUBLIC = True

# ==============================================
# VARIABLES DE ENTORNO (.env) Y BASE DE DATOS
# ==============================================
def _resolve_env_file() -> Path:
    """Prioriza un .env editable del usuario y luego el .env empaquetado."""
    user_env = USER_DATA_DIR / ".env"
    if user_env.exists():
        return user_env
    found = app_paths.find_resource(".env")
    return found if found else user_env

ENV_FILE = _resolve_env_file()
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
DB_CODE_COLUMN = os.getenv("DB_CODE_COLUMN", "codigo")
DB_IMAGE_COLUMN = os.getenv("DB_IMAGE_COLUMN", "imagenArray")
DB_API_ENDPOINT = ""
DB_SYNC_MODE = "db"
# motor de la base de productos: "mysql" (MariaDB/HeidiSQL) o "postgres"; vacío = se deduce del puerto (comportamiento anterior)
DB_ENGINE = os.getenv("DB_ENGINE", "")
DB_SCHEMA = os.getenv("DB_SCHEMA", "public")  # solo PostgreSQL
DB_COMPANY_ID = os.getenv("DB_COMPANY_ID", "")  # solo PostgreSQL: vacío = sin filtro de compañía
if not GCS_PUBLIC_BASE_URL:
    GCS_PUBLIC_BASE_URL = os.getenv("GCS_PUBLIC_BASE_URL", os.getenv("BASE_URL", "")).strip()


def public_base_url() -> str:
    """URL pública base de las imágenes, siempre terminada en '/'."""
    base = (GCS_PUBLIC_BASE_URL or "").strip()
    if not base:
        base = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/"
    base = base.rstrip("/") + "/"
    # si la URL trae una carpeta (como BASE_URL del .env, que termina en .../dependencias/img/productos/), se deja solo hasta
    # el bucket: la ruta del objeto ya incluye la carpeta base, y así cambiarla (por ejemplo a .../productos/V2.0) no duplica tramos
    folder = (GCS_BASE_FOLDER or "").strip("/\\").replace("\\", "/")
    first = folder.split("/", 1)[0] if folder else ""
    if first and f"/{first}/" in base:
        base = base[: base.index(f"/{first}/")] + "/"
    return base

# ==============================================================================
# SERVIDOR HTTP EN RED LOCAL (v2)
# ==============================================================================
DEV_SERVER_PORT = 8765
PROD_SERVER_PORT = 48765
SERVER_ENABLED = True
SERVER_HOST = "0.0.0.0"
SERVER_API_KEY = ""
SERVER_MAX_UPLOAD_MB = 500
SERVER_JOB_RETENTION_DAYS = 3


def _installer_default_port() -> int:
    """Puerto elegido en el instalador (server_defaults.json junto al .exe)."""
    path = BASE_DIR / "server_defaults.json"
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                return int(json.load(f).get("server_port", 0))
        except Exception:
            pass
    return 0


INSTALLER_PORT = _installer_default_port()
SERVER_PORT = INSTALLER_PORT or (PROD_SERVER_PORT if app_paths.is_frozen() else DEV_SERVER_PORT)
_installer_port_pending = False

# ==============================================================================
# GESTOR DE AJUSTES EN ARCHIVO JSON
# ==============================================================================
SETTINGS_FILE = app_paths.output_dir() / "settings.json"
SERVER_SETTING_KEYS = ("server_enabled", "server_port", "server_api_key", "server_installer_port")


def seed_settings_from_package():
    """
    Primer arranque de la app instalada: copia la configuración de la v1 incluida en el paquete
    (defaults/settings.json, tomada de output/settings.json al compilar) para que la conexión a
    BD y GCS quede exactamente igual que en la v1. Los ajustes del servidor no se copian.
    """
    if SETTINGS_FILE.exists():
        return
    seed = app_paths.find_resource("defaults/settings.json")
    if not seed:
        return
    try:
        with open(seed, "r", encoding="utf-8") as f:
            data = {k: v for k, v in json.load(f).items() if k not in SERVER_SETTING_KEYS}
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Config seed warning]: {e}")


def load_settings():
    global THEME, GCS_BUCKET_NAME, GCS_BASE_FOLDER, CLOUD_UPLOAD_ENABLED
    global DB_HOST, DB_PORT, DB_DATABASE, DB_USER, DB_PASSWORD, DB_TABLE, DB_CODE_COLUMN, DB_IMAGE_COLUMN, DB_API_ENDPOINT, DB_SYNC_MODE
    global DB_ENGINE, DB_SCHEMA, DB_COMPANY_ID, GCS_PUBLIC_BASE_URL
    global SERVER_ENABLED, SERVER_PORT, SERVER_API_KEY, _installer_port_pending
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
                DB_CODE_COLUMN = data.get("db_code_column", DB_CODE_COLUMN)
                DB_IMAGE_COLUMN = data.get("db_image_column", DB_IMAGE_COLUMN)
                DB_API_ENDPOINT = data.get("db_api_endpoint", DB_API_ENDPOINT)
                DB_SYNC_MODE = data.get("db_sync_mode", DB_SYNC_MODE)
                DB_ENGINE = data.get("db_engine", DB_ENGINE) or ""
                DB_SCHEMA = data.get("db_schema", DB_SCHEMA) or "public"
                DB_COMPANY_ID = str(data.get("db_company_id", DB_COMPANY_ID) or "")
                GCS_PUBLIC_BASE_URL = data.get("gcs_public_base_url", GCS_PUBLIC_BASE_URL) or GCS_PUBLIC_BASE_URL
                SERVER_ENABLED = bool(data.get("server_enabled", SERVER_ENABLED))
                SERVER_PORT = int(data.get("server_port", SERVER_PORT))
                SERVER_API_KEY = data.get("server_api_key", SERVER_API_KEY)
                # Un puerto nuevo elegido en el instalador (instalación/actualización) tiene prioridad
                if INSTALLER_PORT and data.get("server_installer_port") != INSTALLER_PORT:
                    SERVER_PORT = INSTALLER_PORT
                    _installer_port_pending = True
        except Exception as e:
            print(f"[Config load warning]: {e}")
    env_port = os.getenv("BG_APP_PORT")
    if env_port and env_port.isdigit():
        SERVER_PORT = int(env_port)

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
    db_code_column=None,
    db_image_column=None,
    db_api_endpoint=None,
    db_sync_mode=None,
    server_enabled=None,
    server_port=None,
    server_api_key=None,
    db_engine=None,
    db_schema=None,
    db_company_id=None,
    public_base_url=None
):
    global THEME, GCS_BUCKET_NAME, GCS_BASE_FOLDER, CLOUD_UPLOAD_ENABLED
    global DB_HOST, DB_PORT, DB_DATABASE, DB_USER, DB_PASSWORD, DB_TABLE, DB_CODE_COLUMN, DB_IMAGE_COLUMN, DB_API_ENDPOINT, DB_SYNC_MODE
    global DB_ENGINE, DB_SCHEMA, DB_COMPANY_ID, GCS_PUBLIC_BASE_URL
    global SERVER_ENABLED, SERVER_PORT, SERVER_API_KEY
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
    if db_code_column is not None:
        DB_CODE_COLUMN = db_code_column
    if db_image_column is not None:
        DB_IMAGE_COLUMN = db_image_column
    if db_api_endpoint is not None:
        DB_API_ENDPOINT = db_api_endpoint
    if db_sync_mode is not None:
        DB_SYNC_MODE = db_sync_mode
    if server_enabled is not None:
        SERVER_ENABLED = bool(server_enabled)
    if server_port is not None:
        SERVER_PORT = int(server_port)
    if server_api_key is not None:
        SERVER_API_KEY = server_api_key
    if db_engine is not None:
        DB_ENGINE = db_engine
    if db_schema is not None:
        DB_SCHEMA = db_schema or "public"
    if db_company_id is not None:
        DB_COMPANY_ID = str(db_company_id).strip()
    if public_base_url is not None:
        GCS_PUBLIC_BASE_URL = public_base_url.strip()

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
            "db_code_column": DB_CODE_COLUMN,
            "db_image_column": DB_IMAGE_COLUMN,
            "db_api_endpoint": DB_API_ENDPOINT,
            "db_sync_mode": DB_SYNC_MODE,
            "db_engine": DB_ENGINE,
            "db_schema": DB_SCHEMA,
            "db_company_id": DB_COMPANY_ID,
            "gcs_public_base_url": GCS_PUBLIC_BASE_URL,
            "server_enabled": SERVER_ENABLED,
            "server_port": SERVER_PORT,
            "server_api_key": SERVER_API_KEY,
            "server_installer_port": INSTALLER_PORT
        }
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Config save warning]: {e}")

# Cargar ajustes guardados al iniciar módulo
if app_paths.is_frozen():
    seed_settings_from_package()
load_settings()

# Generar la clave de la API en el primer arranque y registrar el puerto del instalador
if not SERVER_API_KEY:
    save_settings(server_api_key=secrets.token_urlsafe(24))
elif _installer_port_pending:
    save_settings()
