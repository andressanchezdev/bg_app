"""
Servidor HTTP de la red local (solo biblioteca estándar).

Endpoints:
  GET  /health            Estado del servicio (sin autenticación).
  POST /jobs              Recibe imágenes y crea un trabajo (requiere cabecera X-API-Key).
                          Cuerpo admitido:
                            - application/zip        carpeta comprimida (subcarpetas = código de producto)
                            - multipart/form-data    uno o varios archivos (campo "files")
                            - image/*                una sola imagen (?filename=codigo.jpg)
                          Parámetros (query): quality, white_bg, remove_bg, resize, width, height,
                          mode, upload_gcs, register_db.
  GET  /jobs              Lista de trabajos (requiere X-API-Key).
  GET  /jobs/<id>         Estado y resultado del trabajo (requiere X-API-Key).
"""
import hmac
import json
import logging
import os
import shutil
import socket
import tempfile
import threading
import zipfile
from email.parser import BytesParser
from email.policy import default as email_policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import config
from core.pipeline import BatchOptions, build_cloud_service
from server.job_manager import JobManager
from services.image_indexer import VALID_EXTENSIONS

log = logging.getLogger(__name__)
CHUNK = 1024 * 1024


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def lan_addresses() -> List[str]:
    """IPv4 de este equipo en la red local (para mostrar al usuario)."""
    ips = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith("127."))


def _bool(params: Dict[str, List[str]], key: str, default: bool) -> bool:
    if key not in params:
        return default
    return params[key][0].strip().lower() in ("1", "true", "yes", "si", "sí", "on")


def _int(params: Dict[str, List[str]], key: str, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(params[key][0])))
    except (KeyError, ValueError, IndexError):
        return default


def options_from_query(params: Dict[str, List[str]]) -> BatchOptions:
    mode = params.get("mode", ["contain"])[0]
    return BatchOptions(
        quality=_int(params, "quality", 90, 1, 100),
        remove_bg=_bool(params, "remove_bg", True),
        white_bg=_bool(params, "white_bg", False),
        resize_enabled=_bool(params, "resize", True),
        width=_int(params, "width", 900, 16, 8000),
        height=_int(params, "height", 900, 16, 8000),
        resize_mode=mode if mode in ("contain", "cover", "stretch") else "contain",
        upload_gcs=_bool(params, "upload_gcs", True),
        register_db=_bool(params, "register_db", False),
    )


def safe_relative_path(name: str) -> Optional[PurePosixPath]:
    """Normaliza una ruta recibida y descarta rutas absolutas o con '..' (zip-slip)."""
    parts = [p for p in name.replace("\\", "/").split("/") if p not in ("", ".")]
    if not parts or any(p == ".." or ":" in p for p in parts):
        return None
    return PurePosixPath(*parts)


def is_image_name(name: str) -> bool:
    return Path(name).suffix.lower() in VALID_EXTENSIONS


def extract_zip(zip_path: str, dest: Path, max_bytes: int) -> int:
    count, total = 0, 0
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir() or not is_image_name(info.filename):
                continue
            rel = safe_relative_path(info.filename)
            if rel is None or rel.parts[0] == "__MACOSX":
                continue
            total += info.file_size
            if total > max_bytes:
                raise ApiError(413, "El contenido descomprimido supera el tamaño máximo permitido.")
            target = dest.joinpath(*rel.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out, CHUNK)
            count += 1
    return count


