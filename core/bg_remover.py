import os
import threading
from pathlib import Path
import numpy as np
from PIL import Image
from PySide6.QtCore import QThread, Signal

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    cv2 = None
    CV2_AVAILABLE = False

try:
    from rembg import remove, new_session
    REMBG_AVAILABLE = True
except ImportError:
    remove = None
    new_session = None
    REMBG_AVAILABLE = False

_SESSION_INSTANCE = None
_CV2_DNN_INSTANCE = None
_DNN_LOCK = threading.Lock()

MODELS_DIR = os.path.join(os.getcwd(), "models")
DEFAULT_MODEL_PATH = os.path.join(MODELS_DIR, "u2net.onnx")
LITE_MODEL_PATH = os.path.join(MODELS_DIR, "u2netp.onnx")


def get_opencv_dnn_net():
    """
    Carga y mantiene en memoria la red neuronal profunda U2-Net mediante OpenCV DNN.
    Garantiza inferencia de IA de alta precisión sin depender de onnxruntime.
    """
    global _CV2_DNN_INSTANCE
    with _DNN_LOCK:
        if _CV2_DNN_INSTANCE is not None:
            return _CV2_DNN_INSTANCE

        if not CV2_AVAILABLE:
            return None

        model_path = DEFAULT_MODEL_PATH if os.path.exists(DEFAULT_MODEL_PATH) else LITE_MODEL_PATH
        if not os.path.exists(model_path):
            alt_path = os.path.join(Path(__file__).resolve().parent.parent, "models", "u2net.onnx")
            if os.path.exists(alt_path):
                model_path = alt_path
            else:
                print(f"[Aviso]: No se encontró el modelo neuronal en {model_path}")
                return None

        try:
            print(f"[IA Motor]: Cargando red neuronal U2-Net desde {model_path}...")
            _CV2_DNN_INSTANCE = cv2.dnn.readNetFromONNX(model_path)
            return _CV2_DNN_INSTANCE
        except Exception as e:
            print(f"[Error cargando modelo neuronal OpenCV]: {e}")
            return None


def get_ai_session(model_name: str = "u2net"):
    """
    Retorna la sesión única del modelo si rembg está presente,
    o inicializa la red neuronal OpenCV DNN.
    """
    global _SESSION_INSTANCE
    if REMBG_AVAILABLE and new_session is not None:
        if _SESSION_INSTANCE is None:
            try:
                _SESSION_INSTANCE = new_session(model_name)
            except Exception:
                _SESSION_INSTANCE = None
        if _SESSION_INSTANCE is not None:
            return _SESSION_INSTANCE

    # Si rembg no está o falla, inicializar motor neuronal OpenCV DNN
    return get_opencv_dnn_net()


def clean_internal_cavities(orig_rgb: np.ndarray, alpha_pass1: np.ndarray) -> np.ndarray:
    """
    PASO 2: Segundo repaso de limpieza inteligente para partes y cavidades internas.
    Detecta y elimina fondos atrapados en orificios, asas, entre extremidades y cavidades
    interiores preservando los detalles y texturas legítimas del producto.
    """
    h, w = orig_rgb.shape[:2]
    bg_mask_exterior = (alpha_pass1 == 0)

    # Si no hay suficiente fondo exterior confirmado, retornar máscara base
    if bg_mask_exterior.sum() < 50:
        return alpha_pass1

    # 1. Muestrear la firma cromática del fondo confirmado en las 4 esquinas exteriores
    corner_h, corner_w = max(5, int(h * 0.06)), max(5, int(w * 0.06))
    corner_mask = np.zeros((h, w), dtype=bool)
    corner_mask[:corner_h, :corner_w] = True
    corner_mask[:corner_h, -corner_w:] = True
    corner_mask[-corner_h:, :corner_w] = True
    corner_mask[-corner_h:, -corner_w:] = True

    sample_mask = bg_mask_exterior & corner_mask
    if sample_mask.sum() < 30:
        sample_mask = bg_mask_exterior

    sample_pixels = orig_rgb[sample_mask]
    bg_median = np.median(sample_pixels, axis=0)
    bg_std = np.std(sample_pixels, axis=0)

    # Tolerancia adaptativa según la homogeneidad del fondo de estudio
    tol = max(22.0, min(36.0, float(np.mean(bg_std) * 2.5 + 20.0)))

    # 2. Localizar píxeles internos con color idéntico al fondo
    color_dist = np.linalg.norm(orig_rgb.astype(np.float32) - bg_median, axis=2)
    is_bg_color = color_dist <= tol

    # Zonas marcadas como objeto en Paso 1 que coinciden con el fondo exterior
    candidate = (alpha_pass1 > 40) & is_bg_color
    candidate_u8 = candidate.astype(np.uint8) * 255

    # 3. Apertura morfológica para proteger detalles finos y costuras legítimas
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    clean_cand = cv2.morphologyEx(candidate_u8, cv2.MORPH_OPEN, kernel)

    # 4. Filtrar componentes por área y homogeneidad de textura
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(clean_cand, connectivity=8)
    cavity_mask = np.zeros((h, w), dtype=np.uint8)

    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        # Evitar ruidos microscópicos: solo cavidades con área apreciable (>= 25 px)
        if area >= 25:
            comp_pixels = orig_rgb[labels == i]
            comp_std = np.std(comp_pixels, axis=0).mean()
            # El fondo de estudio es plano y tiene muy baja varianza textural (< 18.0)
            if comp_std < 18.0:
                cavity_mask[labels == i] = 255

    # 5. Suavizado de bordes internos (feathering) para transiciones limpias y orgánicas
    if cavity_mask.any():
        feath = cv2.GaussianBlur(cavity_mask.astype(np.float32), (3, 3), 0) / 255.0
        final_alpha = np.clip(alpha_pass1.astype(np.float32) * (1.0 - feath), 0.0, 255.0).astype(np.uint8)
        return final_alpha

    return alpha_pass1


