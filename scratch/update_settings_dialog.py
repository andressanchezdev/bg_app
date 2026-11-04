with open("ui/dialog_settings.py", "r", encoding="utf-8") as f:
    text = f.read()

target = """            # Consultar carpetas existentes
            folders = gcp_service.get_existing_folders()
            if folders:
                folder_list_str = "\\n".join([f"📁 {f}/" for f in folders])
                self.txt_folders_preview.setText(
                    f"Carpetas detectadas en '{folder_val}':\\n{folder_list_str}"
                )
            else:
                self.txt_folders_preview.setText(
                    f"Conexión exitosa. No se encontraron subcarpetas bajo '{folder_val}'.\\n"
                    "Las imágenes sueltas se alojarán directamente en la raíz de esta ruta."
                )"""

replacement = """            # Consultar carpetas existentes
            folders = gcp_service.get_existing_folders()
            if folders:
                limit = 50
                preview_list = folders[:limit]
                folder_list_str = "\\n".join([f"📁 {f}/" for f in preview_list])
                more_txt = f"\\n... y {len(folders) - limit} carpetas más." if len(folders) > limit else ""
                self.txt_folders_preview.setText(
                    f"Carpetas detectadas en '{folder_val}' (Total: {len(folders)}):\\n{folder_list_str}{more_txt}"
                )
            else:
                self.txt_folders_preview.setText(
                    f"Conexión exitosa. No se encontraron subcarpetas bajo '{folder_val}'.\\n"
                    "Por política de catálogo, ninguna imagen se almacenará en la raíz sin carpeta."
                )"""

if target in text:
    text = text.replace(target, replacement, 1)
    with open("ui/dialog_settings.py", "w", encoding="utf-8") as f:
        f.write(text)
    print("SettingsDialog preview updated successfully")
else:
    print("WARNING: target not found")

