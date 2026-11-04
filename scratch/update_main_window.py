import os

path = "ui/main_window.py"
with open(path, "r", encoding="utf-8") as f:
    text = f.read()

# Fix 1: improve credentials resolution and alerting in batch start
old_cred_block = """        if upload_to_gcs:
            gcp_key = getattr(config, "GCS_CREDENTIALS_PATH", os.path.join(os.getcwd(), "credentials", "gcp_key.json"))
            if not os.path.exists(gcp_key):
                candidate = os.path.join(os.path.dirname(sys.executable), "credentials", "gcp_key.json")
                if os.path.exists(candidate):
                    gcp_key = candidate

            bucket_name = getattr(config, "GCS_BUCKET_NAME", "importadorapremiumonline")
            base_folder = getattr(config, "GCS_BASE_FOLDER", "dependencias/img/productos/")

            if os.path.exists(gcp_key) and bucket_name:
                gcp_service = CloudStorageService(
                    bucket_name=bucket_name,
                    credentials_path=gcp_key,
                    base_folder=base_folder
                )
                conn = gcp_service.test_connection()
                if conn["ok"]:
                    existing_folders = gcp_service.get_existing_folders()
                else:
                    upload_to_gcs = False
                    gcp_service = None
            else:
                upload_to_gcs = False"""

new_cred_block = """        if upload_to_gcs:
            gcp_key = getattr(config, "GCS_CREDENTIALS_PATH", "")
            if not gcp_key or not os.path.exists(gcp_key):
                gcp_key = config.resolve_credentials_path()

            bucket_name = getattr(config, "GCS_BUCKET_NAME", "importadorapremiumonline")
            base_folder = getattr(config, "GCS_BASE_FOLDER", "dependencias/img/productos/")

            if os.path.exists(gcp_key) and bucket_name:
                gcp_service = CloudStorageService(
                    bucket_name=bucket_name,
                    credentials_path=gcp_key,
                    base_folder=base_folder
                )
                conn = gcp_service.test_connection()
                if conn["ok"]:
                    existing_folders = gcp_service.get_existing_folders()
                else:
                    QMessageBox.warning(self, "Error de Conexión GCP", f"No se pudo conectar a Google Cloud Storage:\\n\\n{conn.get('message', '')}\\n\\nLas imágenes se procesarán únicamente de forma local.")
                    upload_to_gcs = False
                    gcp_service = None
            else:
                QMessageBox.warning(self, "Credenciales no encontradas", "No se encontró el archivo 'gcp_key.json' de Google Cloud Storage.\\n\\nVerifica que esté en tu Escritorio o en la carpeta 'credentials/'.\\nLas imágenes se procesarán únicamente de forma local.")
                upload_to_gcs = False"""

# Fix 2: avoid joining 4,870 folders into QMessageBox
old_join_1 = "f\"{', '.join(rejected_folders)}\\n\\n\""
new_join_1 = "f\"{(', '.join(list(rejected_folders)[:15]) + '... (' + str(len(rejected_folders)) + ' en total)') if len(rejected_folders) > 15 else ', '.join(rejected_folders)}\\n\\n\""

old_join_2 = "f\"Carpetas disponibles en el bucket: {', '.join(existing_folders) if existing_folders else '(Ninguna carpeta creada)'}\""
new_join_2 = "f\"Total carpetas registradas en GCP: {len(existing_folders)} (ej: {', '.join(existing_folders[:6])}...)\""

if old_cred_block in text:
    text = text.replace(old_cred_block, new_cred_block, 1)
    print("Replaced cred block successfully")
else:
    print("WARNING: old_cred_block not found")

if old_join_1 in text:
    text = text.replace(old_join_1, new_join_1, 1)
    print("Replaced join 1 successfully")
else:
    print("WARNING: old_join_1 not found")

if old_join_2 in text:
    text = text.replace(old_join_2, new_join_2, 1)
    print("Replaced join 2 successfully")
else:
    print("WARNING: old_join_2 not found")

with open(path, "w", encoding="utf-8") as f:
    f.write(text)

print("Updated main_window.py successfully")

