import os
import sys
import json
import requests
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Union

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
        "port": int(getattr(config, "DB_PORT", os.getenv("DB_PORT", "5432"))),
        "database": getattr(config, "DB_DATABASE", os.getenv("DB_DATABASE", "Images")),
        "user": getattr(config, "DB_USER", os.getenv("DB_USER", "postgres")),
        "password": getattr(config, "DB_PASSWORD", os.getenv("DB_PASSWORD", "password_123")),
        "table": getattr(config, "DB_TABLE", "images"),
        "api_endpoint": getattr(config, "DB_API_ENDPOINT", ""),
        "sync_mode": getattr(config, "DB_SYNC_MODE", "postgres")  # postgres, api, both
    }


def test_db_connection(cfg: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Prueba la conexión a PostgreSQL con los parámetros proporcionados o configurados.
    Verifica que la base de datos exista y crea la tabla si no está presente.
    """
    if not PSYCOPG2_AVAILABLE:
        return {"ok": False, "message": "El controlador 'psycopg2' no está instalado en el entorno de Python."}

    c = cfg or get_db_config()
    host = c.get("host", "localhost")
    port = int(c.get("port", 5432))
    dbname = c.get("database", "Images")
    user = c.get("user", "postgres")
    password = c.get("password", "")
    target_table = c.get("table", "images").strip() or "images"

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
            # Asegurar tabla para el almacenamiento de URLs
            create_tbl_sql = f"""
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
            """
            cur.execute(create_tbl_sql)
            conn.commit()

            cur.execute(f"SELECT COUNT(*) FROM \"{target_table}\";")
            count = cur.fetchone()[0]

        conn.close()
        return {
            "ok": True,
            "message": f"Conexión exitosa a PostgreSQL.\n• Base de datos: '{dbname}'\n• Tabla: '{target_table}' ({count} registros existentes)"
        }
    except Exception as e:
        err_msg = str(e)
        if isinstance(e, UnicodeDecodeError):
            err_msg = "Error de codificación al recibir respuesta del servidor PostgreSQL. Verifica el nombre de la base de datos."
        return {
            "ok": False,
            "message": f"Fallo al conectar con PostgreSQL ({host}:{port}/{dbname}):\n{err_msg}"
        }


def test_api_endpoint(endpoint_url: str = None) -> Dict[str, Any]:
    """
    Prueba el envío de un payload POST mínimo al Endpoint REST API.
    """
    url = (endpoint_url or get_db_config().get("api_endpoint", "")).strip()
    if not url:
        return {"ok": False, "message": "No se ha configurado ninguna URL de Endpoint API."}

    sample_payload = {
        "ping": True,
        "test": True,
        "timestamp": datetime.now().isoformat(),
        "total": 1,
        "items": [
            {
                "filename": "test_ping.webp",
                "folder_name": "test",
                "cloud_url": "https://storage.googleapis.com/test_ping.webp",
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
    Método adaptable para registrar las URLs de imágenes procesadas.
    Soporta recibir un solo diccionario o una lista de varios diccionarios.
    Ejecuta el registro en PostgreSQL y/o envía la petición HTTP POST al Endpoint.
    """
    c = cfg or get_db_config()
    sync_mode = c.get("sync_mode", "postgres")
    endpoint_url = c.get("api_endpoint", "").strip()

    # Normalizar a lista
    if isinstance(records, dict):
        raw_list = [records]
    elif isinstance(records, list):
        raw_list = records
    else:
        return {"ok": False, "message": "Formato de datos no válido para registro."}

    # Filtrar y formatear solo elementos válidos
    items_to_save = []
    for item in raw_list:
        fname = item.get("filename") or os.path.basename(item.get("processed_path", "") or item.get("relative_path", ""))
        c_url = item.get("cloud_url", "")
        if not fname:
            continue
        orig_p = item.get("original_path") or item.get("absolute_path") or item.get("processed_path") or ""
        proc_p = item.get("processed_path", "") or ""
        items_to_save.append({
            "filename": fname,
            "folder_name": item.get("folder_name", "") or "",
            "relative_path": item.get("relative_path", "") or "",
            "original_path": orig_p,
            "processed_path": proc_p,
            "cloud_url": c_url,
            "format": "WEBP",
            "status": "PROCESADA" if c_url else "PENDIENTE_GCP",
            "processed_at": datetime.now().isoformat()
        })

    if not items_to_save:
        return {"ok": False, "message": "No hay imágenes para registrar (lista vacía)."}

    results = {
        "ok": True,
        "total_items": len(items_to_save),
        "db_saved": 0,
        "api_saved": 0,
        "errors": []
    }

    # 1. Registro en PostgreSQL
    if sync_mode in ("postgres", "both") and PSYCOPG2_AVAILABLE:
        host = c.get("host", "localhost")
        port = int(c.get("port", 5432))
        dbname = c.get("database", "Images")
        user = c.get("user", "postgres")
        password = c.get("password", "")
        target_table = c.get("table", "images").strip() or "images"

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
                # Asegurar tabla existente
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

                # Inserción de cada registro con columnas estándar
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
            results["db_saved"] = len(items_to_save)
        except Exception as e:
            results["errors"].append(f"PostgreSQL: {e}")

    # 2. Envío HTTP POST al Endpoint API (adaptable a 1 solo archivo o lista)
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

    if results["errors"] and results["db_saved"] == 0 and results["api_saved"] == 0:
        results["ok"] = False
        results["message"] = "Fallaron todos los métodos de registro:\n" + "\n".join(results["errors"])
    else:
        msg_parts = [f"✅ {len(items_to_save)} registro(s) procesados."]
        if results["db_saved"] > 0:
            msg_parts.append(f"• Guardados en PostgreSQL ({c.get('table', 'images')}): {results['db_saved']}")
        if results["api_saved"] > 0:
            msg_parts.append(f"• Enviados a Endpoint API: {results['api_saved']}")
        if results["errors"]:
            msg_parts.append("\n⚠️ Advertencias parciales:\n" + "\n".join(results["errors"]))
        results["message"] = "\n".join(msg_parts)

    return results


def sync_from_json_manifest(json_path: str, cfg: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Lee un archivo manifiesto image_map.json existente y envía todos
    sus registros a la base de datos o Endpoint API.
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
