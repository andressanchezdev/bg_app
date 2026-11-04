import os
import sys
from pathlib import Path
from PIL import Image

# Agregar directorio del proyecto
sys.path.insert(0, os.path.abspath("."))
import config
from services.cloud_storage import CloudStorageService

def main():
    img_suelta = r"C:\Users\Usuario\Downloads\imagenes\pruebaimg.jpeg"
    carpeta_otras = r"C:\Users\Usuario\Downloads\imagenes\otras"
    img_en_otras = os.path.join(carpeta_otras, "pruebaimg.jpeg")

    print("=== INICIANDO PRUEBA DE SUBIDA A GOOGLE CLOUD STORAGE ===")
    print(f"1. Imagen suelta: {img_suelta} (Existe: {os.path.exists(img_suelta)})")
    print(f"2. Imagen en carpeta 'otras': {img_en_otras} (Existe: {os.path.exists(img_en_otras)})")

    # Inicializar servicio GCP
    svc = CloudStorageService(
        bucket_name="importadorapremiumonline",
        credentials_path=config.GCS_CREDENTIALS_PATH,
        base_folder="dependencias/img/productos/"
    )
    bucket = svc.client.bucket("importadorapremiumonline")

    # Preparar versión WebP local
    out_dir = Path("output/pruebas_gcp")
    out_dir.mkdir(parents=True, exist_ok=True)
    webp_suelta = out_dir / "pruebaimg.webp"
    
    # Convertir a WebP
    pil_img = Image.open(img_suelta).convert("RGB")
    pil_img.save(webp_suelta, "WEBP", quality=90)
    print(f"WebP generado localmente: {webp_suelta} ({os.path.getsize(webp_suelta)} bytes)")

    # -------------------------------------------------------------
    # PRUEBA A: Subir imagen suelta
    # -------------------------------------------------------------
    # Caso A1: En la ruta de productos configurada
    dest_a1 = "dependencias/img/productos/pruebaimg.webp"
    blob_a1 = bucket.blob(dest_a1)
    blob_a1.upload_from_filename(str(webp_suelta), content_type="image/webp")
    try:
        blob_a1.make_public()
    except Exception:
        pass
    url_a1 = f"https://storage.googleapis.com/importadorapremiumonline/{dest_a1}"

    # Caso A2: En la raíz absoluta del bucket
    dest_a2 = "pruebaimg.webp"
    blob_a2 = bucket.blob(dest_a2)
    blob_a2.upload_from_filename(str(webp_suelta), content_type="image/webp")
    try:
        blob_a2.make_public()
    except Exception:
        pass
    url_a2 = f"https://storage.googleapis.com/importadorapremiumonline/{dest_a2}"

    print("\n--- RESULTADO IMAGEN SUELTA ---")
    print(f"[Ruta Base App]: {dest_a1}")
    print(f"URL: {url_a1}")
    print(f"[Raíz Bucket]: {dest_a2}")
    print(f"URL: {url_a2}")

    # -------------------------------------------------------------
    # PRUEBA B: Subir con carpeta 'otras'
    # -------------------------------------------------------------
    # Caso B1: En la ruta de productos bajo 'otras/'
    dest_b1 = "dependencias/img/productos/otras/pruebaimg.webp"
    blob_b1 = bucket.blob(dest_b1)
    blob_b1.upload_from_filename(str(webp_suelta), content_type="image/webp")
    try:
        blob_b1.make_public()
    except Exception:
        pass
    url_b1 = f"https://storage.googleapis.com/importadorapremiumonline/{dest_b1}"

    # Caso B2: En la raíz bajo 'otras/'
    dest_b2 = "otras/pruebaimg.webp"
    blob_b2 = bucket.blob(dest_b2)
    blob_b2.upload_from_filename(str(webp_suelta), content_type="image/webp")
    try:
        blob_b2.make_public()
    except Exception:
        pass
    url_b2 = f"https://storage.googleapis.com/importadorapremiumonline/{dest_b2}"

    print("\n--- RESULTADO CON CARPETA 'otras/' ---")
    print(f"[Ruta Base App]: {dest_b1}")
    print(f"URL: {url_b1}")
    print(f"[Raíz Bucket]: {dest_b2}")
    print(f"URL: {url_b2}")

    print("\n=== PRUEBA DE SUBIDA COMPLETADA EXITOSAMENTE ===")

if __name__ == "__main__":
    main()

