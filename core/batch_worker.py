import os
from pathlib import Path
from PySide6.QtCore import QObject, QRunnable, Signal

from core.pipeline import BatchOptions, process_single_image
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
            options = BatchOptions(
                quality=self.quality,
                remove_bg=self.remove_bg,
                white_bg=self.white_bg,
                resize_enabled=bool(self.resize_config and self.resize_config.get("enabled", False)),
                width=(self.resize_config or {}).get("width", 900),
                height=(self.resize_config or {}).get("height", 900),
                resize_mode=(self.resize_config or {}).get("mode", "contain"),
                upload_gcs=self.upload_to_cloud,
            )
            result = process_single_image(
                self.file_path,
                self.output_dir,
                options,
                session=self.session,
                cloud_service=self.cloud_service if self.upload_to_cloud else None,
                target_subfolder=self.target_subfolder,
                progress=self.signals.progress.emit,
            )
            self.signals.finished.emit(self.file_path, result.output_path, result.cloud_url)

        except Exception as e:
            self.signals.error.emit(self.file_path, str(e))
