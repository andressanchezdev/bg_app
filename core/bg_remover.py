from PIL import Image
from rembg import remove, new_session
from PySide6.QtCore import QThread, Signal


# ----------------------------------------------------------------------
# 1. Sesión Singleton de rembg (Evita recargar el modelo en cada imagen)
# ----------------------------------------------------------------------
_SESSION_INSTANCE = None


def get_ai_session(model_name: str = "u2net"):
    """
    Retorna la sesión única del modelo de IA cargado en memoria RAM/GPU.
    Modelos disponibles en rembg: 'u2net', 'isnet-general-use', 'birefnet-general'.
    """
    global _SESSION_INSTANCE
    if _SESSION_INSTANCE is None:
        _SESSION_INSTANCE = new_session(model_name)
    return _SESSION_INSTANCE


# ----------------------------------------------------------------------
# 2. Worker en Hilo Secundario (QThread) para Modo Individual
# ----------------------------------------------------------------------
class AIRemoverWorker(QThread):
    finished = Signal(Image.Image)
    error = Signal(str)

    def __init__(self, pil_image: Image.Image, session=None):
        super().__init__()
        self.pil_image = pil_image
        self.session = session if session else get_ai_session()

    def run(self):
        try:
            # Procesa la imagen con el modelo de rembg
            output_pil = remove(self.pil_image, session=self.session)
            self.finished.emit(output_pil)
        except Exception as e:
            self.error.emit(str(e))