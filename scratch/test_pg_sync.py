# test_pg_sync · prueba sin interfaz de la integración de bg_app con PostgreSQL (getion2import)
# uso: python scratch/test_pg_sync.py  (variables PG_HOST, PG_PORT, PG_DB, PG_USER, PG_PASSWORD; por defecto importadora_test local)
# ojo: escribe en la base indicada y al final deja las imágenes de los productos tocados como estaban; nunca usarlo contra producción
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from services import db_service  # noqa: E402
import psycopg2  # noqa: E402

CFG = {
    "engine": "postgres",
    "host": os.getenv("PG_HOST", "localhost"),
    "port": int(os.getenv("PG_PORT", "5432")),
    "database": os.getenv("PG_DB", "importadora_test"),
    "user": os.getenv("PG_USER", "postgres"),
    "password": os.getenv("PG_PASSWORD", ""),
    "schema": "public",
    "table": "products",
    "code_column": "code",
    "image_column": "images",
    "company_id": "",
    "sync_mode": "db",
    "api_endpoint": "",
}
ok = fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print("  ✓", name)
    else:
        fail += 1
        print("  ✗", name, extra)


def conn():
    return psycopg2.connect(host=CFG["host"], port=CFG["port"], dbname=CFG["database"], user=CFG["user"], password=CFG["password"])


def images_of(pid):
    with conn() as c, c.cursor() as cur:
        cur.execute("SELECT images FROM products WHERE id = %s", (pid,))
        return cur.fetchone()[0]


def set_images(pid, value):
    with conn() as c, c.cursor() as cur:
        cur.execute("UPDATE products SET images = %s WHERE id = %s", (value, pid))


def record(code, filename, folder=None):
    folder = folder if folder is not None else code
    base = config.GCS_BASE_FOLDER.strip("/")
    return {"filename": filename, "folder_name": folder,
            "cloud_url": f"{config.public_base_url()}{base}/{folder}/{filename}", "processed_path": filename}


with conn() as c, c.cursor() as cur:
    cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
    tables_before = cur.fetchone()[0]
    cur.execute("SELECT id, code, company_id, images FROM products WHERE deleted_at IS NULL ORDER BY id LIMIT 2")
    (p1, code1, comp1, img1), (p2, code2, comp2, img2) = cur.fetchall()
    cur.execute("SELECT pc.product_id, pc.code FROM product_codes pc JOIN products p ON p.id = pc.product_id "
                "WHERE p.deleted_at IS NULL AND pc.code <> p.code LIMIT 1")
    alt = cur.fetchone()
    alt_img = images_of(alt[0]) if alt else None

print("== Prueba de conexión")
res = db_service.test_db_connection(CFG)
check("conecta por PostgreSQL aunque pymysql esté instalado", res["ok"] and "PostgreSQL" in res["message"], res["message"])
check("informa la columna de imágenes como TEXT[]", "TEXT[]" in res["message"], res["message"])
bad = dict(CFG, table="productos_que_no_existen")
res = db_service.test_db_connection(bad)
check("tabla inexistente: avisa y no la crea", not res["ok"] and "no existe" in res["message"], res["message"])
with conn() as c, c.cursor() as cur:
    cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
    check("no se creó ninguna tabla", cur.fetchone()[0] == tables_before)

try:
    print("== Registro de imágenes")
    set_images(p1, [])
    r = db_service.post_image_records([record(code1, f"{code1}.webp")], cfg=CFG)
    path1 = f"{config.GCS_BASE_FOLDER.strip('/')}/{code1}/{code1}.webp"
    check("primera imagen agregada", r["ok"] and images_of(p1) == [path1], (r["message"], images_of(p1)))
    r = db_service.post_image_records([record(code1, f"{code1}-2.webp")], cfg=CFG)
    path2 = f"{config.GCS_BASE_FOLDER.strip('/')}/{code1}/{code1}-2.webp"
    check("segunda imagen al final (la primera sigue principal)", images_of(p1) == [path1, path2], images_of(p1))
    r = db_service.post_image_records([record(code1, f"{code1}.webp")], cfg=CFG)
    check("repetir no duplica", images_of(p1) == [path1, path2] and r["ok"], (r["message"], images_of(p1)))
    set_images(p1, ["dependencias/img/blanco.png"])
    db_service.post_image_records([record(code1, f"{code1}.webp")], cfg=CFG)
    check("quita la imagen de relleno", images_of(p1) == [path1], images_of(p1))
    r = db_service.post_image_records([record("NO-EXISTE-999", "NO-EXISTE-999.webp")], cfg=CFG)
    check("código inexistente: sin coincidencia", not r["ok"] and "NO-EXISTE-999" in r["message"], r["message"])
    r = db_service.post_image_records([record(code2, f"{code2}.webp")], cfg=dict(CFG, company_id=str(comp2 + 9999)))
    check("con otra compañía no toca el producto", images_of(p2) == img2, images_of(p2))
    if alt:
        set_images(alt[0], [])
        db_service.post_image_records([record(alt[1], f"{alt[1]}.webp")], cfg=CFG)
        check("encuentra el producto por su código alterno", len(images_of(alt[0])) == 1, images_of(alt[0]))
    print("== Ruta de consumo")
    rel = db_service.extract_gcp_relative_path(record(code1, f"{code1}.webp"))
    check("la ruta guardada es el nombre del objeto en el bucket", rel == path1, rel)
finally:
    set_images(p1, img1)
    set_images(p2, img2)
    if alt:
        set_images(alt[0], alt_img)

print(f"\nRESULTADO bg_app PostgreSQL: {ok} ok, {fail} fallas")
