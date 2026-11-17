# -*- mode: python ; coding: utf-8 -*-
# Build reproducible de Remover Background IP.
# Uso:  python build_release.py   (o: python -m PyInstaller --noconfirm --clean bg_app.spec)
import os
from PyInstaller.utils.hooks import collect_all

base_dir = os.path.abspath(SPECPATH)

datas = [
    (os.path.join(base_dir, "models"), "models"),
    (os.path.join(base_dir, "assets"), "assets"),
]
# Recursos opcionales (no versionados): variables de entorno y llave de servicio de GCP
if os.path.exists(os.path.join(base_dir, ".env")):
    datas.append((os.path.join(base_dir, ".env"), "."))
# Configuración que funciona en la v1 (BD/GCS): se copia al primer arranque de la app instalada
if os.path.exists(os.path.join(base_dir, "output", "settings.json")):
    datas.append((os.path.join(base_dir, "output", "settings.json"), "defaults"))
if os.path.isdir(os.path.join(base_dir, "credentials")):
    datas.append((os.path.join(base_dir, "credentials"), "credentials"))

# Datos de versión del .exe (nombre visible en el Administrador de tareas y en Propiedades)
import re as _re
_cfg = open(os.path.join(base_dir, "config.py"), encoding="utf-8").read()
APP_NAME = _re.search(r'^APP_NAME = "(.+)"', _cfg, _re.M).group(1)
APP_VERSION = _re.search(r'^APP_VERSION = "(.+)"', _cfg, _re.M).group(1)
_v = tuple(int(x) for x in APP_VERSION.split(".")) + (0,) * (4 - len(APP_VERSION.split(".")))
os.makedirs(os.path.join(base_dir, "build"), exist_ok=True)
version_file = os.path.join(base_dir, "build", "version_info.txt")
with open(version_file, "w", encoding="utf-8") as _f:
    _f.write(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={_v}, prodvers={_v}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('0C0A04B0', [
      StringStruct('CompanyName', 'Importadora Premium'),
      StringStruct('FileDescription', '{APP_NAME}'),
      StringStruct('FileVersion', '{APP_VERSION}'),
      StringStruct('InternalName', 'RemoverBackgroundIP'),
      StringStruct('OriginalFilename', 'RemoverBackgroundIP.exe'),
      StringStruct('ProductName', '{APP_NAME}'),
      StringStruct('ProductVersion', '{APP_VERSION}')])]),
    VarFileInfo([VarStruct('Translation', [0x0C0A, 1200])])
  ]
)
""")

binaries = []
# Python 3.15: extensiones con ABI estable "abi3t" (p. ej. cryptography, usada por google-auth)
# enlazan python3t.dll, que vive en <python>/abi3t-compat y PyInstaller no detecta.
# Sin ella el ejecutable falla al arrancar con "DLL load failed while importing _rust".
import sys as _sys
_abi3t = os.path.join(_sys.base_prefix, "abi3t-compat", "python3t.dll")
if os.path.exists(_abi3t):
    binaries.append((_abi3t, "."))
hiddenimports = [
    "pymysql", "psycopg2", "requests", "cv2", "numpy",
    "google.cloud.storage", "google.auth", "google.oauth2.service_account",
    "google.api_core", "google.resumable_media", "google_crc32c",
    "PySide6.QtNetwork",
]
for pkg in ("google.cloud.storage", "google.auth", "pillow_heif"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["main.py"],
    pathex=[base_dir],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter", "matplotlib", "scipy", "pytest",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
        "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.Qt3DCore", "PySide6.QtQuick",
        "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RemoverBackgroundIP",
    version=version_file,
    icon=os.path.join(base_dir, "assets", "app.ico"),
    debug=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="RemoverBackgroundIP",
)
