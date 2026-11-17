import os
import json
import requests
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Union

try:
    import pymysql
    PYMYSQL_AVAILABLE = True
except ImportError:
    pymysql = None
    PYMYSQL_AVAILABLE = False

try:
    import psycopg2
    from psycopg2 import sql
    PSYCOPG2_AVAILABLE = True
except ImportError:
    psycopg2 = None
    PSYCOPG2_AVAILABLE = False

import config


def get_db_config() -> Dict[str, Any]:
    """
    Obtiene la configuración activa de la base de datos y endpoint API,
    combinando settings.json con las variables del archivo .env por defecto.
    """
    return {
        "host": getattr(config, "DB_HOST", os.getenv("DB_HOST", "localhost")),
        "port": int(getattr(config, "DB_PORT", os.getenv("DB_PORT", "3306"))),
        "database": getattr(config, "DB_DATABASE", os.getenv("DB_DATABASE", os.getenv("DB_NAME", "mysql"))),
        "user": getattr(config, "DB_USER", os.getenv("DB_USER", "root")),
        "password": getattr(config, "DB_PASSWORD", os.getenv("DB_PASSWORD", "password_123")),
        "table": getattr(config, "DB_TABLE", os.getenv("DB_TABLE", "productos")),
        "code_column": getattr(config, "DB_CODE_COLUMN", os.getenv("DB_CODE_COLUMN", "codigo")),
        "image_column": getattr(config, "DB_IMAGE_COLUMN", os.getenv("DB_IMAGE_COLUMN", "imagenArray")),
        "api_endpoint": getattr(config, "DB_API_ENDPOINT", ""),
        "sync_mode": getattr(config, "DB_SYNC_MODE", "db"),  # db, api, both
        "engine": getattr(config, "DB_ENGINE", ""),  # mysql, postgres o vacío (se deduce del puerto)
        "schema": getattr(config, "DB_SCHEMA", "public"),
        "company_id": getattr(config, "DB_COMPANY_ID", ""),
    }


def resolve_engine(c: Dict[str, Any]) -> str:
    """Motor de la base de productos: el elegido en Ajustes o, si no hay, el que indica el puerto (comportamiento anterior)."""
    engine = (c.get("engine") or "").strip().lower()
    if engine in ("mysql", "mariadb"):
        return "mysql"
    if engine in ("postgres", "postgresql", "pg"):
        return "postgres"
    return "mysql" if is_mysql_port(int(c.get("port", 3306) or 3306)) else "postgres"


def is_mysql_port(port: int) -> bool:
    """Identifica si el puerto corresponde usualmente a MySQL / MariaDB (3306, 3307, etc.)."""
    return port in (3306, 3307, 3308)


def _base_folder() -> str:
    folder = (getattr(config, "GCS_BASE_FOLDER", "") or "").strip().strip("/\\").replace("\\", "/")
    return folder


def extract_gcp_relative_path(item: dict) -> str:
    """
    Ruta relativa con la que se consume la imagen (ej: dependencias/img/productos/{codigo}/{archivo}.webp).
    Es exactamente el nombre del objeto en el bucket: la interfaz la concatena con su URL base del bucket.
    """
    cloud_url = (item.get("cloud_url") or "").strip()
    if cloud_url:
        unquoted = urllib.parse.unquote(cloud_url).split("?", 1)[0]
        bucket = (getattr(config, "GCS_BUCKET_NAME", "") or "").strip("/")
        prefixes = []
        try:
            prefixes.append(config.public_base_url())
        except Exception:
            pass
        if bucket:
            prefixes += [f"https://storage.googleapis.com/{bucket}/", f"https://{bucket}.storage.googleapis.com/",
                         f"http://storage.googleapis.com/{bucket}/"]
        for prefix in prefixes:
            if prefix and unquoted.startswith(prefix):
                return unquoted[len(prefix):].lstrip("/").replace("\\", "/")
        folder = _base_folder()
        if folder and folder in unquoted:
            return unquoted[unquoted.index(folder):].replace("\\", "/")
        if "dependencias/" in unquoted:
            return unquoted[unquoted.index("dependencias/"):].replace("\\", "/")

    subfolder = item.get("folder_name", "").strip().strip("/\\")
    fname = (item.get("uploaded_filename") or item.get("filename", "")).strip()
    stem = Path(fname).stem
    webp_name = f"{stem}.webp" if not fname.lower().endswith(".webp") else fname
    parts = [p for p in (_base_folder(), subfolder, webp_name) if p]
    return "/".join(parts).replace("\\", "/")


