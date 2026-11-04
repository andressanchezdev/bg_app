import os
import json
import socket
from pathlib import Path
from typing import Optional, Dict, Any, List

try:
    import psycopg2
    from psycopg2 import sql
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    psycopg2 = None
    PSYCOPG2_AVAILABLE = False

try:
    import pymysql
    PYMYSQL_AVAILABLE = True
except ImportError:
    pymysql = None
    PYMYSQL_AVAILABLE = False

try:
    from pymongo import MongoClient
    PYMONGO_AVAILABLE = True
except ImportError:
    MongoClient = None
    PYMONGO_AVAILABLE = False

import sys
import sqlite3
import urllib.request
import urllib.error


def get_app_base_dir() -> str:
    """Retorna el directorio base tanto en desarrollo como en ejecutable congelado (frozen)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.getcwd()


# Cargar variables de entorno desde .env si existe
APP_BASE_DIR = get_app_base_dir()
ENV_PATH = os.path.join(APP_BASE_DIR, ".env")
if not os.path.exists(ENV_PATH) and hasattr(sys, "_MEIPASS"):
    cand_env = os.path.join(sys._MEIPASS, ".env")
    if os.path.exists(cand_env):
        ENV_PATH = cand_env

CONFIG_FILE_PATH = os.path.join(APP_BASE_DIR, "output", "db_config.json")
DEFAULT_SQLITE_PATH = os.path.join(APP_BASE_DIR, "output", "bg_app_local.db")


def load_env_variables() -> Dict[str, str]:
    vars_dict = {}
    if os.path.exists(ENV_PATH):
        try:
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        vars_dict[k] = v
                        os.environ[k] = v
        except Exception:
            pass
    return vars_dict


ENV_VALUES = load_env_variables()

# Valores por defecto leídos prioritariamente del .env del usuario
DEFAULT_PG_CONFIG = {
    "host": ENV_VALUES.get("DB_HOST", os.getenv("DB_HOST", "localhost")),
    "port": int(ENV_VALUES.get("DB_PORT", os.getenv("DB_PORT", "5432"))),
    "database": ENV_VALUES.get("DB_DATABASE", os.getenv("DB_DATABASE", "Imagenes")),
    "user": ENV_VALUES.get("DB_USER", os.getenv("DB_USER", "postgres")),
    "password": ENV_VALUES.get("DB_PASSWORD", os.getenv("DB_PASSWORD", "password_123"))
}

DEFAULT_SQLITE_PATH = os.path.join(os.getcwd(), "output", "bg_app_local.db")

DEFAULT_DB_CONFIG = {
    "active_engine": "postgres",
    "sqlite": {
        "db_path": DEFAULT_SQLITE_PATH
    },
    "postgres": DEFAULT_PG_CONFIG,
    "mariadb": {
        "host": "localhost",
        "port": 3306,
        "database": "Imagenes",
        "user": "root",
        "password": ""
    },
    "mongo": {
        "host": "localhost",
        "port": 27017,
        "database": "Imagenes",
        "uri": "mongodb://localhost:27017/Imagenes",
        "user": "",
        "password": ""
    },
    "express": {
        "url": "http://localhost:3000/api",
        "token": ""
    }
}


def format_pg_error(err: Exception, cfg: Dict[str, Any]) -> str:
    """Traduce errores de PostgreSQL a explicaciones claras."""
    try:
        err_str = str(err).lower()
    except Exception:
        err_str = repr(err).lower()

    user = cfg.get("user", "postgres")
    dbname = cfg.get("database", "Imagenes")
    host = cfg.get("host", "localhost")
    port = cfg.get("port", 5432)

    if "password authentication failed" in err_str or "autenticaci" in err_str or "contrase" in err_str or "codec can't decode" in err_str:
        return (
            f"La contraseña ingresada para el usuario '{user}' no es correcta.\n\n"
            "Solución: Verifica la clave que le asignaste a PostgreSQL en tu equipo o en pgAdmin 4."
        )

    if "does not exist" in err_str and "database" in err_str:
        return (
            f"La base de datos '{dbname}' no existe en tu PostgreSQL.\n\n"
            f"Solución: Abre pgAdmin 4 y asegúrate de crear la base de datos '{dbname}'."
        )

    if "connection to server" in err_str and ("refused" in err_str or "failed" in err_str or "sin respuesta" in err_str):
        return (
            f"No se pudo conectar al servidor de PostgreSQL en {host}:{port}.\n\n"
            "Solución: Asegúrate de que el servicio de PostgreSQL esté iniciado en Windows."
        )

    if "role" in err_str and "does not exist" in err_str:
        return f"El usuario '{user}' no existe en tu servidor PostgreSQL."

    return f"Aviso de conexión con PostgreSQL:\n\n{err_str}"


class DatabaseService:
    """
    Servicio de base de datos multi-motor:
    - SQLite (Local integrado)
    - PostgreSQL (pgAdmin 4)
    - MariaDB / MySQL
    - MongoDB (NoSQL)
    - Express / Servidor API REST
    """

    def __init__(self, initial_config: Optional[Dict[str, Any]] = None):
        self.db_configs = self._load_all_db_config()
        self.active_engine = self.db_configs.get("active_engine", "postgres")
        self.pg_config = self.db_configs.get("postgres", DEFAULT_PG_CONFIG.copy())
        self.sqlite_fallback_path = self.db_configs.get("sqlite", {}).get("db_path", DEFAULT_SQLITE_PATH)

        # Inicializar esquemas y usuario inicial en SQLite
        self._init_sqlite_schema()

        # Si el motor activo es postgres, inicializar PostgreSQL
        if self.active_engine == "postgres":
            try:
                self.init_pg_schema()
            except Exception:
                pass

        # Sembrar usuario inicial de .env en las tablas
        self.ensure_default_user()

    def _load_all_db_config(self) -> Dict[str, Any]:
        cfg = json.loads(json.dumps(DEFAULT_DB_CONFIG))
        if os.path.exists(CONFIG_FILE_PATH):
            try:
                with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for k, v in data.items():
                        if isinstance(v, dict) and k in cfg and isinstance(cfg[k], dict):
                            cfg[k].update(v)
                        else:
                            cfg[k] = v
            except Exception:
                pass
        return cfg

    def get_active_engine(self) -> str:
        return self.active_engine

    def get_engine_config(self, engine: str) -> Dict[str, Any]:
        return self.db_configs.get(engine, DEFAULT_DB_CONFIG.get(engine, {}))

    def save_db_engine_config(self, active_engine: str, engine_configs: Dict[str, Any]):
        self.active_engine = active_engine
        self.db_configs["active_engine"] = active_engine
        for k, v in engine_configs.items():
            self.db_configs[k] = v

        if "postgres" in engine_configs:
            self.pg_config = engine_configs["postgres"]
        if "sqlite" in engine_configs and "db_path" in engine_configs["sqlite"]:
            self.sqlite_fallback_path = engine_configs["sqlite"]["db_path"]

        os.makedirs(os.path.dirname(CONFIG_FILE_PATH), exist_ok=True)
        try:
            with open(CONFIG_FILE_PATH, "w", encoding="utf-8") as f:
                json.dump(self.db_configs, f, indent=2)
        except Exception as e:
            print(f"[Error guardando config DB]: {e}")

        # Inicializar esquemas del motor seleccionado
        if self.active_engine == "postgres":
            try:
                self.init_pg_schema()
            except Exception:
                pass
        else:
            self._init_sqlite_schema()

        self.ensure_default_user()

    # =========================================================================
    # AUTENTICACIÓN DE ACCESO A CONFIGURACIÓN
    # =========================================================================
    def ensure_default_user(self):
        """Asegura que el usuario de .env exista en la tabla users."""
        env_vars = load_env_variables()
        env_user = env_vars.get("USER", os.getenv("USER", "USER")).strip()
        env_pass = env_vars.get("PASSWORD", os.getenv("PASSWORD", "123456")).strip()

        # En SQLite
        try:
            with sqlite3.connect(self.sqlite_fallback_path) as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM users WHERE username = ?", (env_user,))
                if cur.fetchone()[0] == 0:
                    cur.execute(
                        "INSERT INTO users (username, password, role) VALUES (?, ?, 'admin')",
                        (env_user, env_pass)
                    )
                conn.commit()
        except Exception as e:
            pass

        # En PostgreSQL
        if PSYCOPG2_AVAILABLE:
            try:
                with self.get_pg_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT COUNT(*) FROM users WHERE username = %s;", (env_user,))
                        if cur.fetchone()[0] == 0:
                            cur.execute(
                                "INSERT INTO users (username, password, role) VALUES (%s, %s, 'admin');",
                                (env_user, env_pass)
                            )
                    conn.commit()
            except Exception:
                pass

    def authenticate_user(self, username: str, password: str) -> bool:
        """
        Valida las credenciales ingresadas:
        1. Compara contra variables de entorno .env (USER=USER, PASSWORD=123456).
        2. Compara contra tabla 'users' en PostgreSQL si está activo.
        3. Compara contra tabla 'users' en SQLite.
        """
        if not username or not password:
            return False

        u_clean = username.strip()
        p_clean = password.strip()

        # 1. Comprobación directa con .env
        env_vars = load_env_variables()
        env_user = env_vars.get("USER", os.getenv("USER", "USER")).strip()
        env_pass = env_vars.get("PASSWORD", os.getenv("PASSWORD", "123456")).strip()

        if u_clean == env_user and p_clean == env_pass:
            return True

        # 2. Comprobación en PostgreSQL
        if self.active_engine == "postgres" and PSYCOPG2_AVAILABLE:
            try:
                with self.get_pg_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT password FROM users WHERE LOWER(username) = LOWER(%s);", (u_clean,))
                        row = cur.fetchone()
                        if row and row[0] == p_clean:
                            return True
            except Exception:
                pass

        # 3. Comprobación en SQLite
        try:
            with sqlite3.connect(self.sqlite_fallback_path) as conn:
                cur = conn.cursor()
                cur.execute("SELECT password FROM users WHERE LOWER(username) = LOWER(?);", (u_clean,))
                row = cur.fetchone()
                if row and row[0] == p_clean:
                    return True
        except Exception:
            pass

        return False

    # =========================================================================
    # ESQUEMAS Y CONEXIONES POR MOTOR
    # =========================================================================
    def get_pg_connection(self):
        if not PSYCOPG2_AVAILABLE:
            raise RuntimeError("psycopg2 no está disponible.")
        return psycopg2.connect(
            host=self.pg_config.get("host", "localhost"),
            port=int(self.pg_config.get("port", 5432)),
            dbname=self.pg_config.get("database", "Imagenes"),
            user=self.pg_config.get("user", "postgres"),
            password=self.pg_config.get("password", "password_123"),
            connect_timeout=3
        )

    def init_pg_schema(self):
        """Crea las tablas en PostgreSQL incluyendo la tabla de usuarios."""
        with self.get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id SERIAL PRIMARY KEY,
                        username VARCHAR(100) UNIQUE NOT NULL,
                        password VARCHAR(255) NOT NULL,
                        role VARCHAR(50) DEFAULT 'admin',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS app_settings (
                        key VARCHAR(100) PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS batches (
                        id SERIAL PRIMARY KEY,
                        input_path TEXT NOT NULL,
                        total_images INTEGER DEFAULT 0,
                        processed_images INTEGER DEFAULT 0,
                        status VARCHAR(50) DEFAULT 'pending',
                        destination_type VARCHAR(50) DEFAULT 'local',
                        destination_path TEXT,
                        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        finished_at TIMESTAMP
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS images (
                        id SERIAL PRIMARY KEY,
                        batch_id INTEGER REFERENCES batches(id) ON DELETE CASCADE,
                        filename VARCHAR(255) NOT NULL,
                        folder_name VARCHAR(255),
                        relative_path TEXT,
                        original_path TEXT NOT NULL,
                        processed_path TEXT,
                        original_size BIGINT DEFAULT 0,
                        processed_size BIGINT DEFAULT 0,
                        format VARCHAR(20),
                        status VARCHAR(50) DEFAULT 'pending',
                        cloud_url TEXT,
                        error_message TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        processed_at TIMESTAMP
                    );
                """)
            conn.commit()

    def _init_sqlite_schema(self):
        """Crea las tablas en SQLite local."""
        Path(self.sqlite_fallback_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.sqlite_fallback_path)
        with conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    role TEXT DEFAULT 'admin',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS batches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    input_path TEXT NOT NULL,
                    total_images INTEGER DEFAULT 0,
                    processed_images INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending',
                    destination_type TEXT DEFAULT 'local',
                    destination_path TEXT,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    finished_at TIMESTAMP
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_id INTEGER,
                    filename TEXT NOT NULL,
                    folder_name TEXT,
                    relative_path TEXT,
                    original_path TEXT NOT NULL,
                    processed_path TEXT,
                    original_size INTEGER DEFAULT 0,
                    processed_size INTEGER DEFAULT 0,
                    format TEXT,
                    status TEXT DEFAULT 'pending',
                    cloud_url TEXT,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_at TIMESTAMP,
                    FOREIGN KEY (batch_id) REFERENCES batches(id) ON DELETE CASCADE
                );
            """)
            conn.commit()

    # =========================================================================
    # PRUEBA DE CONEXIÓN MULTI-MOTOR
    # =========================================================================
    def test_engine_connection(self, engine: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
        """Prueba la conexión según el motor de base de datos seleccionado."""
        if engine == "sqlite":
            path = cfg.get("db_path", self.sqlite_fallback_path)
            try:
                Path(path).parent.mkdir(parents=True, exist_ok=True)
                with sqlite3.connect(path) as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT sqlite_version();")
                    v = cur.fetchone()[0]
                    cur.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table';")
                    tables = cur.fetchone()[0]
                return {
                    "ok": True,
                    "message": (
                        f"Conexión exitosa a SQLite local.\n\n"
                        f"• Versión SQLite: {v}\n"
                        f"• Archivo: {path}\n"
                        f"• Tablas activas: {tables}"
                    )
                }
            except Exception as e:
                return {"ok": False, "message": f"Error abriendo SQLite:\n{e}"}

        elif engine == "postgres":
            return self.test_pg_connection(cfg)

        elif engine == "mariadb":
            host = cfg.get("host", "localhost")
            port = int(cfg.get("port", 3306))
            user = cfg.get("user", "root")
            pwd = cfg.get("password", "")
            db = cfg.get("database", "Imagenes")

            if PYMYSQL_AVAILABLE:
                try:
                    conn = pymysql.connect(host=host, port=port, user=user, password=pwd, database=db, connect_timeout=3)
                    with conn.cursor() as cur:
                        cur.execute("SELECT VERSION();")
                        v = cur.fetchone()[0]
                    conn.close()
                    return {"ok": True, "message": f"Conexión exitosa a MariaDB/MySQL.\n\n• Versión: {v}\n• Host: {host}:{port}"}
                except Exception as e:
                    return {"ok": False, "message": f"Fallo al conectar a MariaDB/MySQL:\n{e}"}
            else:
                # Comprobar socket TCP
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(3)
                    res = s.connect_ex((host, port))
                    s.close()
                    if res == 0:
                        return {
                            "ok": True,
                            "message": (
                                f"Servidor MariaDB/MySQL detectado en {host}:{port}.\n\n"
                                "El puerto responde correctamente. La persistencia local se mantendrá en SQLite "
                                "hasta instalar el módulo opcional 'pymysql'."
                            )
                        }
                    else:
                        return {"ok": False, "message": f"No se pudo conectar a MariaDB/MySQL en {host}:{port}."}
                except Exception as e:
                    return {"ok": False, "message": f"Error conectando a {host}:{port}:\n{e}"}

        elif engine == "mongo":
            host = cfg.get("host", "localhost")
            port = int(cfg.get("port", 27017))
            uri = cfg.get("uri", f"mongodb://{host}:{port}/")

            if PYMONGO_AVAILABLE:
                try:
                    client = MongoClient(uri, serverSelectionTimeoutMS=3000)
                    client.admin.command('ping')
                    return {"ok": True, "message": f"Conexión exitosa a MongoDB en {host}:{port}."}
                except Exception as e:
                    return {"ok": False, "message": f"Fallo al conectar a MongoDB:\n{e}"}
            else:
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(3)
                    res = s.connect_ex((host, port))
                    s.close()
                    if res == 0:
                        return {
                            "ok": True,
                            "message": (
                                f"Servidor MongoDB detectado en {host}:{port}.\n\n"
                                "El puerto responde correctamente. Puedes usar SQLite local para almacenamiento de lotes."
                            )
                        }
                    else:
                        return {"ok": False, "message": f"No se encontró servidor MongoDB en {host}:{port}."}
                except Exception as e:
                    return {"ok": False, "message": f"Error conectando a MongoDB:\n{e}"}

        elif engine == "express":
            url = cfg.get("url", "http://localhost:3000/api").rstrip("/")
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Antigravity-Client"})
                with urllib.request.urlopen(req, timeout=3) as resp:
                    code = resp.getcode()
                    return {"ok": True, "message": f"Servidor Express respondiendo correctamente en {url} (HTTP {code})."}
            except urllib.error.HTTPError as e:
                # Si devuelve 404 o 200, el servidor existe
                if e.code < 500:
                    return {"ok": True, "message": f"Servidor Express alcanzado en {url} (HTTP {e.code})."}
                return {"ok": False, "message": f"Servidor Express reportó error: HTTP {e.code}"}
            except Exception as e:
                return {"ok": False, "message": f"No se pudo conectar al servidor Express en {url}:\n{e}"}

        return {"ok": False, "message": f"Motor desconocido: {engine}"}

    def test_pg_connection(self, temp_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Prueba la conexión a PostgreSQL con los parámetros proporcionados."""
        cfg = temp_config or self.pg_config
        try:
            conn = psycopg2.connect(
                host=cfg.get("host", "localhost"),
                port=int(cfg.get("port", 5432)),
                dbname=cfg.get("database", "Imagenes"),
                user=cfg.get("user", "postgres"),
                password=cfg.get("password", ""),
                connect_timeout=3
            )
            with conn.cursor() as cur:
                cur.execute("SELECT version();")
                version = cur.fetchone()[0].split(",")[0]
                
                cur.execute("""
                    SELECT table_name FROM information_schema.tables 
                    WHERE table_schema = 'public' AND table_name IN ('batches', 'images', 'app_settings', 'users');
                """)
                tables = [r[0] for r in cur.fetchall()]

                images_count = 0
                if "images" in tables:
                    cur.execute("SELECT COUNT(*) FROM images;")
                    images_count = cur.fetchone()[0]

            conn.close()
            self.init_pg_schema()

            return {
                "ok": True,
                "version": version,
                "images_count": images_count,
                "message": (
                    f"Conexión exitosa a PostgreSQL.\n\n"
                    f"• Base de datos: {cfg.get('database')}\n"
                    f"• Servidor: {version}\n"
                    f"• Tablas verificadas: {', '.join(tables) if tables else 'Creadas exitosamente'}\n"
                    f"• Imágenes registradas en pgAdmin 4: {images_count}"
                )
            }
        except Exception as e:
            human_msg = format_pg_error(e, cfg)
            return {"ok": False, "message": human_msg}

    # =========================================================================
    # OPERACIONES CRUD (TRANSPARENTE ENTRE MOTORES)
    # =========================================================================
    def set_setting(self, key: str, value: str):
        if self.active_engine == "postgres" and PSYCOPG2_AVAILABLE:
            try:
                with self.get_pg_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO app_settings (key, value, updated_at)
                            VALUES (%s, %s, CURRENT_TIMESTAMP)
                            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP;
                        """, (key, value))
                    conn.commit()
                    return
            except Exception:
                pass

        try:
            with sqlite3.connect(self.sqlite_fallback_path) as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO app_settings (key, value, updated_at) 
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP
                """, (key, value))
                conn.commit()
        except Exception:
            pass

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        if self.active_engine == "postgres" and PSYCOPG2_AVAILABLE:
            try:
                with self.get_pg_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT value FROM app_settings WHERE key = %s;", (key,))
                        row = cur.fetchone()
                        if row:
                            return row[0]
            except Exception:
                pass

        try:
            with sqlite3.connect(self.sqlite_fallback_path) as conn:
                cur = conn.cursor()
                cur.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
                row = cur.fetchone()
                if row:
                    return row[0]
        except Exception:
            pass

        return default

    def create_batch(self, input_path: str, total_images: int) -> int:
        if self.active_engine == "postgres" and PSYCOPG2_AVAILABLE:
            try:
                with self.get_pg_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO batches (input_path, total_images, status, started_at)
                            VALUES (%s, %s, 'processing', CURRENT_TIMESTAMP)
                            RETURNING id;
                        """, (input_path, total_images))
                        batch_id = cur.fetchone()[0]
                    conn.commit()
                    return batch_id
            except Exception as e:
                print(f"[Aviso DB PG]: {e}")

        with sqlite3.connect(self.sqlite_fallback_path) as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO batches (input_path, total_images, status, started_at)
                VALUES (?, ?, 'processing', CURRENT_TIMESTAMP)
            """, (input_path, total_images))
            conn.commit()
            return cur.lastrowid

    def record_image_start(self, batch_id: int, rec: Dict[str, Any]) -> int:
        orig_path = rec.get("absolute_path", "")
        orig_size = os.path.getsize(orig_path) if os.path.exists(orig_path) else 0
        ext = Path(orig_path).suffix.lower().replace(".", "")

        if self.active_engine == "postgres" and PSYCOPG2_AVAILABLE:
            try:
                with self.get_pg_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO images (
                                batch_id, filename, folder_name, relative_path,
                                original_path, original_size, format, status
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'processing')
                            RETURNING id;
                        """, (
                            batch_id,
                            rec.get("filename", ""),
                            rec.get("folder_name", ""),
                            rec.get("relative_path", ""),
                            orig_path,
                            orig_size,
                            ext
                        ))
                        img_id = cur.fetchone()[0]
                    conn.commit()
                    return img_id
            except Exception:
                pass

        with sqlite3.connect(self.sqlite_fallback_path) as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO images (
                    batch_id, filename, folder_name, relative_path,
                    original_path, original_size, format, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'processing')
            """, (
                batch_id,
                rec.get("filename", ""),
                rec.get("folder_name", ""),
                rec.get("relative_path", ""),
                orig_path,
                orig_size,
                ext
            ))
            conn.commit()
            return cur.lastrowid

    def update_image_success(
        self,
        original_path: str,
        processed_path: str,
        cloud_url: Optional[str] = None
    ):
        proc_size = os.path.getsize(processed_path) if os.path.exists(processed_path) else 0
        if self.active_engine == "postgres" and PSYCOPG2_AVAILABLE:
            try:
                with self.get_pg_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            UPDATE images
                            SET status = 'completed',
                                processed_path = %s,
                                processed_size = %s,
                                cloud_url = COALESCE(%s, cloud_url),
                                processed_at = CURRENT_TIMESTAMP
                            WHERE original_path = %s;
                        """, (processed_path, proc_size, cloud_url, original_path))
                    conn.commit()
                    return
            except Exception:
                pass

        with sqlite3.connect(self.sqlite_fallback_path) as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE images
                SET status = 'completed',
                    processed_path = ?,
                    processed_size = ?,
                    cloud_url = COALESCE(?, cloud_url),
                    processed_at = CURRENT_TIMESTAMP
                WHERE original_path = ?
            """, (processed_path, proc_size, cloud_url, original_path))
            conn.commit()

    def update_image_error(self, original_path: str, error_message: str):
        if self.active_engine == "postgres" and PSYCOPG2_AVAILABLE:
            try:
                with self.get_pg_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            UPDATE images
                            SET status = 'error',
                                error_message = %s,
                                processed_at = CURRENT_TIMESTAMP
                            WHERE original_path = %s;
                        """, (error_message, original_path))
                    conn.commit()
                    return
            except Exception:
                pass

        with sqlite3.connect(self.sqlite_fallback_path) as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE images
                SET status = 'error',
                    error_message = ?,
                    processed_at = CURRENT_TIMESTAMP
                WHERE original_path = ?
            """, (error_message, original_path))
            conn.commit()

    def finish_batch(
        self,
        batch_id: int,
        processed_count: int,
        destination_type: str = "local",
        destination_path: str = ""
    ):
        if self.active_engine == "postgres" and PSYCOPG2_AVAILABLE:
            try:
                with self.get_pg_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            UPDATE batches
                            SET status = 'completed',
                                processed_images = %s,
                                destination_type = %s,
                                destination_path = %s,
                                finished_at = CURRENT_TIMESTAMP
                            WHERE id = %s;
                        """, (processed_count, destination_type, destination_path, batch_id))
                    conn.commit()
                    return
            except Exception:
                pass

        with sqlite3.connect(self.sqlite_fallback_path) as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE batches
                SET status = 'completed',
                    processed_images = ?,
                    destination_type = ?,
                    destination_path = ?,
                    finished_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (processed_count, destination_type, destination_path, batch_id))
            conn.commit()
