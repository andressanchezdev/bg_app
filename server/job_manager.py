"""
Cola de trabajos de la API: recibe carpetas de imágenes ya extraídas en disco y las procesa
una a la vez en un hilo de fondo con el BatchPipeline compartido.
"""
import logging
import queue
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import app_paths
import config
from core.pipeline import BatchOptions, BatchPipeline

log = logging.getLogger(__name__)


@dataclass
class Job:
    job_id: str
    input_dir: Path
    output_dir: Path
    options: BatchOptions
    status: str = "queued"        # queued | running | done | failed
    created_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    done: int = 0
    total: int = 0
    message: str = "En cola"
    results: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    db: Optional[Dict[str, Any]] = None
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "message": self.message,
            "progress": {"done": self.done, "total": self.total},
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "results": self.results,
            "warnings": self.warnings,
            "db": self.db,
            "error": self.error,
        }


class JobManager:
    def __init__(self):
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._worker = threading.Thread(target=self._loop, name="api-jobs", daemon=True)
        self._worker.start()

    @staticmethod
    def new_job_dirs() -> tuple:
        job_id = uuid.uuid4().hex[:12]
        base = app_paths.jobs_dir() / job_id
        (base / "input").mkdir(parents=True, exist_ok=True)
        (base / "output").mkdir(parents=True, exist_ok=True)
        return job_id, base / "input", base / "output"

    def submit(self, job_id: str, input_dir: Path, output_dir: Path, options: BatchOptions) -> Job:
        job = Job(job_id=job_id, input_dir=input_dir, output_dir=output_dir, options=options)
        with self._lock:
            self._jobs[job_id] = job
        self._queue.put(job_id)
        log.info("Trabajo %s en cola (%s)", job_id, input_dir)
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {"job_id": j.job_id, "status": j.status, "progress": {"done": j.done, "total": j.total}}
                for j in sorted(self._jobs.values(), key=lambda x: x.created_at, reverse=True)
            ]

    def _loop(self) -> None:
        while True:
            job_id = self._queue.get()
            job = self.get(job_id)
            if job is None:
                continue
            self._run(job)
            self._cleanup_old_jobs()

    def _run(self, job: Job) -> None:
        job.status, job.message = "running", "Procesando"

        def on_progress(done: int, total: int, msg: str) -> None:
            job.done, job.total, job.message = done, total, msg

        try:
            report = BatchPipeline(job.options).run(str(job.input_dir), str(job.output_dir), on_progress)
            job.total = report["total"]
            job.results, job.warnings, job.db = report["results"], report["warnings"], report["db"]
            job.status = "done"
            ok = sum(1 for r in job.results if r.get("ok"))
            job.message = f"{ok} de {job.total} imágenes procesadas correctamente"
        except Exception as e:
            log.exception("Trabajo %s falló", job.job_id)
            job.status, job.error, job.message = "failed", str(e), "Error"
        finally:
            job.finished_at = time.time()
            shutil.rmtree(job.input_dir, ignore_errors=True)

    def _cleanup_old_jobs(self) -> None:
        limit = time.time() - config.SERVER_JOB_RETENTION_DAYS * 86400
        for path in app_paths.jobs_dir().iterdir():
            try:
                if path.is_dir() and path.stat().st_mtime < limit:
                    shutil.rmtree(path, ignore_errors=True)
                    with self._lock:
                        self._jobs.pop(path.name, None)
            except OSError:
                pass
