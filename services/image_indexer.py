import os
import json
from pathlib import Path
from typing import List, Dict, Any

VALID_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


class ImageIndexer:
    @staticmethod
    def scan_folder(root_folder_path: str) -> List[Dict[str, Any]]:
        """
        Recorre recursivamente una carpeta y retorna la lista de imágenes mapeadas.
        """
        root_path = Path(root_folder_path).resolve()
        image_records = []

        if not root_path.exists() or not root_path.is_dir():
            raise ValueError(f"La ruta especificada no es una carpeta válida: {root_folder_path}")

        for file_path in root_path.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in VALID_EXTENSIONS:
                folder_name = file_path.parent.name
                
                try:
                    rel_path = str(file_path.relative_to(root_path))
                except ValueError:
                    rel_path = file_path.name

                image_records.append({
                    "folder_name": folder_name,
                    "filename": file_path.name,
                    "relative_path": rel_path,
                    "absolute_path": str(file_path),
                    "processed_path": None,
                    "processed": False,
                    "cloud_url": None
                })

        return image_records

    @staticmethod
    def save_to_json(data: List[Dict[str, Any]], output_json_path: str = "output/image_map.json") -> str:
        """
        Guarda la lista de registros mapeados en un archivo JSON.
        """
        out_path = Path(output_json_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return str(out_path.resolve())

    @staticmethod
    def update_json_record(
        json_path: str,
        absolute_path: str,
        processed_path: str = None,
        gcp_url: str = None,
        cloud_url: str = None,
        processed: bool = True
    ):
        """
        Actualiza el estado del JSON cuando una imagen sea procesada o subida a GCP.
        Soporta los argumentos 'gcp_url' y 'cloud_url' por compatibilidad.
        """
        path = Path(json_path)
        if not path.exists():
            return

        final_cloud_url = gcp_url or cloud_url

        with open(path, "r", encoding="utf-8") as f:
            records = json.load(f)

        for item in records:
            if item.get("absolute_path") == absolute_path:
                item["processed"] = processed
                if processed_path:
                    item["processed_path"] = processed_path
                if final_cloud_url:
                    item["cloud_url"] = final_cloud_url
                break

        with open(path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)