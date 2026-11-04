import os

path = "ui/tab_batch.py"
with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    if "upload_to_cloud=upload_to_cloud," in line:
        new_lines.append("                upload_to_cloud=can_upload_item,\n")
    elif "cloud_service=self.cloud_service if upload_to_cloud else None" in line:
        new_lines.append("                cloud_service=self.cloud_service if can_upload_item else None,\n")
        new_lines.append("                target_subfolder=target_subfolder\n")
    elif "for fpath in self.batch_file_list:" in line:
        # Prepend existing_folders validation
        val_block = (
            "        existing_folders = []\n"
            "        if upload_to_cloud and self.cloud_service:\n"
            "            conn = self.cloud_service.test_connection()\n"
            "            if conn.get('ok'):\n"
            "                existing_folders = self.cloud_service.get_existing_folders()\n"
            "            else:\n"
            "                QMessageBox.warning(self, 'Aviso GCP', conn.get('message', ''))\n"
            "                upload_to_cloud = False\n\n"
            "        for fpath in self.batch_file_list:\n"
        )
        new_lines.append(val_block)
    elif "os.makedirs(target_dir, exist_ok=True)" in line:
        new_lines.append(line)
        target_block = (
            "\n            target_subfolder = ''\n"
            "            can_upload_item = False\n"
            "            if upload_to_cloud and self.cloud_service:\n"
            "                val = self.cloud_service.validate_image_target(folder_name, rec.get('filename', ''), existing_folders)\n"
            "                if val.get('valid'):\n"
            "                    target_subfolder = val.get('target_subfolder', '')\n"
            "                    can_upload_item = True\n"
        )
        new_lines.append(target_block)
    else:
        new_lines.append(line)

with open(path, "w", encoding="utf-8") as f:
    f.writelines(new_lines)
print("Updated tab_batch.py successfully")

