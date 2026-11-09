import os
import sys
import json
import requests
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Union

try:
    import pymysql
    from pymysql.constants import CLIENT
    PYMYSQL_AVAILABLE = True
except ImportError:
    pymysql = None
    PYMYSQL_AVAILABLE = False

try:
    import psycopg2
    from psycopg2 import sql
    from psycopg2.extras import RealDictCursor
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
        "sync_mode": getattr(config, "DB_SYNC_MODE", "db")  # db, api, both
    }


def is_mysql_port(port: int) -> bool:
    """Identifica si el puerto corresponde usualmente a MySQL / MariaDB (3306, 3307, etc.)."""
    return port in (3306, 3307, 3308)


def extract_gcp_relative_path(item: dict) -> str:
    """
    Extrae la ruta relativa estándar para el catálogo (ej: dependencias/img/productos/{codigo}/{archivo}.webp)
    a partir del cloud_url o de las rutas relativas.
    """
    cloud_url = item.get("cloud_url", "")
    if cloud_url and "dependencias/" in cloud_url:
        unquoted = urllib.parse.unquote(cloud_url)
        idx = unquoted.find("dependencias/")
        if idx != -1:
            return unquoted[idx:].replace("\\", "/")

    subfolder = item.get("folder_name", "").strip().strip("/\\")
    fname = (item.get("uploaded_filename") or item.get("filename", "")).strip()
    stem = Path(fname).stem
    webp_name = f"{stem}.webp" if not fname.lower().endswith(".webp") else fname
    if subfolder:
        return f"dependencias/img/productos/{subfolder}/{webp_name}".replace("\\", "/")
    return f"dependencias/img/productos/{webp_name}".replace("\\", "/")


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

    # 1. Conexión MySQL / MariaDB (HeidiSQL)
    if is_mysql_port(port) or PYMYSQL_AVAILABLE:
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

    # 2. Conexión PostgreSQL (fallback si es puerto 5432)
    if PSYCOPG2_AVAILABLE:
        try:
            conn = psycopg2.connect(
                host=host,
                port=port,
                dbname=dbname,
                user=user,
                password=password,
                connect_timeout=4
            )
            with conn.cursor() as cur:
                cur.execute(f"""
                CREATE TABLE IF NOT EXISTS "{target_table}" (
                    id SERIAL PRIMARY KEY,
                    filename VARCHAR(255),
                    folder_name VARCHAR(255),
                    relative_path TEXT,
                    processed_path TEXT,
                    cloud_url TEXT,
                    status VARCHAR(50) DEFAULT 'PROCESADA',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """)
                conn.commit()
                cur.execute(f"SELECT COUNT(*) FROM \"{target_table}\";")
                count = cur.fetchone()[0]
            conn.close()
            return {
                "ok": True,
                "message": f"Conexión exitosa a PostgreSQL.\n• Base de datos: '{dbname}'\n• Tabla: '{target_table}' ({count} registros)"
            }
        except Exception as e:
            return {
                "ok": False,
                "message": f"Fallo al conectar con PostgreSQL ({host}:{port}/{dbname}):\n{e}"
            }

    return {"ok": False, "message": "No se encontró ningún controlador compatible (pymysql o psycopg2)."}


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
    if sync_mode in ("db", "both") and is_mysql_port(port) and PYMYSQL_AVAILABLE:
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
    # 2. PROCESAMIENTO EN BASE DE DATOS (PostgreSQL Fallback en 5432)
    # -----------------------------------------------------------------
    elif sync_mode in ("db", "both") and not is_mysql_port(port) and PSYCOPG2_AVAILABLE:
        try:
            conn = psycopg2.connect(
                host=host,
                port=port,
                dbname=dbname,
                user=user,
                password=password,
                connect_timeout=4
            )
            with conn.cursor() as cur:
                insert_sql = f"""
                INSERT INTO "{target_table}" (
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
                conn.commit()
            conn.close()
            results["db_inserted"] = len(items_to_save)
        except Exception as e:
            results["errors"].append(f"PostgreSQL: {e}")

    # -----------------------------------------------------------------
    # 3. ENVÍO HTTP POST AL ENDPOINT API (Base URL)
    # -----------------------------------------------------------------
    if (sync_mode in ("api", "both") or endpoint_url) and endpoint_url:
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

    # Construir mensaje de respuesta
    if results["errors"] and results["db_updated"] == 0 and results["db_inserted"] == 0 and results["api_saved"] == 0:
        results["ok"] = False
        results["message"] = "Falló el registro en base de datos:\n" + "\n".join(results["errors"])
    else:
        msg_parts = [f"✅ Procesamiento completado ({len(items_to_save)} imágenes):"]
        if results["db_updated"] > 0:
            msg_parts.append(f"• Productos actualizados en MySQL (`{target_table}.imagenArray`): {results['db_updated']}")
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
