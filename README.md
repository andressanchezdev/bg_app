# IA Background Remover, Editor & Batch Converter

Aplicación de escritorio desarrollada en Python con **PySide6** para la eliminación de fondos mediante Inteligencia Artificial, edición manual fina con pinceles y procesamiento/conversión por lotes con exportación optimizada a formato **WebP** y sincronización opcional con **Google Cloud Storage (GCS)**.

---

## 🚀 Características Principales

1. **Eliminación de Fondo con IA**:
   - Integración con el motor de inferencia `rembg` (soporta modelos como `u2net`, `isnet-general-use`, `birefnet-general`).
   - Sesión singleton en memoria para evitar recargas innecesarias del modelo ONNX entre imágenes.

2. **Edición Manual y Retoque Fino (Pinceles)**:
   - Lienzo interactivo basado en `QGraphicsView` y acelerado por `QPainter`.
   - Modos de navegación y zoom interactivo con rueda del ratón.
   - Pincel borrador (transparencia) y pincel restaurador (recuperación de partes eliminadas de la imagen original) con tamaño ajustable de 5 a 200 px.

3. **Estandarización y Redimensionamiento**:
   - Ajuste de dimensiones de salida (ancho y alto personalizables).
   - Bloqueo y cálculo automático de la relación de aspecto (*Aspect Ratio*).
   - Modos de ajuste:
     - **Centrar con Lienzo (Contain)**: escala manteniendo proporciones y centra sobre lienzo transparente.
     - **Recortar para Llenar (Cover)**: escala y recorta bordes para llenar exactamente el área.
     - **Estirar / Deformar (Stretch)**: ajusta directamente a las dimensiones indicadas.

4. **Exportación Optimizada**:
   - Conversión y compresión en formato **WebP** con control de calidad (1-100%).
   - Opción para rellenar fondos transparentes con color blanco sólido (ideal para catálogos y e-commerce).
   - Soporte para formatos comunes (`.png`, `.jpg`, `.jpeg`, `.bmp`, `.webp`) y archivos `.heic` / `.heif` (vía `pillow-heif`).

5. **Procesamiento en Lote (Tandas Masivas)**:
   - Mapeo e indexación recursiva de carpetas y subcarpetas con persistencia en `output/image_map.json`.
   - Ejecución multihilo con `QThreadPool` para no congelar la interfaz de usuario.
   - Tabla de estado en tiempo real con progreso individual y barra general.
   - Opción para abrir cualquier imagen procesada directamente en el editor manual.

6. **Integración con Google Cloud Storage (GCS)**:
   - Carga automática opcional de imágenes procesadas al bucket de GCS configurado.
   - Respeto de la estructura de carpetas origen (`carpeta_padre/imagen.webp`).
   - Generación y copia al portapapeles de URLs públicas/estándar de GCS.
   - Diagnóstico visual de presencia de credenciales en tiempo real (`credentials/gcp_key.json`).

7. **Interfaz Moderna y Temas**:
   - Selector dinámico de temas: **Oscuro** (Dark) y **Claro** (Light).
   - Pantalla de carga (*Splash Screen*) informativa durante el arranque de los módulos y modelos.

---

## 📁 Estructura del Proyecto

```text
bg_app/
│
├── core/
│   ├── batch_worker.py        # QRunnable para tareas de procesamiento en lote
│   ├── bg_remover.py          # Sesión singleton de rembg y QThread individual
│   └── image_processor.py     # Redimensionamiento, conversión de formatos y exportación WebP
│
├── services/
│   ├── cloud_storage.py       # Cliente para Google Cloud Storage
│   └── image_indexer.py       # Escaneo recursivo de carpetas y mapeo en JSON
│
├── ui/
│   ├── canvas.py              # QGraphicsView con soporte de máscaras y pinceles
│   ├── main_window.py         # Ventana principal, estilos y barra superior
│   ├── resize_group.py        # Widget reutilizable de configuración de dimensiones
│   ├── tab_single.py          # Pestaña de edición individual y pinceles
│   ├── tab_batch.py           # Pestaña de procesamiento masivo por lotes
│   ├── tab_settings.py        # Pestaña de configuración (temas y credenciales GCP)
│   └── tab_processing.py      # Módulo auxiliar para mapeo de lotes
│
├── credentials/
│   └── gcp_key.json.example   # Plantilla de ejemplo para llave de servicio de GCP
│
├── output/                    # Directorio de salida predeterminado para exports y JSONs
│
├── config.py                  # Parámetros por defecto globales
├── main.py                    # Punto de entrada de la aplicación con Splash Screen
├── requirements.txt           # Dependencias de Python
└── README.md                  # Documentación
```

---

## 🛠️ Instalación y Requisitos

### 1. Clonar el repositorio
```bash
git clone https://github.com/andressanchezdev/bg_app.git
cd bg_app
```

### 2. Crear y activar entorno virtual (Recomendado)
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

### 3. Instalar dependencias
```bash
pip install -r requirements.txt
```

> **Nota para aceleración por GPU (CUDA)**:
> Si dispones de tarjeta NVIDIA y deseas máxima velocidad con ONNX Runtime:
> ```bash
> pip install onnxruntime-gpu
> ```

---

## ⚙️ Configuración de Google Cloud Storage (Opcional)

Si deseas sincronizar y subir automáticamente las imágenes procesadas a un bucket de Google Cloud Storage:

1. Crea una Cuenta de Servicio en Google Cloud Console con permisos de lectura/escritura sobre tu Bucket (ej: `Storage Object Admin`).
2. Descarga la llave en formato JSON y colócala en:
   ```text
   credentials/gcp_key.json
   ```
3. Configura el nombre del bucket en el archivo `config.py` o directamente desde la pestaña **Configuración** de la aplicación:
   ```python
   GCS_BUCKET_NAME = "mi-bucket-de-gcp"
   GCS_BASE_FOLDER = "dependencias/img/productos/"
   ```

---

## 🚀 Uso de la Aplicación

Ejecuta el archivo principal:
```bash
python main.py
```

### Modo Edición Individual
1. Selecciona la pestaña **🎨 Edición Individual & Pincel**.
2. Haz clic en **📁 Cargar Imagen** para importar un archivo.
3. Presiona **✨ Eliminar Fondo (IA)** para generar la máscara inicial.
4. Ajusta los bordes o detalles con los pinceles **🧹 Pincel Borrador** o **🖌️ Pincel Restaurador**.
5. Configura dimensiones en **Estandarizar Tamaño de Salida** si deseas un tamaño específico.
6. Pulsa **💾 Exportar a .WebP**.

### Modo Lotes Masivos
1. Selecciona la pestaña **⚡ Procesamiento en Lote (Tandas)** o pulsa **📂 Cargar Carpeta (Mapeo JSON)** en la barra superior.
2. Selecciona la carpeta que contiene las imágenes (se escanearán subcarpetas automáticamente).
3. Selecciona la carpeta de destino.
4. Ajusta las opciones deseadas (Fondo blanco, Redimensionamiento, Subida a GCS, Calidad WebP).
5. Pulsa **Iniciar Procesamiento en Lote**. Al finalizar, el estado quedará registrado en `output/image_map.json`.
