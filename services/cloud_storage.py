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

    @property
    def client(self) -> storage.Client:
        """Inicialización perezosa (Lazy Initialization) del cliente de GCS."""
        if self._client is None:
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

    def upload_file(
        self,
        file_path: str,
        destination_blob_name: Optional[str] = None,
        make_public: bool = True
    ) -> Optional[str]:
        """
        Sube un archivo local a un Bucket de Google Cloud Storage respetando la ruta base.
        """
        if not self.bucket_name:
            raise ValueError("No se configuró el nombre del bucket de Google Cloud.")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"El archivo local no existe: {file_path}")

        if destination_blob_name is None:
            destination_blob_name = os.path.basename(file_path)

        destination_blob_name = destination_blob_name.lstrip("/").replace("\\", "/")

        if self.base_folder:
            destination_blob_name = f"{self.base_folder}/{destination_blob_name}"

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
                    # Si el bucket tiene Uniform Bucket-Level Access, blob.make_public() lanza excepción leve
                    pass

            return f"https://storage.googleapis.com/{self.bucket_name}/{destination_blob_name}"

        except Exception as e:
            human_error = format_gcp_error(e, self.bucket_name)
            print(f"[GCS Upload Error]:\n{human_error}")
            return None
