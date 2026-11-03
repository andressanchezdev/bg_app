import os
from io import BytesIO
from PIL import Image, ImageOps
from PySide6.QtGui import QImage


def resize_image(
    pil_image: Image.Image,
    target_width: int,
    target_height: int,
    mode: str = "contain"
) -> Image.Image:
    """
    Estandariza el tamaño de la imagen según las dimensiones y el modo especificado.

    :param mode:
      - 'contain': Escala manteniendo la proporción y la centra en un lienzo transparente del tamaño destino.
      - 'cover': Escala y recorta los bordes para llenar exactamente el tamaño destino.
      - 'stretch': Fuerza el cambio de tamaño a target_width x target_height (puede deformar).
    """
    if target_width <= 0 or target_height <= 0:
        return pil_image

    img = pil_image.convert("RGBA")

    if mode == "stretch":
        return img.resize((target_width, target_height), Image.Resampling.LANCZOS)

    elif mode == "cover":
        return ImageOps.fit(img, (target_width, target_height), Image.Resampling.LANCZOS)

    elif mode == "contain":
        # 1. Recortar al objeto real eliminando márgenes vacíos previos (Autocrop)
        bbox = img.getbbox()
        if bbox:
            cropped_obj = img.crop(bbox)
        else:
            cropped_obj = img

        # 2. Margen de respiro estético uniforme (8% estándar catálogo de productos)
        pad = 0.08
        max_w = max(1, int(target_width * (1.0 - pad * 2)))
        max_h = max(1, int(target_height * (1.0 - pad * 2)))

        # 3. Escalar proporcionalmente preservando la relación de aspecto del objeto
        scale = min(max_w / cropped_obj.width, max_h / cropped_obj.height)
        new_w = max(1, int(cropped_obj.width * scale))
        new_h = max(1, int(cropped_obj.height * scale))
        scaled_obj = cropped_obj.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # 4. Crear lienzo transparente exacto del tamaño destino y centrar simétricamente
        canvas = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))
        offset_x = (target_width - new_w) // 2
        offset_y = (target_height - new_h) // 2
        canvas.paste(scaled_obj, (offset_x, offset_y), mask=scaled_obj)
        return canvas

    return img


def resize_existing_webp_file(
    file_path: str,
    target_width: int,
    target_height: int,
    mode: str = "contain",
    quality: int = 85
) -> dict:
    """
    Abre una imagen WebP procesada existente, aplica el redimensionamiento y centrado en lienzo,
    y la guarda nuevamente optimizada.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Archivo no encontrado: {file_path}")

    with Image.open(file_path) as im:
        resized = resize_image(im, target_width, target_height, mode=mode)
        resized.save(file_path, "WEBP", quality=quality, method=6, exact=False)

    new_size_bytes = os.path.getsize(file_path)
    return {
        "width": target_width,
        "height": target_height,
        "size_kb": new_size_bytes / 1024.0,
        "size_bytes": new_size_bytes
    }


def pil_to_qimage(pil_image: Image.Image) -> QImage:
    bytes_io = BytesIO()
    pil_image.save(bytes_io, format="PNG")
    return QImage.fromData(bytes_io.getvalue())


def qimage_to_pil(qimage: QImage) -> Image.Image:
    buffer = qimage.convertToFormat(QImage.Format_RGBA8888)
    width = buffer.width()
    height = buffer.height()
    ptr = buffer.bits()
    return Image.frombytes("RGBA", (width, height), ptr.tobytes())


def export_to_webp(
    pil_image: Image.Image,
    output_path: str,
    quality: int = 85,
    lossless: bool = False,
    method: int = 6,
    resize_config: dict = None
) -> str:
    """
    Exporta a WebP permitiendo estandarización de tamaño previa.
    :param resize_config: dict opcional {'enabled': True, 'width': 900, 'height': 900, 'mode': 'contain'}
    """
    image_to_save = pil_image.convert("RGBA")

    if resize_config and resize_config.get("enabled", False):
        image_to_save = resize_image(
            image_to_save,
            target_width=resize_config.get("width", 900),
            target_height=resize_config.get("height", 900),
            mode=resize_config.get("mode", "contain")
        )

    image_to_save.save(
        output_path,
        "WEBP",
        quality=quality,
        lossless=lossless,
        method=method,
        exact=False
    )
    return output_path
