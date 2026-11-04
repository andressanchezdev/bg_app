import os
import sys
import threading
from pathlib import Path
from typing import Optional
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

def get_model_path() -> Optional[str]:
    """Localiza el archivo del modelo ONNX tanto en entorno de desarrollo como en ejecutable empaquetado."""
    candidates = []
    if hasattr(sys, "_MEIPASS"):
        candidates.append(sys._MEIPASS)
        candidates.append(os.path.join(sys._MEIPASS, "_internal"))
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        candidates.append(exe_dir)
        candidates.append(os.path.join(exe_dir, "_internal"))
    candidates.append(str(Path(__file__).resolve().parent.parent))
    candidates.append(os.path.join(str(Path(__file__).resolve().parent.parent), "_internal"))
    candidates.append(os.getcwd())
    candidates.append(os.path.join(os.getcwd(), "_internal"))

    for base in candidates:
        if base and os.path.exists(base):
            for m_name in ("u2net.onnx", "u2netp.onnx"):
                p = os.path.join(base, "models", m_name)
                if os.path.exists(p):
                    return p
    return None


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

        model_path = get_model_path()
        if not model_path:
            print("[Aviso]: No se encontró el modelo neuronal U2-Net en ninguna de las rutas esperadas.")
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


def guided_filter_matting(guide_rgb: np.ndarray, raw_alpha: np.ndarray, radius: int = 3, eps: float = 1e-4) -> np.ndarray:
    """
    Refinamiento de bordes a resolución nativa mediante Filtro Guiado (He et al., TPAMI).
    Alinea la máscara suave de la IA con los contrastes reales de la imagen RGB original,
    recuperando detalles finos (tiras, cordones, contornos afilados).
    """
    guide_gray = cv2.cvtColor(guide_rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    p = raw_alpha.astype(np.float32) / 255.0
    ksize = (2 * radius + 1, 2 * radius + 1)

    mean_I = cv2.boxFilter(guide_gray, -1, ksize)
    mean_p = cv2.boxFilter(p, -1, ksize)
    mean_Ip = cv2.boxFilter(guide_gray * p, -1, ksize)
    cov_Ip = mean_Ip - mean_I * mean_p

    mean_II = cv2.boxFilter(guide_gray * guide_gray, -1, ksize)
    var_I = mean_II - mean_I * mean_I

    a = cov_Ip / (var_I + eps)
    b = mean_p - a * mean_I

    mean_a = cv2.boxFilter(a, -1, ksize)
    mean_b = cv2.boxFilter(b, -1, ksize)

    q = mean_a * guide_gray + mean_b
    return np.clip(q * 255.0, 0.0, 255.0).astype(np.uint8)


def decontaminate_color_edges(rgb: np.ndarray, alpha: np.ndarray, bg_color: np.ndarray = None) -> np.ndarray:
    """
    Descontaminación cromática perimetral (Defringing / Remove Matte).
    Elimina el sangrado del fondo blanco/estudio en los bordes semitransparentes del producto,
    restaurando el color puro original sin halos blanquecinos.
    """
    alpha_norm = (alpha.astype(np.float32) / 255.0)[:, :, np.newaxis]
    if bg_color is None:
        bg_color = np.array([255.0, 255.0, 255.0], dtype=np.float32)
    else:
        bg_color = bg_color.astype(np.float32)

    edge_mask = (alpha > 8) & (alpha < 248)
    clean_rgb = rgb.astype(np.float32)

    if edge_mask.any():
        weight = np.clip(alpha_norm, 0.25, 1.0)
        unmixed = (clean_rgb - (1.0 - alpha_norm) * bg_color) / weight
        clean_rgb = np.where(edge_mask[:, :, np.newaxis], unmixed, clean_rgb)

    # Neutralizar píxeles 100% transparentes para reducir entropía y peso de archivo
    clean_rgb = np.where((alpha == 0)[:, :, np.newaxis], 0, clean_rgb)
    return np.clip(clean_rgb, 0.0, 255.0).astype(np.uint8)


def clean_internal_cavities(orig_rgb: np.ndarray, alpha_pass1: np.ndarray):
    """
    FASE 2: Segundo repaso de limpieza inteligente para partes y cavidades internas.
    Drena fondos atrapados en ensenadas, entre extremidades, bajo asas y aberturas
    conectadas al exterior sin dañar prendas, texturas o detalles claros del producto.
    Retorna la máscara procesada y el color de fondo estimado.
    """
    h, w = orig_rgb.shape[:2]
    bg_mask_exterior = (alpha_pass1 == 0)
    default_bg = np.array([255.0, 255.0, 255.0], dtype=np.float32)

    if bg_mask_exterior.sum() < 50:
        return alpha_pass1, default_bg

    # 1. Muestrear la firma cromática del fondo en las 4 esquinas exteriores
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

    # Solo si el fondo exterior es relativamente homogéneo (fondo de estudio)
    if bg_std.mean() < 28.0:
        dist = np.linalg.norm(orig_rgb.astype(np.float32) - bg_median, axis=2)
        tol = max(20.0, min(36.0, float(np.mean(bg_std) * 2.5 + 18.0)))
        is_bg_color = (dist <= tol).astype(np.uint8)

        # 2. Conectar con el exterior: solo drena áreas donde el fondo penetra desde los bordes
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(is_bg_color, connectivity=8)
        outer_labels = set(np.unique(np.concatenate([labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1]])))
        if 0 in outer_labels:
            outer_labels.remove(0)

        connected_exterior = np.zeros((h, w), dtype=bool)
        for lab in outer_labels:
            connected_exterior |= (labels == lab)

        # Cavidades abiertas donde el fondo exterior penetró pero la IA cubrió por error
        drain_mask = connected_exterior & (alpha_pass1 > 30)
        if drain_mask.any():
            feath = cv2.GaussianBlur(drain_mask.astype(np.float32), (3, 3), 0)
            final_alpha = np.clip(alpha_pass1.astype(np.float32) * (1.0 - feath), 0.0, 255.0).astype(np.uint8)
            return final_alpha, bg_median

    return alpha_pass1, bg_median


