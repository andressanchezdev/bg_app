import os
import re
from pathlib import Path
from typing import Optional, Dict, Any, List
from google.cloud import storage
from google.api_core import exceptions as gcp_exceptions
from google.auth.exceptions import GoogleAuthError


def format_gcp_error(err: Exception, bucket_name: str = "") -> str:
    """
    Traduce errores técnicos de Google Cloud a explicaciones claras,
    organizadas y comprensibles para el usuario final (sin jerga técnica ni stack traces).
    """
    err_str = str(err).lower()

    if isinstance(err, gcp_exceptions.NotFound) or "404" in err_str or "not found" in err_str:
        return (
            f"El bucket '{bucket_name}' no existe en Google Cloud.\n\n"
            "Solución: Verifica en la consola de Google Cloud que el nombre del bucket "
            "esté escrito exactamente igual (distingue mayúsculas y minúsculas)."
        )

    if isinstance(err, gcp_exceptions.Forbidden) or "403" in err_str or "access denied" in err_str or "permission" in err_str:
        return (
            f"Permiso denegado al acceder al bucket '{bucket_name}'.\n\n"
            "Solución: En Google Cloud Console, ve a IAM y asegúrate de que tu Cuenta de Servicio "
            "tenga asignado el rol 'Storage Object Admin' sobre este bucket."
        )

    if isinstance(err, gcp_exceptions.Unauthorized) or "401" in err_str or "invalid credentials" in err_str:
        return (
            "Las credenciales del archivo JSON no son válidas o han sido revocadas.\n\n"
            "Solución: Genera una nueva clave JSON para tu Cuenta de Servicio en Google Cloud Console "
            "e impórtala nuevamente en la aplicación."
        )

    if isinstance(err, GoogleAuthError) or "private_key" in err_str or "jwt" in err_str:
        return (
            "El archivo de credenciales JSON está incompleto o dañado.\n\n"
            "Solución: Descarga nuevamente el archivo JSON original de la Cuenta de Servicio de Google Cloud."
        )

    if "name resolution" in err_str or "failed to resolve" in err_str or "connection" in err_str or "getaddrinfo" in err_str:
        return (
            "No se pudo establecer conexión con los servidores de Google Cloud.\n\n"
            "Solución: Comprueba tu conexión a internet o verifica si tu red tiene un firewall que bloquee storage.googleapis.com."
        )

    # Mensaje amigable general
    return (
        f"No se pudo completar la operación con el servidor de Google Cloud.\n\n"
        f"Detalle: {str(err)}"
    )