def extract_candidate_codes(item: dict) -> List[str]:
    """
    Obtiene los posibles códigos de producto asociados a una imagen
    a partir de la subcarpeta o del nombre del archivo.
    """
    candidates = []
    folder = item.get("folder_name", "").strip().strip("/\\")
    if folder:
        candidates.append(folder)

    fname = item.get("filename", "")
    stem = os.path.splitext(fname)[0].strip()
    if stem and stem not in candidates:
        candidates.append(stem)

    for sep in ['-', '_', ' ']:
        if sep in stem:
            part = stem.split(sep)[0].strip()
            if part and part not in candidates:
                candidates.append(part)

    return candidates


def test_db_connection(cfg: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Prueba la conexión a la base de datos (MySQL/HeidiSQL o PostgreSQL) con los parámetros configurados.
    Valida la existencia de la tabla e informa la cantidad de registros.
    """
    c = cfg or get_db_config()
    host = c.get("host", "localhost")
    port = int(c.get("port", 3306))
    dbname = c.get("database", "mysql")
    user = c.get("user", "root")
    password = c.get("password", "")
    target_table = (c.get("table", "productos") or "productos").strip()

    # 1. Conexión MySQL / MariaDB (HeidiSQL): misma lógica de siempre
    if resolve_engine(c) == "mysql":
        if not PYMYSQL_AVAILABLE:
            return {"ok": False, "message": "El controlador 'pymysql' no está instalado en Python."}

        try:
            conn = pymysql.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=dbname,
                connect_timeout=4
            )
            with conn.cursor() as cur:
                # Comprobar versión
                cur.execute("SELECT VERSION();")
                version = cur.fetchone()[0]

                # Comprobar tabla
                cur.execute("SHOW TABLES LIKE %s;", (target_table,))
                table_exists = cur.fetchone() is not None

                if not table_exists:
                    # Crear tabla genérica si no existe
                    cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS `{target_table}` (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        codigo VARCHAR(50),
                        imagenArray TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    """)
                    conn.commit()

                cur.execute(f"SELECT COUNT(*) FROM `{target_table}`;")
                count = cur.fetchone()[0]

            conn.close()
            return {
                "ok": True,
                "message": (
                    f"Conexión exitosa a MySQL / MariaDB (HeidiSQL).\n\n"
                    f"• Versión del motor: {version}\n"
                    f"• Servidor: {host}:{port}\n"
                    f"• Base de datos: '{dbname}'\n"
                    f"• Tabla activa: '{target_table}' ({count:,} registros)"
                )
            }
        except Exception as e:
            return {
                "ok": False,
                "message": f"Fallo al conectar con MySQL ({host}:{port}/{dbname}):\n{e}"
            }

    # 2. Conexión PostgreSQL: solo lee, nunca crea tablas
    return _pg_test(c)


