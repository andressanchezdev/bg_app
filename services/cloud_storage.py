import os
from typing import Optional
from google.cloud import storage
from google.api_core.exceptions import GoogleAPIError


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
        """
        :param bucket_name: Nombre del bucket en GCS. Si no se especifica, 
                            se busca en la variable de entorno 'GCS_BUCKET_NAME'.
        :param credentials_path: Ruta al archivo JSON de credenciales de la cuenta de servicio.
                                 Si no se especifica, busca 'GOOGLE_APPLICATION_CREDENTIALS'.
        :param base_folder: Carpeta o prefijo base opcional dentro del bucket (ej: "procesados/").
        """
        if credentials_path:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

        self.bucket_name = bucket_name or os.getenv("GCS_BUCKET_NAME")
        
        # Limpiar barras diagonales sobrantes para asegurar un formato consistente
        self.base_folder = base_folder.strip("/") if base_folder else ""
        self._client = None

    @property
    def client(self) -> storage.Client:
        """Inicialización perezosa (Lazy Initialization) del cliente de GCS."""
        if self._client is None:
            self._client = storage.Client()
        return self._client

    def upload_file(
        self,
        file_path: str,
        destination_blob_name: Optional[str] = None,
        make_public: bool = False
    ) -> Optional[str]:
        """
        Sube un archivo local a un Bucket de Google Cloud Storage respetando la ruta base.

        :param file_path: Ruta del archivo local a subir.
        :param destination_blob_name: Nombre que tendrá el archivo dentro del bucket (ej: "carpeta/imagen.webp").
                                      Si es None, usará el nombre base del archivo.
        :param make_public: Si se marca True, intentará hacer público el objeto.
        :return: URL pública o estándar de GCS del archivo subido, o None si falla.
        """
        if not self.bucket_name:
            raise ValueError(
                "No se configuró 'bucket_name'. Pásalo al instanciar "
                "CloudStorageService o define la variable de entorno GCS_BUCKET_NAME."
            )

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"El archivo local no existe: {file_path}")

        if destination_blob_name is None:
            destination_blob_name = os.path.basename(file_path)

        # Limpiar cualquier barra diagonal inicial en el destination_blob_name para evitar dobles slashes
        destination_blob_name = destination_blob_name.lstrip("/")

        # Anteponer la carpeta base si está configurada
        if self.base_folder:
            destination_blob_name = f"{self.base_folder}/{destination_blob_name}"

        try:
            bucket = self.client.bucket(self.bucket_name)
            blob = bucket.blob(destination_blob_name)

            # Subir el archivo asignando Content-Type adecuado para imágenes WebP
            content_type = "image/webp" if file_path.lower().endswith(".webp") else None
            blob.upload_from_filename(file_path, content_type=content_type)

            if make_public:
                try:
                    blob.make_public()
                    return blob.public_url
                except Exception as e:
                    print(f"[Aviso GCS]: No se pudo hacer público el objeto (puede deberse a políticas del bucket): {e}")

            # Retorna la URL estándar de Google Cloud Storage
            return f"https://storage.googleapis.com/{self.bucket_name}/{destination_blob_name}"

        except GoogleAPIError as e:
            print(f"[GCS Error]: Error al subir el archivo {file_path}: {e}")
            return None
        except Exception as e:
            print(f"[Error Inesperado GCS]: {e}")
            return None