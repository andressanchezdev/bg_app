import os
import sys
from pathlib import Path
from PIL import Image

sys.path.insert(0, os.path.abspath("."))
import config
from core.bg_remover import get_ai_session, process_remove_background
from core.image_processor import export_to_webp
from services.cloud_storage import CloudStorageService

def test_full_pipeline():
    print("=== TEST COMPLETO: PROCESAMIENTO IA + RENDERIZADO WEBP + SUBIDA GCP ===")
    
    # Rutas de prueba
    input_suelta = r"C:\Users\Usuario\Downloads\imagenes\pruebaimg.jpeg"
    input_otras = r"C:\Users\Usuario\Downloads\imagenes\otras\pruebaimg.jpeg"
    
    out_dir = Path("output/processed_test")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Cargar modelo IA offline (U2-Net)
    print("\n1. Inicializando sesión de IA U2-Net...")
    ai_session = get_ai_session()
    print("   IA inicializada con éxito.")
    
    # 2. Inicializar servicio GCP
    svc = CloudStorageService(
        bucket_name="importadorapremiumonline",
        credentials_path=config.GCS_CREDENTIALS_PATH,
        base_folder="dependencias/img/productos/"
    )
    
    # =========================================================================
    # CASO 1: Procesar imagen suelta con fondo transparente
    # =========================================================================
    print(f"\n2. Procesando imagen suelta: {input_suelta}")
    raw_suelta = Image.open(input_suelta)
    print("   Aislando objeto con IA (eliminando fondo)...")
    cutout_suelta = process_remove_background(raw_suelta, session=ai_session)
    
    local_webp_suelta = out_dir / "pruebaimg_ia.webp"
    export_to_webp(
        pil_image=cutout_suelta,
        output_path=str(local_webp_suelta),
        quality=90,
        white_bg=False,
        resize_config={"enabled": True, "width": 900, "height": 900, "mode": "contain"}
    )
    print(f"   Exportado localmente a WebP: {local_webp_suelta} ({os.path.getsize(local_webp_suelta)} bytes)")
    
    print("   Subiendo a GCP en dependencias/img/productos/...")
    url_suelta = svc.upload_file(
        file_path=str(local_webp_suelta),
        destination_blob_name="pruebaimg_ia.webp",
        subfolder="",  # Imagen suelta directa en dependencias/img/productos/
        make_public=True
    )
    print(f"   URL generada: {url_suelta}")
    
    # =========================================================================
    # CASO 2: Procesar imagen dentro de carpeta 'otras' con fondo blanco
    # =========================================================================
    print(f"\n3. Procesando imagen en carpeta 'otras': {input_otras}")
    raw_otras = Image.open(input_otras)
    print("   Aislando objeto con IA...")
    cutout_otras = process_remove_background(raw_otras, session=ai_session)
    
    local_webp_otras = out_dir / "pruebaimg_otras_blanco.webp"
    export_to_webp(
        pil_image=cutout_otras,
        output_path=str(local_webp_otras),
        quality=90,
        white_bg=True,
        resize_config={"enabled": True, "width": 900, "height": 900, "mode": "contain"}
    )
    print(f"   Exportado localmente a WebP (fondo blanco): {local_webp_otras} ({os.path.getsize(local_webp_otras)} bytes)")
    
    print("   Subiendo a GCP bajo subcarpeta 'otras/'...")
    url_otras = svc.upload_file(
        file_path=str(local_webp_otras),
        destination_blob_name="pruebaimg_otras_blanco.webp",
        subfolder="otras",
        make_public=True
    )
    print(f"   URL generada: {url_otras}")
    
    print("\n=== VALIDACIÓN COMPLETA FINALIZADA CON ÉXITO ===")

if __name__ == "__main__":
    test_full_pipeline()

