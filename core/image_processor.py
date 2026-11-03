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
        # Mantiene la relación de aspecto ajustándose dentro de las dimensiones
        img.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)
        
        # Crea un lienzo transparente del tamaño exacto destino
        canvas = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))
        
        # Centra la imagen escalada en el lienzo
        offset_x = (target_width - img.width) // 2
        offset_y = (target_height - img.height) // 2
        canvas.paste(img, (offset_x, offset_y), mask=img)
        return canvas

    return img


def pil_to_qimage(pil_image: Image.Image) -> QImage:
    bytes_io = BytesIO()
    pil_image.save(bytes_io, format="PNG")
    return QImage.fromData(bytes_io.getvalue())


def qimage_to_pil(qimage: QImage) -> Image.Image:
    buffer = qimage.convertToFormat(QImage.Format_RGBA8888)
    width, height = buffer.width()
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
    :param resize_config: dict opcional {'enabled': True, 'width': 1080, 'height': 1080, 'mode': 'contain'}
    """
    image_to_save = pil_image.convert("RGBA")

    if resize_config and resize_config.get("enabled", False):
        image_to_save = resize_image(
            image_to_save,
            target_width=resize_config.get("width", 1080),
            target_height=resize_config.get("height", 1080),
            mode=resize_config.get("mode", "contain")
        )

    image_to_save.save(
        output_path,
        "WEBP",
        quality=quality,
        lossless=lossless,
        method=method
    )
    return output_path