def test_api_endpoint(endpoint_url: str = None) -> Dict[str, Any]:
    """
    Prueba el envío de un payload POST mínimo al Endpoint REST API.
    """
    url = (endpoint_url or get_db_config().get("api_endpoint", "")).strip()
    if not url:
        return {"ok": False, "message": "No se ha configurado ninguna URL de Endpoint API (Base URL)."}

    sample_payload = {
        "ping": True,
        "test": True,
        "timestamp": datetime.now().isoformat(),
        "total": 1,
        "items": [
            {
                "codigo": "TEST_CODE",
                "filename": "test_ping.webp",
                "folder_name": "test",
                "cloud_url": "https://storage.googleapis.com/test_ping.webp",
                "gcp_path": "dependencias/img/productos/test/test_ping.webp",
                "status": "TEST"
            }
        ]
    }

    try:
        resp = requests.post(
            url,
            json=sample_payload,
            headers={"Content-Type": "application/json", "User-Agent": "BgApp-Client/1.0"},
            timeout=5
        )
        if resp.status_code in (200, 201, 202):
            return {
                "ok": True,
                "message": f"Endpoint API respondió exitosamente.\n• Código HTTP: {resp.status_code}\n• Respuesta: {resp.text[:200]}"
            }
        else:
            return {
                "ok": False,
                "message": f"El Endpoint respondió con código de estado HTTP {resp.status_code}:\n{resp.text[:300]}"
            }
    except Exception as e:
        return {
            "ok": False,
            "message": f"No se pudo conectar con el Endpoint API ({url}):\n{e}"
        }


