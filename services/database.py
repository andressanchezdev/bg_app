import os
import json
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

import sqlite3

# Cargar variables de entorno desde .env si existe
ENV_PATH = os.path.join(os.getcwd(), ".env")
CONFIG_FILE_PATH = os.path.join(os.getcwd(), "output", "db_config.json")


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


def format_pg_error(err: Exception, cfg: Dict[str, Any]) -> str:
    """
    Traduce errores técnicos de PostgreSQL a explicaciones claras y comprensibles
    para el usuario final.
    """
    try:
        err_str = str(err).lower()
    except Exception:
        err_str = repr(err).lower()

    user = cfg.get("user", "postgres")
    dbname = cfg.get("database", "Imagenes")
    host = cfg.get("host", "localhost")
    port = cfg.get("port", 5432)

    # Detectar error de autenticación / contraseña (incluyendo codificación de Windows en español)
    if "password authentication failed" in err_str or "autenticaci" in err_str or "contrase" in err_str or "codec can't decode" in err_str:
        return (
            f"La contraseña ingresada para el usuario '{user}' no es correcta.\n\n"
            "Solución: Verifica la clave que le asignaste a PostgreSQL en tu equipo o en pgAdmin 4."
        )

    if "does not exist" in err_str and "database" in err_str:
        return (
            f"La base de datos '{dbname}' no existe en tu PostgreSQL.\n\n"
            f"Solución: Abre pgAdmin 4 y asegúrate de crear la base de datos con el nombre exacto '{dbname}', "
            "o ingresa una base de datos existente en el campo correspondiente."
        )

    if "connection to server" in err_str and ("refused" in err_str or "failed" in err_str or "sin respuesta" in err_str):
        return (
            f"No se pudo conectar al servidor de PostgreSQL en {host}:{port}.\n\n"
            "Solución: Asegúrate de que el servicio de PostgreSQL esté iniciado en Windows "
            "o ábrelo a través de pgAdmin 4."
        )

    if "role" in err_str and "does not exist" in err_str:
        return (
            f"El usuario '{user}' no existe en tu servidor PostgreSQL.\n\n"
            "Solución: Revisa que el nombre de usuario sea correcto (el predeterminado es 'postgres')."
        )

    return (
        f"Aviso de conexión con PostgreSQL:\n\n{err_str}"
    )


class DatabaseService:
    """
    Servicio de base de datos con soporte primario para PostgreSQL (pgAdmin 4).
    Maneja la conexión, creación de esquemas y registro de lotes e imágenes.
    """

    def __init__(self, pg_config: Optional[Dict[str, Any]] = None):
        self.pg_config = pg_config or self._load_pg_config()
        self.engine_type = "postgres"
        self.sqlite_fallback_path = os.path.join(os.getcwd(), "output", "bg_app_local.db")

        try:
            self.init_pg_schema()
        except Exception:
            self._init_sqlite_schema()

    def _load_pg_config(self) -> Dict[str, Any]:
        cfg = DEFAULT_PG_CONFIG.copy()
        if os.path.exists(CONFIG_FILE_PATH):
            try:
                with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    cfg.update(data.get("postgres", {}))
            except Exception:
                pass
        return cfg

    def save_pg_config(self, new_config: Dict[str, Any]):
        self.pg_config = {**self.pg_config, **new_config}
        os.makedirs(os.path.dirname(CONFIG_FILE_PATH), exist_ok=True)
        try:
            current_data = {}
            if os.path.exists(CONFIG_FILE_PATH):
                with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
                    current_data = json.load(f)
            current_data["postgres"] = self.pg_config
            with open(CONFIG_FILE_PATH, "w", encoding="utf-8") as f:
                json.dump(current_data, f, indent=2)
        except Exception as e:
            print(f"[Error guardando config DB]: {e}")

    def get_pg_connection(self):
        if not PSYCOPG2_AVAILABLE:
            raise RuntimeError("psycopg2 no está instalado.")
        return psycopg2.connect(
            host=self.pg_config.get("host", "localhost"),
            port=int(self.pg_config.get("port", 5432)),
            dbname=self.pg_config.get("database", "Imagenes"),
            user=self.pg_config.get("user", "postgres"),
            password=self.pg_config.get("password", "password_123"),
            connect_timeout=3
        )

    def init_pg_schema(self):
        """Crea las tablas en PostgreSQL si no existen."""
        with self.get_pg_connection() as conn:
            with conn.cursor() as cur:
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
            self.engine_type = "postgres"

    def _init_sqlite_schema(self):
        Path(self.sqlite_fallback_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.sqlite_fallback_path)
        with conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
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
                )
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
                )
            """)
            conn.commit()

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
                
                # Validar tablas existentes
                cur.execute("""
                    SELECT table_name FROM information_schema.tables 
                    WHERE table_schema = 'public' AND table_name IN ('batches', 'images', 'app_settings');
                """)
                tables = [r[0] for r in cur.fetchall()]

                # Contar imágenes registradas si la tabla existe
                images_count = 0
                if "images" in tables:
                    cur.execute("SELECT COUNT(*) FROM images;")
                    images_count = cur.fetchone()[0]

            conn.close()

            # Asegurar esquema
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
            return {
                "ok": False,
                "message": human_msg
            }

    # =========================================================================
    # OPERACIONES CRUD
    # =========================================================================
    def set_setting(self, key: str, value: str):
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