def remove_background_neural_u2net(pil_image: Image.Image) -> Image.Image:
    """
    Segmentación semántica profunda utilizando la red neuronal U2-Net con
    pipeline de dos pasos: silueta exterior + limpieza de cavidades internas.
    """
    net = get_opencv_dnn_net()
    if net is None:
        raise RuntimeError("No se pudo inicializar la red neuronal U2-Net para segmentación.")

    # 1. Convertir imagen PIL a formato OpenCV BGR
    orig_rgba = pil_image.convert("RGBA")
    orig_np = np.array(orig_rgba)
    orig_h, orig_w = orig_np.shape[:2]

    # Imagen RGB para inferencia
    rgb = orig_np[:, :, :3]
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

    # 2. Preprocesamiento estándar U2Net (320x320 con normalización ImageNet)
    input_size = 320
    resized_bgr = cv2.resize(bgr, (input_size, input_size)).astype(np.float32) / 255.0
    
    # Normalización con media y desviación estándar de ImageNet
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)  # BGR order: [0.406, 0.456, 0.485]
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    norm_bgr = (resized_bgr[:, :, ::-1] - mean) / std  # invertir a RGB antes de normalizar

    # Convertir a formato NCHW para la red
    blob = np.transpose(norm_bgr, (2, 0, 1))
    blob = np.expand_dims(blob, axis=0)

    # 3. Inferencia de la red neuronal con exclusión mutua para concurrencia segura
    with _DNN_LOCK:
        net.setInput(blob)
        output = net.forward()

    # 4. Procesar mapa de saliencia de salida
    raw_mask = output[0, 0]

    # Normalizar entre 0 y 1
    d_min, d_max = raw_mask.min(), raw_mask.max()
    if d_max > d_min:
        norm_mask = (raw_mask - d_min) / (d_max - d_min)
    else:
        norm_mask = raw_mask

    # 5. Escalar máscara a resolución original con interpolación cúbica suave
    mask_full = cv2.resize(norm_mask, (orig_w, orig_h), interpolation=cv2.INTER_CUBIC)

    # 6. PASO 1: Aislamiento al 100% del contorno exterior y silueta
    # A) Umbral de corte estricto de fondo (elimina ruido tenue < 0.18) y consolidación (> 0.82)
    t_low = 0.18
    t_high = 0.82
    refined_mask = np.clip((mask_full - t_low) / (t_high - t_low), 0.0, 1.0)

    # B) Supresión de ruido satélite / manchas residuales exteriores mediante componentes conexos
    bin_mask = (refined_mask > 0.15).astype(np.uint8)
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(bin_mask, connectivity=8)

    total_area = orig_w * orig_h
    clean_bin_mask = np.zeros_like(bin_mask)
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        if area >= total_area * 0.008:
            clean_bin_mask[labels == i] = 1

    # Si ningún componente alcanzó el 0.8%, asegurar conservar el de mayor área
    if clean_bin_mask.sum() == 0 and num_labels > 1:
        largest_i = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
        clean_bin_mask[labels == largest_i] = 1

    # Máscara exterior del Paso 1
    pass1_mask = refined_mask * clean_bin_mask
    alpha_pass1 = (pass1_mask * 255.0).astype(np.uint8)

    # 7. PASO 2: Segundo repaso para cavidades y partes internas
    alpha_final = clean_internal_cavities(rgb, alpha_pass1)

    # 8. Asignar nuevo canal alfa a la imagen original
    orig_np[:, :, 3] = alpha_final
    return Image.fromarray(orig_np, "RGBA")


def process_remove_background(pil_image: Image.Image, session=None) -> Image.Image:
    """
    Punto único de entrada para remoción de fondo con IA.
    Ejecuta rembg si está disponible, o la red neuronal U2-Net profunda vía OpenCV.
    Aplica el segundo repaso de cavidades internas en ambos casos.
    """
    if REMBG_AVAILABLE and remove is not None and session is not None:
        try:
            res = remove(pil_image, session=session)
            arr = np.array(res)
            if arr.shape[2] == 4:
                rgb = arr[:, :, :3]
                alpha = arr[:, :, 3]
                arr[:, :, 3] = clean_internal_cavities(rgb, alpha)
                return Image.fromarray(arr, "RGBA")
            return res
        except Exception:
            pass

    # Ejecutar inferencia neuronal U2-Net con dos fases integradas
    return remove_background_neural_u2net(pil_image)


class AIRemoverWorker(QThread):
    finished = Signal(Image.Image)
    error = Signal(str)

    def __init__(self, pil_image: Image.Image, session=None):
        super().__init__()
        self.pil_image = pil_image
        self.session = session if session else get_ai_session()

    def run(self):
        try:
            output_pil = process_remove_background(self.pil_image, session=self.session)
            self.finished.emit(output_pil)
        except Exception as e:
            self.error.emit(str(e))
