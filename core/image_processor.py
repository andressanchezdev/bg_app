import os
from io import BytesIO
import numpy as np
from PIL import Image, ImageOps
from PySide6.QtGui import QImage


def get_object_bbox(img: Image.Image) -> tuple:
    """
    Obtiene el cuadro delimitador (bounding box) exacto del objeto:
    - Si la imagen tiene canal alfa con transparencias, usa el canal alfa.
    - Si la imagen es opaca (fondo blanco), detecta los píxeles que no son blancos.
    """
    if img.mode in ("RGBA", "LA"):
        alpha = img.split()[-1]
        extrema = alpha.getextrema()
        if extrema[0] < 250:
            bbox = alpha.getbbox()
            if bbox:
                return bbox

    # Si es RGB o no tiene transparencia, aislar sobre fondo blanco (R, G, B >= 248)
    rgb = img.convert("RGB")
    arr = np.array(rgb)
    not_white = ~((arr[:, :, 0] >= 248) & (arr[:, :, 1] >= 248) & (arr[:, :, 2] >= 248))
    coords = np.argwhere(not_white)
    if coords.size > 0:
        y0, x0 = coords.min(axis=0)
        y1, x1 = coords.max(axis=0) + 1
        return (int(x0), int(y0), int(x1), int(y1))

    return img.getbbox() or (0, 0, img.width, img.height)


def resize_image(
    pil_image: Image.Image,
    target_width: int,
    target_height: int,
    mode: str = "contain",
    white_bg: bool = False
) -> Image.Image:
    """
    Estandariza el tamaño de la imagen según las dimensiones y el modo especificado.

    :param mode:
      - 'contain': Escala manteniendo la proporción y centra el objeto en un lienzo
                   del tamaño exacto (target_width x target_height).
      - 'cover': Escala y recorta para llenar completamente el tamaño destino.
      - 'stretch': Fuerza el cambio de tamaño a target_width x target_height.
    :param white_bg:
      - True: El 100% del lienzo (de esquina a esquina) se rellena de blanco sólido (#FFFFFF).
      - False: El lienzo exterior se conserva 100% transparente (RGBA).
    """
    if target_width <= 0 or target_height <= 0:
        return pil_image

    img = pil_image.convert("RGBA")

    if mode == "stretch":
        resized = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
        if white_bg:
            bg = Image.new("RGBA", (target_width, target_height), (255, 255, 255, 255))
            bg.paste(resized, mask=resized.split()[3])
            return bg.convert("RGB")
        return resized

    elif mode == "cover":
        fitted = ImageOps.fit(img, (target_width, target_height), Image.Resampling.LANCZOS)
        if white_bg:
            bg = Image.new("RGBA", (target_width, target_height), (255, 255, 255, 255))
            bg.paste(fitted, mask=fitted.split()[3])
            return bg.convert("RGB")
        return fitted

    elif mode == "contain":
        # 1. Recortar al objeto real eliminando márgenes vacíos o blancos
        bbox = get_object_bbox(img)
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

        # 4. Crear lienzo exacto de las medidas destino
        # Si white_bg es True: fondo blanco puro (255, 255, 255, 255) en el 100% del lienzo
        # Si white_bg es False: fondo transparente (0, 0, 0, 0)
        canvas_color = (255, 255, 255, 255) if white_bg else (0, 0, 0, 0)
        canvas = Image.new("RGBA", (target_width, target_height), canvas_color)

        offset_x = (target_width - new_w) // 2
        offset_y = (target_height - new_h) // 2

        # Pegar el objeto centrado usando su máscara alfa
        canvas.paste(scaled_obj, (offset_x, offset_y), mask=scaled_obj.split()[3])

        if white_bg:
            return canvas.convert("RGB")
        return canvas

    return img


def resize_existing_webp_file(
    file_path: str,
    target_width: int,
    target_height: int,
    mode: str = "contain",
    quality: int = 90,
    white_bg: bool = False
) -> dict:
    """
    Abre una imagen WebP procesada existente, aplica el redimensionamiento y centrado en lienzo,
    asegurando que si es fondo blanco, este cubra el 100% de las nuevas medidas.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Archivo no encontrado: {file_path}")

    with Image.open(file_path) as raw_im:
        im = ImageOps.exif_transpose(raw_im)
        # Detectar si la imagen ya era sólida (fondo blanco)
        is_already_solid = (im.mode == "RGB") or (
            im.mode in ("RGBA", "LA") and im.getchannel("A").getextrema()[0] == 255
        )
        effective_white_bg = white_bg or is_already_solid

        resized = resize_image(
            im,
            target_width=target_width,
            target_height=target_height,
            mode=mode,
            white_bg=effective_white_bg
        )
        export_to_webp(
            pil_image=resized,
            output_path=file_path,
            quality=quality,
            method=6,
            white_bg=effective_white_bg
        )

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
    quality: int = 90,
    lossless: bool = False,
    method: int = 6,
    resize_config: dict = None,
    white_bg: bool = False
) -> str:
    """
    Renderiza y optimiza la imagen a WebP preservando la máxima nitidez visual
    y reduciendo el peso de archivo al mínimo.
    Si white_bg es True, garantiza que el 100% del lienzo sea blanco uniforme sin transparencias.
    """
    image_to_save = pil_image.convert("RGBA")

    # Renderizado y centrado en lienzo si está configurado
    if resize_config and resize_config.get("enabled", False):
        image_to_save = resize_image(
            image_to_save,
            target_width=resize_config.get("width", 900),
            target_height=resize_config.get("height", 900),
            mode=resize_config.get("mode", "contain"),
            white_bg=white_bg
        )
    elif white_bg:
        # Si no había redimensionamiento pero se pidió fondo blanco
        bg = Image.new("RGBA", image_to_save.size, (255, 255, 255, 255))
        bg.paste(image_to_save, (0, 0), mask=image_to_save.split()[3])
        image_to_save = bg.convert("RGB")

    # Si es fondo blanco, asegurarse que es RGB sin canal alfa (más ligero y 100% opaco)
    if white_bg:
        if image_to_save.mode != "RGB":
            bg = Image.new("RGB", image_to_save.size, (255, 255, 255))
            if "A" in image_to_save.getbands():
                bg.paste(image_to_save, mask=image_to_save.split()[3])
            else:
                bg.paste(image_to_save)
            image_to_save = bg
    else:
        # Optimización de peso para WebP transparente:
        # Neutralizar el color de píxeles 100% transparentes (alpha == 0) para
        # eliminar entropía residual y reducir el peso del archivo
        arr = np.array(image_to_save)
        if arr.ndim == 3 and arr.shape[2] == 4:
            transparent_mask = (arr[:, :, 3] == 0)
            if transparent_mask.any():
                arr[transparent_mask, :3] = 0
                image_to_save = Image.fromarray(arr, "RGBA")

    image_to_save.save(
        output_path,
        "WEBP",
        quality=quality,
        lossless=lossless,
        method=method,
        exact=False
    )
    return output_path
