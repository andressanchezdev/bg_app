import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

def main():
    print("=" * 60)
    print("DIAGNÓSTICO COMPLETO DE INTEGRACIÓN GOOGLE CLOUD STORAGE")
    print("=" * 60)

    # 1. Comprobar archivo de credenciales
    key_candidates = [
        os.path.join(os.getcwd(), "credentials", "gcp_key.json"),
        os.path.join(os.path.expanduser("~"), "Desktop", "gcp_key.json"),
        os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    ]

    key_found = None
    for p in key_candidates:
        if p and os.path.exists(p):
            key_found = p
            break

    print(f"\n[1] Archivo de Credenciales:")
    if not key_found:
        print("  ❌ ERROR: No se encontró el archivo gcp_key.json.")
        print(f"     Buscado en: {key_candidates}")
        return
    else:
        print(f"  ✅ Archivo detectado: {key_found}")

    # 2. Validar sintaxis y firma del JSON
    try:
        from google.oauth2 import service_account
        creds = service_account.Credentials.from_service_account_file(key_found)
        print(f"  ✅ Credencial válida:")
        print(f"     • Proyecto: {creds.project_id}")
        print(f"     • Email SA: {creds.service_account_email}")
    except Exception as e:
        print(f"  ❌ Error al leer credenciales: {e}")
        return

    # 3. Validar Bucket y variables
    import config
    bucket_name = getattr(config, "GCS_BUCKET_NAME", "importadorapremiumonline")
    base_folder = getattr(config, "GCS_BASE_FOLDER", "dependencias/img/productos/")
    print(f"\n[2] Configuración de Destino:")
    print(f"  • Bucket: '{bucket_name}'")
    print(f"  • Ruta base: '{base_folder}'")

    # 4. Probar conexión y permisos con el SDK
    print(f"\n[3] Conexión y Permisos en GCP:")
    try:
        from google.cloud import storage
        client = storage.Client.from_service_account_json(key_found)
        bucket = client.get_bucket(bucket_name)
        print(f"  ✅ Bucket '{bucket_name}' encontrado en región: {bucket.location}")

        # Listar carpetas existentes en base_folder
        prefix = base_folder.strip("/")
        if prefix:
            prefix += "/"
        
        print(f"\n[4] Explorando carpetas bajo '{prefix}':")
        blobs = bucket.list_blobs(prefix=prefix, delimiter="/")
        
        folders = set()
        for b in blobs:
            if b.name.endswith("/"):
                sub = b.name[len(prefix):].strip("/")
                if sub:
                    folders.add(sub)
        for p in blobs.prefixes:
            sub = p[len(prefix):].strip("/")
            if sub:
                folders.add(sub)

        folder_list = sorted(list(folders))
        if folder_list:
            print(f"  ✅ Carpetas existentes detectadas ({len(folder_list)}):")
            for f in folder_list:
                print(f"     📁 {f}/")
        else:
            print(f"  ⚠️ No hay subcarpetas bajo '{prefix}'.")

        # 5. Probar permiso de escritura con archivo de prueba
        test_blob_name = f"{prefix}_test_connectivity.tmp"
        print(f"\n[5] Probando permiso de escritura:")
        blob = bucket.blob(test_blob_name)
        blob.upload_from_string(b"test", content_type="text/plain")
        print(f"  ✅ Permiso de escritura CONFIRMADO (Storage Object Admin / Creator)")
        # Borrar prueba
        blob.delete()
        print(f"  ✅ Archivo temporal de prueba eliminado.")

        print("\n" + "=" * 60)
        print("RESULTADO: TODO EL SDK Y PERMISOS ESTÁN 100% OPERATIVOS")
        print("=" * 60)

    except Exception as e:
        print(f"  ❌ Fallo de conexión o permisos con GCP:")
        print(f"     Detalle: {e}")

if __name__ == "__main__":
    main()
