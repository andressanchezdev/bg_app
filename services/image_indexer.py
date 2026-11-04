import os
import json
from pathlib import Path
from typing import List, Dict, Any

VALID_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".heic", ".heif"}


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
                try:
                    rel_p = file_path.relative_to(root_path)
                    rel_path = str(rel_p)
                    folder_name = rel_p.parent.as_posix() if rel_p.parent.as_posix() != "." else ""
                except ValueError:
                    rel_path = file_path.name
                    folder_name = ""

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
    def scan_single_file(file_path_str: str) -> List[Dict[str, Any]]:
        """
        Mapea un único archivo de imagen en la misma estructura de datos que un lote.
        """
        file_path = Path(file_path_str).resolve()
        if not file_path.exists() or not file_path.is_file():
            raise ValueError(f"El archivo no existe: {file_path_str}")

        if file_path.suffix.lower() not in VALID_EXTENSIONS:
            raise ValueError(f"Extensión no admitida ({file_path.suffix}). Formatos: {', '.join(VALID_EXTENSIONS)}")

        return [{
            "folder_name": file_path.parent.name,
            "filename": file_path.name,
            "relative_path": file_path.name,
            "absolute_path": str(file_path),
            "processed_path": None,
            "processed": False,
            "cloud_url": None
        }]

    @staticmethod
    def get_summary(records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Genera estadísticas y métricas del conjunto de imágenes para la vista previa.
        """
        total = len(records)
        format_counts: Dict[str, int] = {}
        folders = set()

        for rec in records:
            ext = Path(rec["filename"]).suffix.lower().replace(".", "").upper()
            if ext in ("JPEG", "JPG"):
                ext = "JPG"
            format_counts[ext] = format_counts.get(ext, 0) + 1

            if rec.get("folder_name"):
                folders.add(rec["folder_name"])

        return {
            "total_images": total,
            "format_counts": format_counts,
            "subfolders_count": len(folders),
            "subfolders": sorted(list(folders))
        }

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
