"""
Build de release de Remover Background IP.

  1. Limpia build/ y dist/.
  2. Empaqueta con PyInstaller usando bg_app.spec.
  3. Ejecuta el .exe generado con --self-test (aborta si falla).
  4. Compila el instalador con Inno Setup (ISCC) -> dist/setup-<version>.exe

Uso:  python build_release.py [--skip-installer]
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST_APP = ROOT / "dist" / "RemoverBackgroundIP"
EXE = DIST_APP / "RemoverBackgroundIP.exe"


def app_version() -> str:
    for line in (ROOT / "config.py").read_text(encoding="utf-8").splitlines():
        if line.startswith("APP_VERSION"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("No se encontró APP_VERSION en config.py")


def find_iscc():
    candidates = [
        shutil.which("iscc"),
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Inno Setup 6", "ISCC.exe"),
    ]
    return next((c for c in candidates if c and os.path.exists(c)), None)


def step(msg: str) -> None:
    print(f"\n==> {msg}", flush=True)


def main() -> int:
    skip_installer = "--skip-installer" in sys.argv
    version = app_version()

    for model in ("u2net.onnx",):
        if not (ROOT / "models" / model).exists():
            raise SystemExit(f"Falta models/{model} (no está en git; cópielo antes de compilar).")

    step("Limpiando build/ y dist/")
    for d in ("build", "dist"):
        shutil.rmtree(ROOT / d, ignore_errors=True)

    step("Empaquetando con PyInstaller (bg_app.spec)")
    res = subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "bg_app.spec"], cwd=ROOT)
    if res.returncode != 0 or not EXE.exists():
        raise SystemExit("PyInstaller falló.")

    step("Verificando el ejecutable (--self-test)")
    env = dict(os.environ, LOCALAPPDATA=str(ROOT / "build" / "selftest_data"))
    res = subprocess.run([str(EXE), "--self-test"], cwd=os.environ.get("SystemRoot", "C:\\Windows"), env=env, timeout=300)
    log_file = ROOT / "build" / "selftest_data" / "RemoverBackgroundIP" / "logs" / "app.log"
    if log_file.exists():
        print(log_file.read_text(encoding="utf-8", errors="replace"))
    if res.returncode != 0:
        raise SystemExit("El self-test del ejecutable falló: revise el log anterior.")

    if skip_installer:
        print(f"\nListo (sin instalador): {EXE}")
        return 0

    step("Compilando instalador con Inno Setup")
    iscc = find_iscc()
    if not iscc:
        raise SystemExit("No se encontró ISCC.exe. Instale Inno Setup 6: winget install JRSoftware.InnoSetup")
    res = subprocess.run([iscc, f"/DMyAppVersion={version}", "installer.iss"], cwd=ROOT)
    if res.returncode != 0:
        raise SystemExit("Inno Setup falló.")

    setup = ROOT / "dist" / f"setup-{version}.exe"
    print(f"\nListo: {setup} ({setup.stat().st_size / 1024 / 1024:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
