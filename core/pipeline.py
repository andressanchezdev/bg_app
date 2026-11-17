"""
Pipeline de procesamiento sin interfaz gráfica, compartido por la GUI (lotes) y la API HTTP.

process_single_image(): una imagen -> quitar fondo -> WebP -> (opcional) subir a GCS.
BatchPipeline.run():    una carpeta completa, con la misma resolución de carpeta de producto
                        en GCS que usa el procesamiento por lotes de la ventana principal.
"""
import logging
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, Dict, List, Optional, Any

from PIL import Image, ImageOps

import config
from core.bg_remover import process_remove_background, get_ai_session
from core.image_processor import export_to_webp
from services.cloud_storage import CloudStorageService
from services.image_indexer import ImageIndexer

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

log = logging.getLogger(__name__)


@dataclass
class BatchOptions:
    quality: int = 90
    remove_bg: bool = True
    white_bg: bool = False
    resize_enabled: bool = True
    width: int = 900
    height: int = 900
    resize_mode: str = "contain"
    upload_gcs: bool = True
    register_db: bool = False

    @property
    def resize_config(self) -> Dict[str, Any]:
        return {
            "enabled": self.resize_enabled,
            "width": self.width,
            "height": self.height,
            "mode": self.resize_mode,
        }


@dataclass
class ImageResult:
    source_path: str
    relative_path: str = ""
    output_path: str = ""
    cloud_url: str = ""
    target_subfolder: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["ok"] = self.ok
        return d


ProgressCallback = Callable[[str, str], None]


def process_single_image(
    file_path: str,
    output_dir: str,
    options: BatchOptions,
    session=None,
    cloud_service: Optional[CloudStorageService] = None,
    target_subfolder: str = "",
    progress: Optional[ProgressCallback] = None,
) -> ImageResult:
    """Procesa una imagen. Lanza excepción si falla el procesamiento local."""
    notify = progress or (lambda _p, _m: None)
    result = ImageResult(source_path=file_path, target_subfolder=target_subfolder)

    notify(file_path, "Cargando...")
    with Image.open(file_path) as raw_img:
        pil_img = ImageOps.exif_transpose(raw_img).convert("RGBA")

    if options.remove_bg:
        notify(file_path, "Aislando objeto (Fase 1 y 2)...")
        pil_img = process_remove_background(pil_img, session=session)

    notify(file_path, "Renderizando y optimizando WebP...")
    os.makedirs(output_dir, exist_ok=True)
    output_webp_path = os.path.join(output_dir, f"{Path(file_path).stem}.webp")
    export_to_webp(
        pil_image=pil_img,
        output_path=output_webp_path,
        quality=options.quality,
        method=6,
        resize_config=options.resize_config,
        white_bg=options.white_bg,
    )
    result.output_path = output_webp_path

    if cloud_service is not None:
        notify(file_path, "Subiendo a GCP...")
        url = cloud_service.upload_file(
            output_webp_path,
            destination_blob_name=os.path.basename(output_webp_path),
            subfolder=target_subfolder,
            make_public=True,
        )
        if url:
            result.cloud_url = url
        else:
            result.error = "Procesada localmente, pero falló la subida a GCP."
    return result


def build_cloud_service() -> Optional[CloudStorageService]:
    """Crea el servicio de GCS con la configuración actual, o None si no hay credenciales."""
    key_path = config.resolve_credentials_path()
    bucket = getattr(config, "GCS_BUCKET_NAME", "")
    if not key_path or not os.path.exists(key_path) or not bucket:
        return None
    return CloudStorageService(
        bucket_name=bucket,
        credentials_path=key_path,
        base_folder=getattr(config, "GCS_BASE_FOLDER", ""),
    )


class BatchPipeline:
    """Procesa una carpeta completa de forma secuencial (la inferencia ya es exclusiva)."""

    def __init__(self, options: BatchOptions, session=None):
        self.options = options
        self.session = session if session is not None else get_ai_session()
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def run(
        self,
        input_folder: str,
        output_dir: str,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict[str, Any]:
        notify = on_progress or (lambda _d, _t, _m: None)
        records = ImageIndexer.scan_folder(input_folder)
        total = len(records)
        warnings: List[str] = []
        if total == 0:
            return {"total": 0, "results": [], "warnings": ["No se encontraron imágenes válidas."], "db": None}

        cloud_service, existing_folders = None, []
        if self.options.upload_gcs:
            cloud_service = build_cloud_service()
            if cloud_service is None:
                warnings.append("No se encontraron credenciales de GCP: se procesó solo localmente.")
            else:
                conn = cloud_service.test_connection()
                if conn.get("ok"):
                    existing_folders = cloud_service.get_existing_folders()
                else:
                    warnings.append(f"Sin conexión a GCP: {conn.get('message', '')}")
                    cloud_service = None

        results: List[ImageResult] = []
        for idx, rec in enumerate(records, 1):
            if self.cancelled:
                warnings.append("Trabajo cancelado.")
                break
            fpath, fname = rec["absolute_path"], rec.get("filename", "")
            notify(idx - 1, total, f"Procesando {fname}")

            target_subfolder = ""
            if cloud_service is not None:
                val = cloud_service.resolve_product_folder(
                    filename=fname,
                    existing_folders=existing_folders,
                    folder_candidate=rec.get("folder_name", ""),
                )
                target_subfolder = val["target_subfolder"]

            # Conservar la estructura de carpetas para que nombres repetidos no se sobrescriban
            item_out_dir = os.path.join(output_dir, *Path(rec.get("folder_name", "")).parts)
            try:
                res = process_single_image(
                    fpath, item_out_dir, self.options,
                    session=self.session,
                    cloud_service=cloud_service,
                    target_subfolder=target_subfolder,
                )
            except Exception as e:
                log.exception("Error procesando %s", fpath)
                res = ImageResult(source_path=fpath, target_subfolder=target_subfolder, error=str(e))
            res.relative_path = rec.get("relative_path", "")
            results.append(res)

            rec.update({
                "processed": not res.error or bool(res.output_path),
                "processed_path": res.output_path or None,
                "cloud_url": res.cloud_url or None,
                "folder_name": target_subfolder or rec.get("folder_name", ""),
            })

        notify(len(results), total, "Finalizado")
        ImageIndexer.save_to_json(records, os.path.join(output_dir, "image_map.json"))

        db_report = None
        if self.options.register_db and any(r.cloud_url for r in results):
            try:
                from services.db_service import post_image_records
                db_report = post_image_records([r for r in records if r.get("cloud_url")])
            except Exception as e:
                db_report = {"ok": False, "message": str(e)}

        return {
            "total": total,
            "results": [r.to_dict() for r in results],
            "warnings": warnings,
            "db": db_report,
        }