def post_image_records(
    records: Union[List[Dict[str, Any]], Dict[str, Any]],
    cfg: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Método adaptable para registrar las rutas y URLs de imágenes procesadas.
    Soporta:
      - MySQL / MariaDB (HeidiSQL): actualiza el campo `imagenArray` del producto según su `codigo`.
      - PostgreSQL: inserta en tabla de imágenes.
      - Endpoint REST API: envía petición HTTP POST con el payload estructurado.
    """
    c = cfg or get_db_config()
    sync_mode = c.get("sync_mode", "db")
    endpoint_url = c.get("api_endpoint", "").strip()

    # Normalizar a lista
    if isinstance(records, dict):
        raw_list = [records]
    elif isinstance(records, list):
        raw_list = records
    else:
        return {"ok": False, "message": "Formato de datos no válido para registro."}

    # Filtrar y formatear elementos válidos
    items_to_save = []
    for item in raw_list:
        fname = item.get("filename") or os.path.basename(item.get("processed_path", "") or item.get("relative_path", ""))
        c_url = item.get("cloud_url", "")
        if not fname:
            continue
        gcp_path = extract_gcp_relative_path(item)
        candidates = extract_candidate_codes(item)
        orig_p = item.get("original_path") or item.get("absolute_path") or item.get("processed_path") or ""
        proc_p = item.get("processed_path", "") or ""

        items_to_save.append({
            "filename": fname,
            "folder_name": item.get("folder_name", "") or "",
            "relative_path": item.get("relative_path", "") or "",
            "original_path": orig_p,
            "processed_path": proc_p,
            "cloud_url": c_url,
            "gcp_path": gcp_path,
            "candidate_codes": candidates,
            "format": "WEBP",
            "status": "PROCESADA" if c_url else "PENDIENTE_GCP",
            "processed_at": datetime.now().isoformat()
        })

    if not items_to_save:
        return {"ok": False, "message": "No hay imágenes para registrar (lista vacía)."}

    results = {
        "ok": True,
        "total_items": len(items_to_save),
        "db_updated": 0,
        "db_inserted": 0,
        "api_saved": 0,
        "unmatched": [],
        "errors": []
    }

    port = int(c.get("port", 3306))
    host = c.get("host", "localhost")
    dbname = c.get("database", "mysql")
    user = c.get("user", "root")
    password = c.get("password", "")
    target_table = (c.get("table", "productos") or "productos").strip()
    col_code = (c.get("code_column", "codigo") or "codigo").strip()
    col_image = (c.get("image_column", "imagenArray") or "imagenArray").strip()

    # -----------------------------------------------------------------
    # 1. PROCESAMIENTO EN BASE DE DATOS (MySQL / HeidiSQL)
    # -----------------------------------------------------------------
    engine = resolve_engine(c)
    if sync_mode in ("db", "both") and engine == "mysql" and PYMYSQL_AVAILABLE:
        try:
            conn = pymysql.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=dbname,
                connect_timeout=5,
                autocommit=True
            )
            with conn.cursor() as cur:
                # Comprobar si la tabla tiene la columna de búsqueda y la columna de imágenes
                cur.execute(f"SHOW COLUMNS FROM `{target_table}` LIKE %s;", (col_code,))
                has_col_code = cur.fetchone() is not None
                cur.execute(f"SHOW COLUMNS FROM `{target_table}` LIKE %s;", (col_image,))
                has_col_image = cur.fetchone() is not None

                # Si tiene ambas columnas, actualizamos por código de forma dinámica
                if has_col_code and has_col_image:
                    for item in items_to_save:
                        matched = None
                        matched_code = ""

                        # 1. Probar coincidencia exacta con cada candidato
                        for code_cand in item["candidate_codes"]:
                            if not code_cand:
                                continue
                            cur.execute(f"SELECT id, `{col_code}`, `{col_image}` FROM `{target_table}` WHERE `{col_code}` = %s LIMIT 1;", (code_cand,))
                            row = cur.fetchone()
                            if row:
                                matched = row
                                matched_code = row[1]
                                break

                        # 2. Si no hubo coincidencia exacta, probar prefijo
                        if not matched:
                            stem = os.path.splitext(item["filename"])[0]
                            cur.execute(
                                f"SELECT id, `{col_code}`, `{col_image}` FROM `{target_table}` WHERE %s LIKE CONCAT(`{col_code}`, '%%') ORDER BY LENGTH(`{col_code}`) DESC LIMIT 1;",
                                (stem,)
                            )
                            row = cur.fetchone()
                            if row:
                                matched = row
                                matched_code = row[1]

                        if matched:
                            prod_id, prod_code, current_arr_raw = matched
                            try:
                                arr = json.loads(current_arr_raw) if current_arr_raw else []
                                if not isinstance(arr, list):
                                    # Si no es json lista, podría ser una ruta simple previa o texto
                                    arr = [str(current_arr_raw)] if current_arr_raw else []
                            except Exception:
                                arr = [str(current_arr_raw)] if current_arr_raw else []

                            # Limpiar placeholders de imagen base
                            cleaned_arr = [
                                x for x in arr
                                if "imagen_base_productos.png" not in x and "blanco.png" not in x
                            ]

                            # Agregar nueva ruta relativa si no existe
                            if item["gcp_path"] not in cleaned_arr:
                                cleaned_arr.append(item["gcp_path"])

                            updated_json = json.dumps(cleaned_arr, ensure_ascii=False)
                            cur.execute(f"UPDATE `{target_table}` SET `{col_image}` = %s WHERE id = %s;", (updated_json, prod_id))
                            results["db_updated"] += 1
                        else:
                            results["unmatched"].append(f"{item['filename']} (códigos probados: {item['candidate_codes']})")
                else:
                    # Inserción estándar si la tabla tiene otra estructura (tabla de logs/imágenes)
                    insert_sql = f"""
                    INSERT INTO `{target_table}` (
                        filename, folder_name, relative_path, original_path, processed_path, cloud_url, format, status, processed_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW());
                    """
                    for item in items_to_save:
                        cur.execute(insert_sql, (
                            item["filename"],
                            item["folder_name"],
                            item["relative_path"],
                            item["original_path"],
                            item["processed_path"],
                            item["cloud_url"],
                            item["format"],
                            item["status"]
                        ))
                    results["db_inserted"] = len(items_to_save)
            conn.close()
        except Exception as e:
            results["errors"].append(f"MySQL (HeidiSQL): {e}")

    # -----------------------------------------------------------------
    # 2. PROCESAMIENTO EN BASE DE DATOS (PostgreSQL): agrega la ruta al arreglo de imágenes del producto
    # -----------------------------------------------------------------
    elif sync_mode in ("db", "both") and engine == "postgres":
        if not PSYCOPG2_AVAILABLE:
            results["errors"].append("PostgreSQL: el controlador 'psycopg2' no está instalado.")
        else:
            try:
                pg = _pg_update_images(c, items_to_save)
                results["db_updated"] = pg["added"]
                results["already"] = pg["already"]
                results["unmatched"] += pg["unmatched"]
            except Exception as e:
                results["errors"].append(f"PostgreSQL: {_safe_error(e, password)}")
    elif sync_mode in ("db", "both") and engine == "mysql" and not PYMYSQL_AVAILABLE:
        results["errors"].append("MySQL: el controlador 'pymysql' no está instalado.")

    # -----------------------------------------------------------------
    # 3. ENVÍO HTTP POST AL ENDPOINT API (Base URL)
    # -----------------------------------------------------------------
    # Solo se envía a la API si el modo lo pide ("Solo Base de Datos" no debe hacer POST)
    if sync_mode in ("api", "both") and endpoint_url:
        payload = {
            "total": len(items_to_save),
            "timestamp": datetime.now().isoformat(),
            "items": items_to_save if len(items_to_save) > 1 else items_to_save[0]
        }
        try:
            resp = requests.post(
                endpoint_url,
                json=payload,
                headers={"Content-Type": "application/json", "User-Agent": "BgApp-Client/1.0"},
                timeout=8
            )
            if resp.status_code in (200, 201, 202):
                results["api_saved"] = len(items_to_save)
            else:
                results["errors"].append(f"API HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            results["errors"].append(f"API POST: {e}")

    # Construir mensaje de respuesta: solo se informa "error" cuando realmente hubo uno
    def _unmatched_lines(limit=10):
        lines = [f"  - {um}" for um in results["unmatched"][:limit]]
        if len(results["unmatched"]) > limit:
            lines.append(f"  ... y {len(results['unmatched']) - limit} más.")
        return lines

    engine_label = "PostgreSQL" if engine == "postgres" else "MySQL"
    already = results.get("already", 0)
    saved_any = results["db_updated"] > 0 or results["db_inserted"] > 0 or results["api_saved"] > 0 or already > 0
    if not saved_any and results["errors"]:
        results["ok"] = False
        msg_parts = ["❌ Falló el registro:"] + [f"  - {e}" for e in results["errors"]]
        if results["unmatched"]:
            msg_parts.append(f"\nAdemás, {len(results['unmatched'])} imagen(es) sin producto coincidente en `{target_table}`:")
            msg_parts += _unmatched_lines()
        results["message"] = "\n".join(msg_parts)
    elif not saved_any and results["unmatched"]:
        results["ok"] = False
        results["message"] = "\n".join(
            [f"⚠️ No se registró ninguna imagen: ninguna coincide con un producto en `{target_table}.{col_code}`.",
             "La conexión a la base de datos funcionó correctamente.", ""]
            + _unmatched_lines()
            + ["", "Nombre la imagen o su carpeta con el código exacto del producto (ej: 36DK0076-1)."]
        )
    elif not saved_any:
        results["ok"] = False
        results["message"] = (
            f"⚠️ No se realizó ningún registro (modo de envío: '{sync_mode}'). "
            "Revise el modo de envío y los datos de conexión en Configuración."
        )
    else:
        msg_parts = [f"✅ Procesamiento completado ({len(items_to_save)} imágenes):"]
        if results["db_updated"] > 0:
            msg_parts.append(f"• Productos actualizados en {engine_label} (`{target_table}.{col_image}`): {results['db_updated']}")
        if already > 0:
            msg_parts.append(f"• Imágenes que el producto ya tenía (no se duplican): {already}")
        if results["db_inserted"] > 0:
            msg_parts.append(f"• Filas insertadas en DB (`{target_table}`): {results['db_inserted']}")
        if results["api_saved"] > 0:
            msg_parts.append(f"• Enviados a Base URL (API): {results['api_saved']}")
        if results["unmatched"]:
            msg_parts.append(f"\n⚠️ {len(results['unmatched'])} imagen(es) sin producto coincidente por código en `{target_table}`:")
            for um in results["unmatched"][:5]:
                msg_parts.append(f"  - {um}")
            if len(results["unmatched"]) > 5:
                msg_parts.append(f"  ... y {len(results['unmatched']) - 5} más.")
        if results["errors"]:
            msg_parts.append("\n⚠️ Advertencias:\n" + "\n".join(results["errors"]))
        results["message"] = "\n".join(msg_parts)

    return results


def sync_from_json_manifest(json_path: str, cfg: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Lee un archivo manifiesto image_map.json existente y actualiza las imágenes
    en la tabla productos (imagenArray) o en la base de datos configurada.
    """
    if not os.path.exists(json_path):
        return {"ok": False, "message": f"No se encontró el archivo: {json_path}"}

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return {"ok": False, "message": "El formato del JSON debe ser una lista de registros."}
        return post_image_records(data, cfg=cfg)
    except Exception as e:
        return {"ok": False, "message": f"Error leyendo archivo JSON:\n{e}"}


# =============================================================================
# POSTGRESQL (getion2import: products.code + products.images TEXT[])
# =============================================================================
PLACEHOLDER_IMAGES = ("imagen_base_productos.png", "blanco.png")


def _safe_error(err: Exception, password: str = "") -> str:
    """Texto del error sin la contraseña (por si el driver la repite)."""
    if isinstance(err, UnicodeDecodeError):
        # en Windows el servidor responde en su idioma (WIN1252) antes de autenticar: casi siempre es usuario o contraseña
        return ("El servidor rechazó la conexión (su mensaje llegó en otra codificación). "
                "Revise usuario, contraseña, base de datos y que el servidor acepte conexiones desde este equipo.")
    text = str(err).strip()
    if password:
        text = text.replace(password, "***")
    return text


def _pg_connect(c: Dict[str, Any]):
    schema = (c.get("schema") or "public").strip() or "public"
    return psycopg2.connect(
        host=c.get("host", "localhost"),
        port=int(c.get("port", 5432)),
        dbname=c.get("database", "postgres"),
        user=c.get("user", "postgres"),
        password=c.get("password", ""),
        connect_timeout=4,
        options=f"-c search_path={schema}",
        application_name="bg_app",
    )


def _pg_columns(cur, schema: str, table: str) -> Dict[str, Dict[str, str]]:
    """Columnas reales de la tabla: nombre exacto -> tipo (data_type, udt_name)."""
    cur.execute(
        "SELECT column_name, data_type, udt_name FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s",
        (schema, table),
    )
    return {r[0]: {"data_type": r[1], "udt_name": r[2]} for r in cur.fetchall()}


def _pg_find_column(columns: Dict[str, Dict[str, str]], wanted: str) -> str:
    """Nombre exacto de la columna (respeta mayúsculas; si no, compara sin distinguirlas)."""
    if wanted in columns:
        return wanted
    for name in columns:
        if name.lower() == wanted.lower():
            return name
    return ""


def _pg_company_id(c: Dict[str, Any]):
    raw = str(c.get("company_id") or "").strip()
    return int(raw) if raw.isdigit() else None


def _pg_test(c: Dict[str, Any]) -> Dict[str, Any]:
    """Prueba la conexión a PostgreSQL: valida tabla y columnas e informa el tipo de la columna de imágenes. No crea nada."""
    if not PSYCOPG2_AVAILABLE:
        return {"ok": False, "message": "El controlador 'psycopg2' no está instalado en Python."}
    host, port, dbname = c.get("host", "localhost"), int(c.get("port", 5432)), c.get("database", "")
    schema = (c.get("schema") or "public").strip() or "public"
    table = (c.get("table") or "products").strip()
    company_id = _pg_company_id(c)
    try:
        conn = _pg_connect(c)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT version();")
                version = cur.fetchone()[0].split(",")[0]
                columns = _pg_columns(cur, schema, table)
                if not columns:
                    return {"ok": False, "message": (
                        f"Conexión correcta a PostgreSQL ({version}), pero la tabla '{schema}.{table}' no existe.\n\n"
                        "Revise el nombre de la tabla en Ajustes (para getion2import: products). No se creó nada.")}
                col_code = _pg_find_column(columns, (c.get("code_column") or "code").strip())
                col_image = _pg_find_column(columns, (c.get("image_column") or "images").strip())
                missing = [n for n, v in (("código", col_code), ("imágenes", col_image)) if not v]
                if missing:
                    return {"ok": False, "message": (
                        f"Conexión correcta a PostgreSQL, pero en '{schema}.{table}' no existe la columna de {' ni la de '.join(missing)}.\n\n"
                        f"Columnas disponibles: {', '.join(sorted(columns))}")}
                img_type = columns[col_image]
                type_label = "arreglo de texto (TEXT[])" if img_type["data_type"] == "ARRAY" else img_type["data_type"]
                where, params = [], []
                if "deleted_at" in columns:
                    where.append("deleted_at IS NULL")
                if company_id is not None and "company_id" in columns:
                    where.append("company_id = %s")
                    params.append(company_id)
                query = sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(schema, table))
                if where:
                    query = query + sql.SQL(" WHERE " + " AND ".join(where))
                cur.execute(query, params)
                count = cur.fetchone()[0]
        finally:
            conn.rollback()
            conn.close()
        company_txt = f"\n• Compañía: {company_id}" if company_id is not None else "\n• Compañía: todas (sin filtro)"
        return {"ok": True, "message": (
            f"Conexión exitosa a PostgreSQL.\n\n"
            f"• Servidor: {version}\n• {host}:{port} / base '{dbname}'\n"
            f"• Tabla: '{schema}.{table}' ({count:,} productos activos){company_txt}\n"
            f"• Columna de código: '{col_code}'\n• Columna de imágenes: '{col_image}' ({type_label})")}
    except Exception as e:
        return {"ok": False, "message": f"Fallo al conectar con PostgreSQL ({host}:{port}/{dbname}):\n{_safe_error(e, c.get('password', ''))}"}


