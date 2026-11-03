import os
from pathlib import Path

# Ruta base del proyecto
BASE_DIR = Path(__file__).resolve().parent

# ==============================================================================
# CONFIGURACIÓN DE REDIMENSIONAMIENTO Y CALIDAD DE SALIDA
# ==============================================================================
DEFAULT_RESIZE_ENABLED = False     # Redimensionar por defecto
DEFAULT_OUTPUT_WIDTH = 900        # Ancho estándar
DEFAULT_OUTPUT_HEIGHT = 900       # Alto estándar
# Modos de escalado disponibles: 'contain' (mantiene relación de aspecto con lienzo),
# 'cover' (recorta para llenar), 'stretch' (deforma)
DEFAULT_RESIZE_MODE = "contain"

DEFAULT_WEBP_QUALITY = 85
DEFAULT_AI_MODEL = "u2net"

# ==============================================================================
# APARIENCIA E INTERFAZ
# ==============================================================================
THEME = "dark"  # Opciones: "dark" / "light"

# ==============================================================================
# INTEGRACIÓN CON GOOGLE CLOUD STORAGE (GCP)
# ==============================================================================
CLOUD_UPLOAD_ENABLED = False

# Nombre del Bucket de GCP (se usa GCS_BUCKET_NAME para coincidir con la librería)
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "importadorapremiumonline")
GCS_BASE_FOLDER = os.getenv("GCS_BASE_FOLDER", "dependencias/img/productos/")

# Ruta relativa y absoluta del archivo de credenciales de GCP
GCP_KEY_PATH = "credentials/gcp_key.json"
GCS_CREDENTIALS_PATH = os.getenv(
    "GOOGLE_APPLICATION_CREDENTIALS",
    str(BASE_DIR / GCP_KEY_PATH)
)

# Forzar la variable de entorno para que el SDK de Google la detecte siempre
if os.path.exists(GCS_CREDENTIALS_PATH):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = GCS_CREDENTIALS_PATH

# Indicar si los archivos subidos al bucket se hacen públicos por defecto
GCS_MAKE_PUBLIC = True