import os
from pathlib import Path
from PIL import Image, ImageOps
from PySide6.QtCore import QObject, QRunnable, Signal

from core.image_processor import export_to_webp
from core.bg_remover import process_remove_background
from services.cloud_storage import CloudStorageService


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
        white_bg: bool = False,
        resize_config: dict = None,
        upload_to_cloud: bool = False,
        cloud_service: CloudStorageService = None,
        target_subfolder: str = ""
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
        self.target_subfolder = target_subfolder
        self.signals = WorkerSignals()

    def run(self):
        try:
            self.signals.started.emit(self.file_path)
            self.signals.progress.emit(self.file_path, "Cargando...")

            raw_img = Image.open(self.file_path)
            pil_img = ImageOps.exif_transpose(raw_img).convert("RGBA")

            if self.remove_bg:
                self.signals.progress.emit(self.file_path, "Aislando objeto (Fase 1 y 2)...")
                pil_img = process_remove_background(pil_img, session=self.session)

            self.signals.progress.emit(self.file_path, "Renderizando y optimizando WebP...")
            base_name = Path(self.file_path).stem
            
            os.makedirs(self.output_dir, exist_ok=True)
            output_webp_path = os.path.join(self.output_dir, f"{base_name}.webp")

            export_to_webp(
                pil_image=pil_img,
                output_path=output_webp_path,
                quality=self.quality,
                method=6,
                resize_config=self.resize_config,
                white_bg=self.white_bg
            )

            cloud_url = ""
            if self.upload_to_cloud and self.cloud_service:
                self.signals.progress.emit(self.file_path, "Subiendo a GCP...")
                destination_blob_name = os.path.basename(output_webp_path)
                
                res_url = self.cloud_service.upload_file(
                    output_webp_path, 
                    destination_blob_name=destination_blob_name,
                    subfolder=self.target_subfolder,
                    make_public=True
                )
                if res_url:
                    cloud_url = res_url

            self.signals.finished.emit(self.file_path, output_webp_path, cloud_url)

        except Exception as e:
            err_str = str(e)
            self.signals.error.emit(self.file_path, err_str)
