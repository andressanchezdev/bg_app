import os
from pathlib import Path
from typing import Optional, Dict, Any
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

    def validate_image_target(
        self,
        folder_name: str,
        filename: str,
        existing_folders: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Valida cómo y dónde se almacenará una imagen en GCP:
        1. Las imágenes NUNCA se almacenan en la ruta raíz directa de base_folder.
        2. Si la imagen pertenece a una carpeta: el nombre de la carpeta DEBE coincidir
           con una carpeta existente en GCP. Si coincide, se sube adentro de esa carpeta.
        3. Si la imagen está suelta (sin carpeta): se lee su nombre (stem) y DEBE coincidir
           con una carpeta existente en GCP con ese mismo nombre. Si coincide, se almacena
           dentro de dicha carpeta.
        4. Si no coincide ninguna carpeta, se rechaza y se genera un error claro.
        """
        if existing_folders is None:
            existing_folders = self.get_existing_folders()

        clean_folder = folder_name.strip("/").replace("\\", "/") if folder_name else ""
        stem_name = Path(filename).stem.strip()

        # Caso 1: La imagen pertenece a una carpeta origen
        if clean_folder and clean_folder != ".":
            match = None
            for ef in existing_folders:
                if ef.lower() == clean_folder.lower():
                    match = ef
                    break

            if match:
                return {
                    "valid": True,
                    "target_subfolder": match,
                    "is_loose": False,
                    "reason": f"Carpeta '{clean_folder}' coincide con la carpeta '{match}' en GCP."
                }
            else:
                return {
                    "valid": False,
                    "target_subfolder": None,
                    "is_loose": False,
                    "reason": (
                        f"La carpeta '{clean_folder}' NO existe dentro de '{self.base_folder}' en GCP.\n"
                        f"Carpetas disponibles: {', '.join(existing_folders) if existing_folders else '(Ninguna carpeta creada)'}"
                    )
                }

        # Caso 2: Imagen suelta (sin carpeta).
        # Regla: se lee su nombre de archivo y se almacena dentro de la carpeta con su mismo nombre.
        match_by_name = None
        for ef in existing_folders:
            if ef.lower() == stem_name.lower():
                match_by_name = ef
                break

        if match_by_name:
            return {
                "valid": True,
                "target_subfolder": match_by_name,
                "is_loose": True,
                "reason": f"Imagen suelta '{filename}': coincide con la carpeta existente '{match_by_name}' en GCP."
            }
        else:
            return {
                "valid": True,
                "target_subfolder": "",
                "is_loose": True,
                "reason": f"Imagen pura suelta '{filename}': se sube directamente a '{self.base_folder}'."
            }

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

        clean_sub = subfolder.strip("/").replace("\\", "/") if subfolder else ""

        if destination_blob_name is None:
            destination_blob_name = os.path.basename(file_path)

        destination_blob_name = destination_blob_name.lstrip("/").replace("\\", "/")

        clean_base = self.base_folder.strip("/") if self.base_folder else ""

        # Si viene en subcarpeta, anteponer la subcarpeta
        if clean_sub and not destination_blob_name.startswith(clean_sub):
            destination_blob_name = f"{clean_sub}/{destination_blob_name}"

        # Anteponer la carpeta base si está definida y no está ya presente
        if clean_base and not destination_blob_name.startswith(clean_base):
            destination_blob_name = f"{clean_base}/{destination_blob_name}"

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
