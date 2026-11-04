import os
import sys
import zipfile
import shutil
import subprocess

def main():
    root_dir = os.path.abspath(os.path.dirname(__file__))
    dist_app = os.path.join(root_dir, "dist", "IABackgroundRemover")
    
    if not os.path.exists(dist_app):
        print(f"Error: No se encontró la carpeta compilada: {dist_app}")
        sys.exit(1)
        
    exe_target = os.path.join(dist_app, "IABackgroundRemover.exe")
    if not os.path.exists(exe_target):
        print(f"Error: No se encontró el ejecutable principal en: {exe_target}")
        sys.exit(1)
        
    print("[1/3] Creando paquete comprimido app_payload.zip...")
    zip_path = os.path.join(root_dir, "app_payload.zip")
    
    total_files = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for foldername, _, filenames in os.walk(dist_app):
            for filename in filenames:
                filepath = os.path.join(foldername, filename)
                arcname = os.path.relpath(filepath, dist_app)
                zf.write(filepath, arcname)
                total_files += 1
                
    zip_size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"       -> {total_files} archivos comprimidos ({zip_size_mb:.2f} MB)")
    
    print("[2/3] Compilando instalador setup.exe con PyInstaller...")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name", "setup",
        "--add-data", f"{zip_path};.",
        "installer.py"
    ]
    
    res = subprocess.run(cmd, cwd=root_dir)
    if res.returncode != 0:
        print("Error al compilar setup.exe")
        sys.exit(res.returncode)
        
    # Copiar también setup.exe a la raíz para mayor comodidad
    dist_setup = os.path.join(root_dir, "dist", "setup.exe")
    root_setup = os.path.join(root_dir, "setup.exe")
    if os.path.exists(dist_setup):
        shutil.copy2(dist_setup, root_setup)
        setup_size_mb = os.path.getsize(root_setup) / (1024 * 1024)
        print(f"[3/3] ¡Éxito! setup.exe generado correctamente:")
        print(f"      - {dist_setup} ({setup_size_mb:.2f} MB)")
        print(f"      - {root_setup} ({setup_size_mb:.2f} MB)")
    else:
        print("Advertencia: No se encontró dist/setup.exe tras la compilación.")

if __name__ == "__main__":
    main()

