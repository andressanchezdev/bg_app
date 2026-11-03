import os
from PIL import Image
from rembg import remove
from PySide6.QtCore import QObject, QRunnable, Signal

from core.image_processor import export_to_webp
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
        session,
        quality: int = 85,
        remove_bg: bool = True,
        white_bg: bool = True,
        resize_config: dict = None,   # {'enabled': True, 'width': X, 'height': Y, 'mode': '...'}
        upload_to_cloud: bool = False,
        cloud_service: CloudStorageService = None
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
        self.signals = WorkerSignals()

    def run(self):
        try:
            self.signals.started.emit(self.file_path)

            self.signals.progress.emit(self.file_path, "Cargando...")
            pil_img = Image.open(self.file_path).convert("RGBA")

            if self.remove_bg:
                self.signals.progress.emit(self.file_path, "Procesando IA...")
                pil_img = remove(pil_img, session=self.session)

                # Aplicar fondo blanco si está habilitado y la imagen tiene canal alfa (transparencia)
                if self.white_bg and pil_img.mode in ("RGBA", "LA"):
                    self.signals.progress.emit(self.file_path, "Aplicando fondo blanco...")
                    background = Image.new("RGB", pil_img.size, (255, 255, 255))
                    background.paste(pil_img, mask=pil_img.split()[3])
                    pil_img = background

            self.signals.progress.emit(self.file_path, "Estandarizando / Exportando...")
            base_name = os.path.splitext(os.path.basename(self.file_path))[0]
            
            # Asegurar directorio de salida
            os.makedirs(self.output_dir, exist_ok=True)
            output_webp_path = os.path.join(self.output_dir, f"{base_name}_processed.webp")

            export_to_webp(
                pil_image=pil_img,
                output_path=output_webp_path,
                quality=self.quality,
                method=6,
                resize_config=self.resize_config
            )

            cloud_url = ""

            if self.upload_to_cloud and self.cloud_service:
                self.signals.progress.emit(self.file_path, "Subiendo a GCS...")
                
                # El servicio de nube ya antepone la base_folder configurada, 
                # por lo que pasamos el nombre base o dejamos que el servicio decida.
                destination_blob_name = f"{os.path.basename(output_webp_path)}"
                
                res_url = self.cloud_service.upload_file(
                    output_webp_path, 
                    destination_blob_name=destination_blob_name,
                    make_public=True
                )
                if res_url:
                    cloud_url = res_url

            # Emitimos la ruta local y la URL en la nube
            self.signals.finished.emit(self.file_path, output_webp_path, cloud_url)

        except Exception as e:
            self.signals.error.emit(self.file_path, str(e))