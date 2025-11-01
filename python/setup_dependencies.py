#!/usr/bin/env python3
"""
Setup script pentru dependențele DXF to GLB converter
Instalează toate dependențele necesare pentru funcționalitatea completă
"""

import subprocess
import sys
import os
import platform

def install_package(package):
    """Instalează un pachet Python prin pip"""
    try:
        # Upgrade pip înainte de instalare
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], 
                            capture_output=True)
        
        # Instalează pachetul
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        print(f"✓ {package} installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to install {package}: {e}")
        return False

def check_package(package_name, import_name=None):
    """Verifică dacă un pachet este deja instalat"""
    if import_name is None:
        import_name = package_name
    
    try:
        # Încearcă să importe modulul
        if '.' in import_name:
            # Pentru module nested ca 'trimesh.util'
            parts = import_name.split('.')
            mod = __import__(parts[0])
            for part in parts[1:]:
                mod = getattr(mod, part)
        else:
            __import__(import_name)
        print(f"✓ {package_name} already installed")
        return True
    except (ImportError, AttributeError):
        print(f"⚠ {package_name} not found, installing...")
        return False

def check_python_version():
    """Verifică dacă versiunea Python este compatibilă"""
    if sys.version_info < (3, 8):
        print("✗ Python 3.8+ is required!")
        return False
    print(f"✓ Python {sys.version} detected")
    return True

def install_from_requirements():
    """Instalează toate dependențele din requirements.txt"""
    requirements_path = os.path.join(os.path.dirname(__file__), "requirements.txt")
    
    if not os.path.exists(requirements_path):
        print(f"✗ {requirements_path} not found!")
        return False
    
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "-r", requirements_path
        ])
        print("✓ All requirements.txt dependencies installed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to install from requirements.txt: {e}")
        return False

def main():
    print("=== DXF to GLB Converter Setup ===\n")
    
    # Verifică versiunea Python
    if not check_python_version():
        return 1
    
    print(f"Platform: {platform.system()} {platform.release()}\n")
    
    # Lista dependențelor critice pentru verificare
    critical_dependencies = [
        ("ezdxf", "ezdxf"),           # DXF parsing
        ("trimesh", "trimesh"),        # 3D mesh processing
        ("numpy", "numpy"),           # Mathematical operations
        ("shapely", "shapely"),       # 2D geometry
        ("watchdog", "watchdog"),     # File monitoring
    ]
    
    # Optional dependencies
    optional_dependencies = [
        ("ifcopenshell", "ifcopenshell"),  # IFC processing
        ("scipy", "scipy"),               # Scientific computing
        ("networkx", "networkx"),         # Graph algorithms
        ("numba", "numba"),              # Performance
    ]
    
    print("Installing from requirements.txt...")
    requirements_success = install_from_requirements()
    
    print("\nVerifying critical dependencies...")
    all_critical_installed = True
    for import_name, package_name in critical_dependencies:
        if not check_package(package_name, import_name):
            if not install_package(package_name):
                all_critical_installed = False
    
    print("\nVerifying optional dependencies...")
    optional_count = 0
    for import_name, package_name in optional_dependencies:
        if check_package(package_name, import_name):
            optional_count += 1
        else:
            print(f"ℹ {package_name} (optional) - installing...")
            if install_package(package_name):
                optional_count += 1
    
    print(f"\n=== Setup Complete ===")
    print(f"✓ Critical dependencies: {len([d for d in critical_dependencies if check_package(d[1], d[0])])}/{len(critical_dependencies)}")
    print(f"✓ Optional dependencies: {optional_count}/{len(optional_dependencies)}")
    
    if all_critical_installed:
        print("\n🎉 Setup successful! You can now use:")
        print("1. DXF conversion: python python/dxf_to_glb_trimesh.py input.dxf output.glb")
        print("2. File monitoring: python python/dxf_watchdog.py")
        print("3. IFC export: python python/ifc_space_exporter.py (if ifcopenshell installed)")
        print("\nRun the Godot project and load DXF files through the UI!")
        return 0
    else:
        print("\n⚠ Some critical dependencies failed to install.")
        print("Try running: pip install -r python/requirements.txt")
        return 1

if __name__ == "__main__":
    sys.exit(main())