def remove_background_neural_u2net(pil_image: Image.Image) -> Image.Image:
    """
    Segmentación semántica profunda utilizando la red neuronal U2-Net con
    pipeline de dos fases: silueta exterior completa + limpieza de cavidades internas +
    refinamiento Guided Filter + descontaminación cromática de halos.
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

    # 6. FASE 1: Silueta y contorno exterior
    # Umbral no destructivo que preserva todas las partes del objeto (cabeza, cuerpo, accesorios)
    alpha_pass1 = np.clip((mask_full - 0.04) / (0.75 - 0.04), 0.0, 1.0)
    alpha_u8 = (alpha_pass1 * 255.0).astype(np.uint8)

    # 7. FASE 2: Segundo repaso para cavidades y partes internas
    alpha_cav, bg_color = clean_internal_cavities(rgb, alpha_u8)

    # 8. Refinamiento de bordes a resolución nativa con Filtro Guiado (Guided Filter Matting)
    alpha_guided = guided_filter_matting(rgb, alpha_cav, radius=3, eps=1e-4)

    # 9. Descontaminación cromática perimetral (Defringing / Anti-haloing)
    clean_rgb = decontaminate_color_edges(rgb, alpha_guided, bg_color=bg_color)

    # 10. Composición de la imagen RGBA final
    out_rgba = np.dstack([clean_rgb, alpha_guided])
    return Image.fromarray(out_rgba, "RGBA")


def process_remove_background(pil_image: Image.Image, session=None) -> Image.Image:
    """
    Punto único de entrada para remoción de fondo con IA.
    Ejecuta rembg si está disponible, o la red neuronal U2-Net profunda vía OpenCV.
    Aplica el segundo repaso de cavidades internas y refinamiento de bordes.
    """
    if REMBG_AVAILABLE and remove is not None and session is not None:
        try:
            res = remove(pil_image, session=session)
            arr = np.array(res)
            if arr.shape[2] == 4:
                rgb = arr[:, :, :3]
                alpha = arr[:, :, 3]
                alpha_cav, bg_color = clean_internal_cavities(rgb, alpha)
                alpha_guided = guided_filter_matting(rgb, alpha_cav, radius=3, eps=1e-4)
                clean_rgb = decontaminate_color_edges(rgb, alpha_guided, bg_color=bg_color)
                return Image.fromarray(np.dstack([clean_rgb, alpha_guided]), "RGBA")
            return res
        except Exception:
            pass

    # Ejecutar inferencia neuronal U2-Net con pipeline de alta precisión
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