def _merge_images(current, new_path: str):
    """Lista de imágenes sin rellenos y con la ruta nueva al final (sin duplicar). Devuelve (lista, agregada)."""
    if isinstance(current, list):
        arr = [str(x) for x in current if x]
    elif current in (None, ""):
        arr = []
    else:
        try:
            parsed = json.loads(current) if isinstance(current, str) else current
            arr = [str(x) for x in parsed if x] if isinstance(parsed, list) else [str(current)]
        except Exception:
            arr = [str(current)]
    arr = [x for x in arr if not any(ph in x for ph in PLACEHOLDER_IMAGES)]
    if new_path in arr:
        return arr, False
    return arr + [new_path], True


def _pg_update_images(c: Dict[str, Any], items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Agrega la ruta de cada imagen a la columna de imágenes del producto que corresponde a su código.
    Busca por código exacto, luego por códigos alternos (product_codes) y luego por el prefijo más largo.
    Nunca toca productos borrados; con compañía configurada solo busca en ella; un código repetido en varias
    compañías sin compañía configurada no se registra (se informa como ambiguo). Todo va en una transacción.
    """
    schema = (c.get("schema") or "public").strip() or "public"
    table = (c.get("table") or "products").strip()
    out = {"added": 0, "already": 0, "unmatched": [], "ambiguous": []}
    conn = _pg_connect(c)
    try:
        with conn.cursor() as cur:
            columns = _pg_columns(cur, schema, table)
            if not columns:
                raise RuntimeError(f"la tabla '{schema}.{table}' no existe")
            col_code = _pg_find_column(columns, (c.get("code_column") or "code").strip())
            col_image = _pg_find_column(columns, (c.get("image_column") or "images").strip())
            if not col_code or not col_image:
                raise RuntimeError(f"en '{schema}.{table}' faltan las columnas de código o de imágenes")
            is_array = columns[col_image]["data_type"] == "ARRAY"
            has_deleted = "deleted_at" in columns
            has_company = "company_id" in columns
            has_updated = "updated_at" in columns
            company_id = _pg_company_id(c)
            cur.execute("SELECT to_regclass(%s) IS NOT NULL", (f"{schema}.product_codes",))
            has_alt_codes = bool(cur.fetchone()[0]) and has_company

            tbl = sql.Identifier(schema, table)
            code_id, image_id = sql.Identifier(col_code), sql.Identifier(col_image)
            filters, base_params = [], []
            if has_deleted:
                filters.append(sql.SQL("p.deleted_at IS NULL"))
            if company_id is not None and has_company:
                filters.append(sql.SQL("p.company_id = %s"))
                base_params.append(company_id)
            extra = sql.SQL("").join(sql.SQL(" AND ") + f for f in filters)
            company_col = sql.SQL("p.company_id") if has_company else sql.SQL("NULL")

            def find(where_sql, params):
                q = (sql.SQL("SELECT p.id, {comp} FROM {tbl} p WHERE ").format(comp=company_col, tbl=tbl)
                     + where_sql + extra + sql.SQL(" LIMIT 3"))
                cur.execute(q, params + base_params)
                return cur.fetchall()

            for item in items:
                rows, used = [], ""
                for code in item["candidate_codes"]:
                    if not code:
                        continue
                    rows = find(sql.SQL("p.{} = %s").format(code_id), [code])
                    if not rows and has_alt_codes:
                        rows = find(sql.SQL(
                            "p.id IN (SELECT pc.product_id FROM {} pc WHERE pc.code = %s AND pc.company_id = p.company_id)"
                        ).format(sql.Identifier(schema, "product_codes")), [code])
                    if rows:
                        used = code
                        break
                if not rows:
                    stem = os.path.splitext(item["filename"])[0]
                    q = (sql.SQL("SELECT p.id, {comp}, p.{code} FROM {tbl} p WHERE %s LIKE p.{code} || '%%' AND length(p.{code}) > 0").format(
                        comp=company_col, code=code_id, tbl=tbl)
                         + extra + sql.SQL(" ORDER BY length(p.{}) DESC LIMIT 3").format(code_id))
                    cur.execute(q, [stem] + base_params)
                    found = cur.fetchall()
                    if found:
                        longest = len(found[0][2])
                        rows = [(r[0], r[1]) for r in found if len(r[2]) == longest]
                        used = found[0][2]
                if not rows:
                    out["unmatched"].append(f"{item['filename']} (códigos probados: {item['candidate_codes']})")
                    continue
                if len(rows) > 1:
                    out["ambiguous"].append(item["filename"])
                    out["unmatched"].append(f"{item['filename']} (el código {used} existe en varias compañías: configure la compañía en Ajustes)")
                    continue

                product_id = rows[0][0]
                cur.execute(sql.SQL("SELECT {img} FROM {tbl} WHERE id = %s FOR UPDATE").format(img=image_id, tbl=tbl), [product_id])
                current = cur.fetchone()[0]
                merged, added = _merge_images(current, item["gcp_path"])
                original = current if isinstance(current, list) else None
                if not added and original == merged:
                    out["already"] += 1
                    continue
                value = merged if is_array else json.dumps(merged, ensure_ascii=False)
                set_sql = sql.SQL("{img} = %s").format(img=image_id)
                if has_updated:
                    set_sql = set_sql + sql.SQL(", updated_at = CURRENT_TIMESTAMP")
                cur.execute(sql.SQL("UPDATE {tbl} SET ").format(tbl=tbl) + set_sql + sql.SQL(" WHERE id = %s"), [value, product_id])
                if added:
                    out["added"] += 1
                else:
                    out["already"] += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return out
