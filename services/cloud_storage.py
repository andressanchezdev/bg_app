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
        self._cached_subfolder_files = {}  # {subfolder: set(filenames)}

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

    def get_files_in_subfolder(self, subfolder: str, force_refresh: bool = False) -> Set[str]:
        """
        Consulta y retorna el conjunto de nombres de archivos existentes dentro
        de una subcarpeta de GCP (ej: 'dependencias/img/productos/{subfolder}/').
        Usa caché en memoria para evitar llamadas de red redundantes.
        """
        clean_sub = subfolder.strip("/\\").replace("\\", "/")
        if not force_refresh and clean_sub in self._cached_subfolder_files:
            return self._cached_subfolder_files[clean_sub]

        if not self.bucket_name:
            return set()

        try:
            bucket = self.client.bucket(self.bucket_name)
            clean_base = self.base_folder.strip("/\\").replace("\\", "/")
            prefix = f"{clean_base}/{clean_sub}/" if clean_base else f"{clean_sub}/"
            prefix = prefix.lstrip("/")

            blobs = bucket.list_blobs(prefix=prefix, delimiter="/")
            file_names = set()
            for b in blobs:
                # Extraer sólo el nombre del archivo dentro de esa subcarpeta
                fname = b.name[len(prefix):].strip("/")
                if fname and not fname.endswith("/"):
                    file_names.add(fname)

            self._cached_subfolder_files[clean_sub] = file_names
            return file_names
        except Exception as e:
            print(f"[GCS get_files_in_subfolder Warning for {subfolder}]: {e}")
            if clean_sub not in self._cached_subfolder_files:
                self._cached_subfolder_files[clean_sub] = set()
            return self._cached_subfolder_files[clean_sub]

    def resolve_non_colliding_name(self, subfolder: str, target_filename: str) -> str:
        """
        Si el nombre de archivo ya existe dentro de la subcarpeta en GCP,
        le asigna un consecutivo automático (ej: '01100610-5.webp' -> '01100610-5-2.webp')
        para NUNCA sobreescribir imágenes existentes.
        """
        clean_sub = subfolder.strip("/\\").replace("\\", "/")
        existing_files = self.get_files_in_subfolder(clean_sub)

        # Normalizar extension a webp si aplica
        stem = Path(target_filename).stem
        ext = Path(target_filename).suffix.lower()
        if not ext:
            ext = ".webp"

        candidate = f"{stem}{ext}"
        existing_lower = {f.lower() for f in existing_files}

        if candidate.lower() not in existing_lower:
            existing_files.add(candidate)
            return candidate

        # Extraer base sin sufijo numérico previo si existiera
        # Ej: '01100610-5-2' -> base_stem='01100610-5', o '01100610-5' -> base_stem='01100610-5'
        # Buscar el mayor consecutivo existente
        pattern = re.compile(rf"^{re.escape(stem)}[-_](\d+)\{ext}$", re.IGNORECASE)
        max_idx = 1

        for ef in existing_files:
            m = pattern.match(ef)
            if m:
                try:
                    idx = int(m.group(1))
                    if idx >= max_idx:
                        max_idx = idx + 1
                except ValueError:
                    pass
            elif ef.lower() == candidate.lower():
                if max_idx <= 1:
                    max_idx = 2

        new_name = f"{stem}-{max_idx}{ext}"
        while new_name.lower() in existing_lower:
            max_idx += 1
            new_name = f"{stem}-{max_idx}{ext}"

        existing_files.add(new_name)
        return new_name

    def resolve_product_folder(
        self,
        filename: str,
        existing_folders: Optional[List[str]] = None,
        folder_candidate: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Determina de forma inteligente la subcarpeta de producto en GCP:
        1. Evalúa si la carpeta contenedora inmediata (ej: 'productos/01100610-5' -> '01100610-5')
           coincide con una carpeta existente en GCP. Si es así, agrupa el contenido dentro de ella.
        2. Evalúa si el nombre de la imagen coincide de forma exacta, por prefijo o delimitador con GCP.
        3. Si la carpeta contenedora no es genérica (ej: no es 'productos', 'fotos', 'descargas'),
           la toma como el código del producto para crearla en GCP si aún no existe.
        4. Si es una imagen suelta, extrae el código del propio nombre de archivo.
        """
        if existing_folders is None:
            existing_folders = self.get_existing_folders()

        stem = Path(filename).stem.strip()
        folder_dict = {ef.lower(): ef for ef in existing_folders}

        # Conjunto de nombres de carpetas genéricas locales que NO deben ser tomadas como códigos de producto
        GENERIC_CONTAINERS = {
            "productos", "producto", "imagenes", "fotos", "descargas", "downloads",
            "desktop", "escritorio", "nuevo", "lote", "lotes", "batch", "processed",
            "output", "temp", "tmp", "galeria", "variantes", "angulos", "tomas", "subcarpetas", "hd", "web"
        }

        # -----------------------------------------------------------------
        # 1. VALIDACIÓN POR JERARQUÍA COMPLETA DE CARPETAS (SOPORTE MULTINIVEL)
        # -----------------------------------------------------------------
        # Si la imagen viene dentro de 'productos/01100610-5/galeria/angulos/' o '01100610-5/sub1/'
        # analiza todos los segmentos del árbol para encontrar el código del producto
        if folder_candidate:
            clean_cand = folder_candidate.strip("/\\").replace("\\", "/")
            segments = [s.strip() for s in clean_cand.split("/") if s.strip()]

            # 1.A. ¿Alguno de los directorios de la ruta coincide con una carpeta existente en GCP?
            for seg in segments:
                if seg.lower() in folder_dict:
                    target = folder_dict[seg.lower()]
                    return {
                        "valid": True,
                        "target_subfolder": target,
                        "created_new": False,
                        "reason": f"El directorio '{seg}' en la ruta coincide con la carpeta existente '{target}' en GCP."
                    }

                # Buscar por delimitadores en cada segmento del directorio
                for sep in ('-', '_', ' '):
                    if sep in seg:
                        part = seg.split(sep)[0].strip()
                        if part.lower() in folder_dict:
                            target = folder_dict[part.lower()]
                            return {
                                "valid": True,
                                "target_subfolder": target,
                                "created_new": False,
                                "reason": f"Código extraído del directorio '{part}' coincide con carpeta en GCP."
                            }

            # 1.B. Si no coincide con GCP, buscar el primer segmento del árbol que represente un código de producto nuevo
            for seg in segments:
                if seg.lower() not in GENERIC_CONTAINERS and len(seg) > 1:
                    clean_code = "".join(c for c in seg if c.isalnum() or c in ('-', '_', '.')).strip()
                    if clean_code:
                        if clean_code not in existing_folders:
                            existing_folders.append(clean_code)
                        return {
                            "valid": True,
                            "target_subfolder": clean_code,
                            "created_new": True,
                            "reason": f"Subdirectorio '{clean_code}' detectado como código de producto para agrupar las imágenes en GCP."
                        }

        # -----------------------------------------------------------------
        # 2. VALIDACIÓN POR NOMBRE DE ARCHIVO
        # -----------------------------------------------------------------
        # 2.A. Coincidencia exacta con el nombre del archivo
        if stem.lower() in folder_dict:
            target = folder_dict[stem.lower()]
            return {
                "valid": True,
                "target_subfolder": target,
                "created_new": False,
                "reason": f"Coincidencia exacta de archivo con carpeta existente '{target}' en GCP."
            }

        # 2.B. Coincidencia de prefijo con carpetas en GCP
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

        # 2.C. Delimitadores comunes en el archivo ('-', '_', ' ')
        for sep in ('-', '_', ' '):
            if sep in stem:
                part = stem.split(sep)[0].strip()
                if part.lower() in folder_dict:
                    target = folder_dict[part.lower()]
                    return {
                        "valid": True,
                        "target_subfolder": target,
                        "created_new": False,
                        "reason": f"Código extraído del archivo '{part}' coincide con carpeta existente '{target}' en GCP."
                    }

        # -----------------------------------------------------------------
        # 3. CREACIÓN DE NUEVA CARPETA EN GCP (Si no existía previamente)
        # -----------------------------------------------------------------
        # Prioridad 3.A: Si la carpeta contenedora no es genérica, ella es el código del producto
        if folder_candidate:
            clean_cand = folder_candidate.strip("/\\").replace("\\", "/")
            leaf_folder = clean_cand.split("/")[-1].strip()
            if leaf_folder.lower() not in GENERIC_CONTAINERS and len(leaf_folder) > 1:
                clean_code = "".join(c for c in leaf_folder if c.isalnum() or c in ('-', '_', '.')).strip()
                if clean_code:
                    if clean_code not in existing_folders:
                        existing_folders.append(clean_code)
                    return {
                        "valid": True,
                        "target_subfolder": clean_code,
                        "created_new": True,
                        "reason": f"Carpeta contenedora '{clean_code}' será creada en GCP para agrupar estas imágenes."
                    }

        # Prioridad 3.B: Si es un archivo suelto, extrae el código de su nombre
        code_match = re.match(r"^([A-Za-z0-9]+(?:[-_ ]\d+)*)(?:[-_ ]|$)", stem)
        if code_match:
            new_code = code_match.group(1).strip()
        else:
            new_code = re.split(r"[-_ ]", stem, maxsplit=1)[0].strip()
        clean_code = "".join(c for c in new_code if c.isalnum() or c in ('-', '_', '.')).strip() or stem

        if clean_code not in existing_folders:
            existing_folders.append(clean_code)

        return {
            "valid": True,
            "target_subfolder": clean_code,
            "created_new": True,
            "reason": f"Se creará la carpeta '{clean_code}' en GCP a partir del código de la imagen."
        }

    def validate_image_target(
        self,
        folder_name: str,
        filename: str,
        existing_folders: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Resuelve la carpeta en GCP evaluando tanto la carpeta contenedora como el nombre de archivo.
        """
        return self.resolve_product_folder(
            filename=filename,
            existing_folders=existing_folders,
            folder_candidate=folder_name
        )

    def upload_file(
        self,
        file_path: str,
        destination_blob_name: Optional[str] = None,
        subfolder: Optional[str] = None,
        make_public: bool = True,
        avoid_overwrite: bool = True
    ) -> Optional[str]:
        """
        Sube un archivo local a un Bucket de Google Cloud Storage.
        Si avoid_overwrite=True, verifica los archivos existentes en la subcarpeta
        y le asigna un consecutivo automático si el nombre ya existe.
        """
        if not self.bucket_name:
            raise ValueError("No se configuró el nombre del bucket de Google Cloud.")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"El archivo local no existe: {file_path}")

        if destination_blob_name is None:
            destination_blob_name = os.path.basename(file_path)

        # Only the image filename is uploaded; local or supplied parent folders are ignored.
        raw_name = destination_blob_name.replace("\\", "/").rsplit("/", 1)[-1]
        clean_sub = subfolder.strip("/\\").replace("\\", "/") if subfolder else ""

        # Si se debe evitar sobreescribir, resolver consecutivo
        if avoid_overwrite and clean_sub:
            image_name = self.resolve_non_colliding_name(clean_sub, raw_name)
        else:
            image_name = raw_name

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