class CloudStorageService:
    """
    Servicio para subir y gestionar archivos en Google Cloud Storage (GCS).
    """

    def __init__(
        self,
        bucket_name: Optional[str] = None,
        credentials_path: Optional[str] = None,
        base_folder: Optional[str] = None
    ):
        self.credentials_path = credentials_path or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if self.credentials_path and os.path.exists(self.credentials_path):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.credentials_path

        self.bucket_name = bucket_name or os.getenv("GCS_BUCKET_NAME")
        self.base_folder = base_folder.strip("/") if base_folder else ""
        self._client = None
        self._cached_folders = None

    @property
    def client(self) -> storage.Client:
        """Inicialización perezosa (Lazy Initialization) del cliente de GCS."""
        if self._client is None:
            if self.credentials_path and os.path.exists(self.credentials_path):
                self._client = storage.Client.from_service_account_json(self.credentials_path)
            else:
                self._client = storage.Client()
        return self._client

    def test_connection(self) -> Dict[str, Any]:
        """
        Verifica si las credenciales y el bucket configurado son válidos y accesibles,
        devolviendo explicaciones claras y organizadas para el usuario final.
        """
        if not self.credentials_path or not os.path.exists(self.credentials_path):
            return {
                "ok": False,
                "error_type": "credentials_missing",
                "message": (
                    "No se ha encontrado el archivo de credenciales de Google Cloud.\n\n"
                    "Solución: Haz clic en 'Importar clave JSON...' y selecciona el archivo "
                    "descargado desde tu consola de Google Cloud."
                )
            }

        if not self.bucket_name or not self.bucket_name.strip():
            return {
                "ok": False,
                "error_type": "bucket_missing",
                "message": (
                    "No has especificado el nombre del Bucket.\n\n"
                    "Solución: Escribe el nombre del bucket que creaste en Google Cloud Storage."
                )
            }

        try:
            # Intentar obtener metadata del bucket
            bucket = self.client.get_bucket(self.bucket_name)
            location = getattr(bucket, "location", "Nube")
            return {
                "ok": True,
                "bucket_name": self.bucket_name,
                "location": location,
                "message": (
                    f"Conexión exitosa con Google Cloud Storage.\n\n"
                    f"• Bucket activo: {self.bucket_name}\n"
                    f"• Región/Ubicación: {location}\n"
                    f"• Estado: Listo para subir imágenes"
                )
            }
        except Exception as e:
            human_msg = format_gcp_error(e, self.bucket_name)
            return {
                "ok": False,
                "error_type": "api_error",
                "message": human_msg
            }

    def get_existing_folders(self, force_refresh: bool = False) -> List[str]:
        """
        Consulta en Google Cloud Storage y retorna los nombres de las carpetas/prefijos
        existentes bajo self.base_folder (ej: si existe 'dependencias/img/productos/calzado/', retorna 'calzado').
        Usa la API oficial de GCP con delimiter='/' y captura tanto prefijos virtuales como marcadores de directorio.
        Utiliza caché en memoria para evitar llamadas redundantes de red.
        """
        if not force_refresh and self._cached_folders is not None:
            return self._cached_folders

        if not self.bucket_name:
            return []
        try:
            bucket = self.client.bucket(self.bucket_name)
            prefix = self.base_folder.strip("/")
            if prefix:
                prefix += "/"

            blobs = bucket.list_blobs(prefix=prefix, delimiter="/")
            folders = set()

            # Consumir iterador para poblar tanto prefixes como blobs de directorio
            for b in blobs:
                if b.name.endswith("/"):
                    sub = b.name[len(prefix):].strip("/")
                    if sub:
                        folders.add(sub)

            for p in blobs.prefixes:
                sub = p[len(prefix):].strip("/")
                if sub:
                    folders.add(sub)

            self._cached_folders = sorted(list(folders))
            return self._cached_folders
        except Exception as e:
            print(f"[GCS get_existing_folders Warning]: {e}")
            return []

    def resolve_product_folder(
        self,
        filename: str,
        existing_folders: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Determina la subcarpeta de producto en GCP basándose EXCLUSIVAMENTE en el nombre de la imagen:
        1. No valida ni depende del nombre del directorio local.
        2. Busca coincidencia exacta con una carpeta existente en GCP.
        3. Busca coincidencia de prefijo con carpetas en GCP (ej: '01100610-5-PASTILLAS' -> '01100610-5').
        4. Busca coincidencia separando por delimitadores ('-', '_', ' ').
        5. Si la carpeta no existe, infiere el código del nombre y lo usa como prefijo
           al subir la imagen; GCS representa la carpeta a partir del objeto subido.
        """
        if existing_folders is None:
            existing_folders = self.get_existing_folders()

        stem = Path(filename).stem.strip()
        folder_dict = {ef.lower(): ef for ef in existing_folders}

        # 1. Coincidencia exacta con carpeta en GCP
        if stem.lower() in folder_dict:
            target = folder_dict[stem.lower()]
            return {
                "valid": True,
                "target_subfolder": target,
                "created_new": False,
                "reason": f"Coincidencia exacta con carpeta existente '{target}' en GCP."
            }

        # 2. Coincidencia de prefijo con carpetas en GCP (ordenando de más larga a más corta)
        for ef_lower, ef_original in sorted(folder_dict.items(), key=lambda x: len(x[0]), reverse=True):
            if stem.lower().startswith(ef_lower):
                remainder = stem[len(ef_lower):]
                if not remainder or remainder[0] in ('-', '_', ' ', '.'):
                    return {
                        "valid": True,
                        "target_subfolder": ef_original,
                        "created_new": False,
                        "reason": f"Prefijo de imagen coincide con carpeta existente '{ef_original}' en GCP."
                    }

        # 3. Delimitadores comunes ('-', '_', ' ')
        for sep in ('-', '_', ' '):
            if sep in stem:
                part = stem.split(sep)[0].strip()
                if part.lower() in folder_dict:
                    target = folder_dict[part.lower()]
                    return {
                        "valid": True,
                        "target_subfolder": target,
                        "created_new": False,
                        "reason": f"Código extraído '{part}' coincide con carpeta existente '{target}' en GCP."
                    }

        # Preserve numeric code segments, such as 01100610-5, before a descriptive suffix.
        code_match = re.match(r"^([A-Za-z0-9]+(?:[-_ ]\d+)*)(?:[-_ ]|$)", stem)
        if code_match:
            new_code = code_match.group(1).strip()
        else:
            new_code = re.split(r"[-_ ]", stem, maxsplit=1)[0].strip()
        clean_code = "".join(c for c in new_code if c.isalnum() or c in ('-', '_', '.')).strip() or stem

        # Keep the inferred prefix for subsequent images in this batch.
        if clean_code not in existing_folders:
            existing_folders.append(clean_code)

        return {
            "valid": True,
            "target_subfolder": clean_code,
            "created_new": True,
            "reason": (
                f"Se usará '{clean_code}' como prefijo GCP; la carpeta aparecerá "
                "al subir la imagen."
            )
        }

    def validate_image_target(
        self,
        folder_name: str,
        filename: str,
        existing_folders: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Resuelve la carpeta en GCP basándose en el nombre de la imagen / código,
        creándola automáticamente si aún no existe.
        """
        return self.resolve_product_folder(filename, existing_folders=existing_folders)

    def upload_file(
        self,
        file_path: str,
        destination_blob_name: Optional[str] = None,
        subfolder: Optional[str] = None,
        make_public: bool = True
    ) -> Optional[str]:
        """
        Sube un archivo local a un Bucket de Google Cloud Storage.
        EXIGE que subfolder esté especificado (no se permite guardar en la ruta raíz directa).
        """
        if not self.bucket_name:
            raise ValueError("No se configuró el nombre del bucket de Google Cloud.")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"El archivo local no existe: {file_path}")

        if destination_blob_name is None:
            destination_blob_name = os.path.basename(file_path)

        # Only the image filename is uploaded; local or supplied parent folders are ignored.
        image_name = destination_blob_name.replace("\\", "/").rsplit("/", 1)[-1]
        clean_sub = subfolder.strip("/\\").replace("\\", "/") if subfolder else ""
        clean_base = self.base_folder.strip("/\\").replace("\\", "/") if self.base_folder else ""
        destination_blob_name = "/".join(
            part for part in (clean_base, clean_sub, image_name) if part
        )

        try:
            bucket = self.client.bucket(self.bucket_name)
            blob = bucket.blob(destination_blob_name)

            content_type = "image/webp" if file_path.lower().endswith(".webp") else None
            blob.upload_from_filename(file_path, content_type=content_type)

            if make_public:
                try:
                    blob.make_public()
                    return blob.public_url
                except Exception:
                    pass

            return f"https://storage.googleapis.com/{self.bucket_name}/{destination_blob_name}"

        except Exception as e:
            human_error = format_gcp_error(e, self.bucket_name)
            print(f"[GCS Upload Error]:\n{human_error}")
            return None
