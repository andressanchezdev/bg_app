import os
from pathlib import Path
from PIL import Image
from PySide6.QtCore import QObject, QRunnable, Signal

from core.image_processor import export_to_webp
from core.bg_remover import process_remove_background
from services.cloud_storage import CloudStorageService
from services.database import DatabaseService


class WorkerSignals(QObject):
    started = Signal(str)
    progress = Signal(str, str)
    # emitir: (ruta_original, ruta_local_exportada, url_gcs)
    finished = Signal(str, str, str)
    error = Signal(str, str)


class ImageBatchWorker(QRunnable):
    def __init__(
        self,
        file_path: str,
        output_dir: str,
        session=None,
        quality: int = 85,
        remove_bg: bool = True,
        white_bg: bool = False,       # PRIORIDAD: Fondo transparente (sin relleno blanco)
        resize_config: dict = None,
        upload_to_cloud: bool = False,
        cloud_service: CloudStorageService = None,
        db_service: DatabaseService = None,
        batch_id: int = None
    ):
        super().__init__()
        self.file_path = file_path
        self.output_dir = output_dir
        self.session = session
        self.quality = quality
        self.remove_bg = remove_bg
        self.white_bg = white_bg
        self.resize_config = resize_config
        self.upload_to_cloud = upload_to_cloud
        self.cloud_service = cloud_service
        self.db_service = db_service
        self.batch_id = batch_id
        self.signals = WorkerSignals()

    def run(self):
        try:
            self.signals.started.emit(self.file_path)
            self.signals.progress.emit(self.file_path, "Cargando...")

            # Soporte HEIC/HEIF y formatos convencionales
            pil_img = Image.open(self.file_path).convert("RGBA")

            if self.remove_bg:
                self.signals.progress.emit(self.file_path, "Aislando objeto...")
                pil_img = process_remove_background(pil_img, session=self.session)

                # Si el usuario solicitara explícitamente fondo blanco
                if self.white_bg and pil_img.mode in ("RGBA", "LA"):
                    self.signals.progress.emit(self.file_path, "Rellenando fondo blanco...")
                    background = Image.new("RGB", pil_img.size, (255, 255, 255))
                    background.paste(pil_img, mask=pil_img.split()[3])
                    pil_img = background

            self.signals.progress.emit(self.file_path, "Optimizando WebP...")
            base_name = Path(self.file_path).stem  # Mismo nombre exacto sin la extensión vieja
            
            os.makedirs(self.output_dir, exist_ok=True)
            # Salida con el mismo nombre exacto pero extensión .webp
            output_webp_path = os.path.join(self.output_dir, f"{base_name}.webp")

            export_to_webp(
                pil_image=pil_img,
                output_path=output_webp_path,
                quality=self.quality,
                method=6,
                resize_config=self.resize_config
            )

            cloud_url = ""
            if self.upload_to_cloud and self.cloud_service:
                self.signals.progress.emit(self.file_path, "Subiendo a GCP...")
                destination_blob_name = os.path.basename(output_webp_path)
                
                res_url = self.cloud_service.upload_file(
                    output_webp_path, 
                    destination_blob_name=destination_blob_name,
                    make_public=True
                )
                if res_url:
                    cloud_url = res_url

            # Registrar éxito en base de datos local
            if self.db_service:
                try:
                    self.db_service.update_image_success(
                        original_path=self.file_path,
                        processed_path=output_webp_path,
                        cloud_url=cloud_url if cloud_url else None
                    )
                except Exception as e:
                    print(f"[DB Warning]: {e}")

            self.signals.finished.emit(self.file_path, output_webp_path, cloud_url)

        except Exception as e:
            err_str = str(e)
            if self.db_service:
                try:
                    self.db_service.update_image_error(self.file_path, err_str)
                except Exception:
                    pass
            self.signals.error.emit(self.file_path, err_str)