def extract_multipart(body_path: str, content_type: str, dest: Path) -> int:
    with open(body_path, "rb") as f:
        header = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode()
        msg = BytesParser(policy=email_policy).parsebytes(header + f.read())
    if not msg.is_multipart():
        raise ApiError(400, "Cuerpo multipart inválido.")
    count = 0
    for part in msg.iter_parts():
        filename = part.get_filename()
        if not filename:
            continue
        data = part.get_payload(decode=True) or b""
        if filename.lower().endswith(".zip"):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
                tmp.write(data)
            try:
                count += extract_zip(tmp.name, dest, config.SERVER_MAX_UPLOAD_MB * CHUNK * 4)
            finally:
                os.unlink(tmp.name)
            continue
        rel = safe_relative_path(filename)
        if rel is None or not is_image_name(rel.name):
            continue
        target = dest.joinpath(*rel.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        count += 1
    return count


class ApiRequestHandler(BaseHTTPRequestHandler):
    server_version = "RemoverBackgroundIP"
    protocol_version = "HTTP/1.1"

    @property
    def app(self) -> "ApiServer":
        return self.server.app  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args) -> None:
        log.info("%s - %s", self.address_string(), fmt % args)

    # -- utilidades -------------------------------------------------------------------------
    def _send_json(self, status: int, payload) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _require_api_key(self) -> None:
        expected = config.SERVER_API_KEY or ""
        received = self.headers.get("X-API-Key", "")
        if not expected or not hmac.compare_digest(expected, received):
            raise ApiError(401, "API key inválida o ausente (cabecera X-API-Key).")

    def _save_body(self) -> str:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            raise ApiError(411, "Se requiere Content-Length con el contenido a procesar.")
        if length > config.SERVER_MAX_UPLOAD_MB * CHUNK:
            raise ApiError(413, f"El archivo supera el máximo de {config.SERVER_MAX_UPLOAD_MB} MB.")
        tmp = tempfile.NamedTemporaryFile(delete=False, prefix="bgapp_upload_")
        remaining = length
        with tmp:
            while remaining > 0:
                chunk = self.rfile.read(min(CHUNK, remaining))
                if not chunk:
                    break
                tmp.write(chunk)
                remaining -= len(chunk)
        if remaining:
            os.unlink(tmp.name)
            raise ApiError(400, "La conexión se cerró antes de recibir todo el contenido.")
        return tmp.name

    def _dispatch(self, method: str) -> None:
        try:
            url = urlparse(self.path)
            parts = [p for p in url.path.split("/") if p]
            if method == "GET" and parts in (["health"], []):
                return self._send_json(200, self.app.health())
            if parts and parts[0] == "jobs":
                self._require_api_key()
                if method == "POST" and len(parts) == 1:
                    return self._create_job(parse_qs(url.query))
                if method == "GET" and len(parts) == 1:
                    return self._send_json(200, {"jobs": self.app.jobs.list()})
                if method == "GET" and len(parts) == 2:
                    job = self.app.jobs.get(parts[1])
                    if job is None:
                        raise ApiError(404, "Trabajo no encontrado.")
                    return self._send_json(200, job.to_dict())
            raise ApiError(404, "Ruta no encontrada.")
        except ApiError as e:
            self._send_json(e.status, {"error": e.message})
        except Exception as e:
            log.exception("Error atendiendo %s %s", method, self.path)
            self._send_json(500, {"error": f"Error interno: {e}"})

    def _create_job(self, params: Dict[str, List[str]]) -> None:
        content_type = self.headers.get("Content-Type", "").strip()
        ctype = content_type.split(";")[0].strip().lower()
        body_path = self._save_body()
        job_id, input_dir, output_dir = self.app.jobs.new_job_dirs()
        try:
            if ctype in ("application/zip", "application/x-zip-compressed", "application/octet-stream"):
                if not zipfile.is_zipfile(body_path):
                    raise ApiError(400, "El contenido no es un archivo ZIP válido.")
                count = extract_zip(body_path, input_dir, config.SERVER_MAX_UPLOAD_MB * CHUNK * 4)
            elif ctype == "multipart/form-data":
                count = extract_multipart(body_path, content_type, input_dir)
            elif ctype.startswith("image/"):
                name = params.get("filename", [""])[0] or self.headers.get("X-Filename", "")
                rel = safe_relative_path(name) if name else None
                if rel is None or not is_image_name(rel.name):
                    raise ApiError(400, "Indique ?filename=<codigo>.<ext> con una extensión de imagen válida.")
                target = input_dir.joinpath(*rel.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(body_path, target)
                count = 1
            else:
                raise ApiError(415, "Content-Type no soportado. Use application/zip, multipart/form-data o image/*.")
            if count == 0:
                raise ApiError(400, f"No se encontraron imágenes válidas ({', '.join(sorted(VALID_EXTENSIONS))}).")
        except Exception:
            shutil.rmtree(input_dir.parent, ignore_errors=True)
            raise
        finally:
            if os.path.exists(body_path):
                os.unlink(body_path)

        job = self.app.jobs.submit(job_id, input_dir, output_dir, options_from_query(params))
        job.total = count
        self._send_json(202, {"job_id": job_id, "files": count, "status_url": f"/jobs/{job_id}"})

    # -- verbos -----------------------------------------------------------------------------
    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key, X-Filename")
        self.send_header("Content-Length", "0")
        self.end_headers()


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    # En Windows SO_REUSEADDR permite que dos procesos usen el mismo puerto: desactivarlo.
    allow_reuse_address = False


class ApiServer:
    """Controla el ciclo de vida del servidor HTTP en un hilo de fondo."""

    def __init__(self):
        self.jobs = JobManager()
        self._httpd: Optional[_Server] = None
        self._thread: Optional[threading.Thread] = None
        self.port: int = 0
        self.last_error: str = ""

    @property
    def is_running(self) -> bool:
        return self._httpd is not None

    def start(self, port: Optional[int] = None, host: Optional[str] = None) -> bool:
        self.stop()
        self.port = int(config.SERVER_PORT if port is None else port)
        try:
            httpd = _Server((host or config.SERVER_HOST, self.port), ApiRequestHandler)
            self.port = httpd.server_address[1]
        except OSError as e:
            self.last_error = f"No se pudo abrir el puerto {self.port}: {e}"
            log.error(self.last_error)
            return False
        httpd.app = self  # type: ignore[attr-defined]
        self._httpd = httpd
        self._thread = threading.Thread(target=httpd.serve_forever, name="api-http", daemon=True)
        self._thread.start()
        self.last_error = ""
        log.info("Servidor API escuchando en %s:%s", host or config.SERVER_HOST, self.port)
        return True

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
            log.info("Servidor API detenido")

    def urls(self) -> List[str]:
        return [f"http://{ip}:{self.port}" for ip in lan_addresses()] or [f"http://localhost:{self.port}"]

    def health(self) -> Dict:
        from core.bg_remover import get_model_path
        return {
            "status": "ok",
            "app": config.APP_NAME,
            "version": config.APP_VERSION,
            "hostname": socket.gethostname(),
            "port": self.port,
            "addresses": self.urls(),
            "model_ready": get_model_path() is not None,
            "gcs_configured": build_cloud_service() is not None,
            "bucket": getattr(config, "GCS_BUCKET_NAME", ""),
        }
