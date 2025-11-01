"""
Integrare IFC Direct Exporter în pipeline-ul principal DXF to IFC.
Permite conversia directă din DXF în IFC fără GLB intermediar.
"""

import os
import sys
from pathlib import Path
import json
from typing import List, Dict, Any

# Import convertorul principal 
sys.path.append(os.path.join(os.path.dirname(__file__), "."))
try:
    from dxf_to_glb_trimesh import (
        extract_global_z_from_filename,
        read_control_circles,
        dxf_to_gltf
    )
    from ifc_direct_exporter import IFCDirectExporter, create_multi_level_ifc_from_dxf_data
    
    print("[DEBUG] IFC Direct integration loaded successfully")
except ImportError as e:
    print(f"[ERROR] Failed to import required modules: {e}")
    sys.exit(1)

import ezdxf


def process_single_dxf_for_ifc(dxf_path: str, force_global_z: float = None) -> Dict[str, Any]:
    """
    Procesează un singur fișier DXF și extrage datele pentru IFC direct.
    
    Args:
        dxf_path: Calea către fișierul DXF
        force_global_z: Forțează o valoare Z specifică (opțional)
        
    Returns:
        Dict cu datele procesate pentru IFC
    """
    
    try:
        print(f"[DEBUG] Processing DXF for IFC: {dxf_path}")
        
        # Extrage global Z din filename sau folosește valoarea forțată
        if force_global_z is not None:
            global_z = force_global_z
        else:
            global_z = extract_global_z_from_filename(dxf_path)
        
        # Procesează DXF-ul prin convertorul existent pentru a obține mapping-ul
        temp_glb = dxf_path.replace('.dxf', '_temp_for_ifc.glb')
        temp_mapping = dxf_path.replace('.dxf', '_temp_for_ifc_mapping.json')
        
        try:
            # Rulează conversia completă pentru a obține mapping-ul
            result = dxf_to_gltf(dxf_path, temp_glb, arc_segments=16)
            
            # Citește mapping-ul generat
            if os.path.exists(temp_mapping):
                with open(temp_mapping, 'r', encoding='utf-8') as f:
                    mapping_data = json.load(f)
                
                # Curăță fișierele temporare
                for temp_file in [temp_glb, temp_mapping]:
                    if os.path.exists(temp_file):
                        try:
                            os.remove(temp_file)
                        except:
                            pass
                
                # Returnează datele procesate
                return {
                    "filename": os.path.basename(dxf_path),
                    "full_path": dxf_path,
                    "global_z": global_z,
                    "elements": mapping_data,
                    "element_count": len(mapping_data)
                }
            else:
                print(f"[ERROR] No mapping file generated for {dxf_path}")
                return None
                
        except Exception as e:
            print(f"[ERROR] Failed to process DXF {dxf_path}: {e}")
            return None
            
    except Exception as e:
        print(f"[ERROR] Failed to process DXF for IFC {dxf_path}: {e}")
        return None


def convert_multiple_dxf_to_single_ifc(
    dxf_files: List[str], 
    output_ifc_path: str,
    project_name: str = None,
    global_z_overrides: Dict[str, float] = None
) -> bool:
    """
    Convertește multiple fișiere DXF într-un singur model IFC cu nivele separate.
    
    Args:
        dxf_files: Lista cu căile către fișierele DXF
        output_ifc_path: Calea de export pentru fișierul IFC
        project_name: Numele proiectului (opțional)
        global_z_overrides: Dict cu overrides pentru Z-urile globale {filename: z_value}
        
    Returns:
        bool: True dacă conversia a reușit
    """
    
    try:
        # Generează numele proiectului dacă nu e specificat
        if not project_name:
            project_name = f"Multi-Level Building from {len(dxf_files)} DXF files"
        
        print(f"[DEBUG] Converting {len(dxf_files)} DXF files to IFC: {output_ifc_path}")
        
        # Procesează fiecare fișier DXF
        processed_data = []
        
        for dxf_file in dxf_files:
            if not os.path.exists(dxf_file):
                print(f"[WARNING] DXF file not found: {dxf_file}")
                continue
                
            # Verifică override pentru Z global
            filename = os.path.basename(dxf_file)
            force_z = global_z_overrides.get(filename) if global_z_overrides else None
            
            # Procesează fișierul
            dxf_data = process_single_dxf_for_ifc(dxf_file, force_z)
            
            if dxf_data:
                processed_data.append(dxf_data)
                print(f"[DEBUG] Processed {filename}: {dxf_data['element_count']} elements at Z={dxf_data['global_z']}")
            else:
                print(f"[WARNING] Failed to process {filename}")
        
        if not processed_data:
            print("[ERROR] No DXF files were processed successfully")
            return False
        
        # Sortează datele după global_z pentru ordine corectă a nivelelor
        processed_data.sort(key=lambda x: x['global_z'])
        
        # Creează modelul IFC
        result = create_multi_level_ifc_from_dxf_data(
            processed_data,
            output_ifc_path,
            project_name
        )
        
        if result:
            print(f"[SUCCESS] IFC export completed:")
            print(f"  Project: {result['project_name']}")
            print(f"  Storeys: {result['total_storeys']}")
            print(f"  Elements: {result['total_elements']}")
            
            # Afișează detalii pentru fiecare nivel
            for dxf_file, storey_info in result['storeys'].items():
                print(f"  - {dxf_file}: {storey_info['name']} (Z={storey_info['elevation']:.2f}, {storey_info['element_count']} elements)")
            
            return True
        else:
            print("[ERROR] IFC export failed")
            return False
            
    except Exception as e:
        print(f"[ERROR] Multi-DXF to IFC conversion failed: {e}")
        return False


def convert_dxf_folder_to_ifc(
    dxf_folder: str,
    output_ifc_path: str,
    project_name: str = None,
    dxf_pattern: str = "*.dxf"
) -> bool:
    """
    Convertește toate fișierele DXF dintr-un folder într-un singur model IFC.
    
    Args:
        dxf_folder: Folderul cu fișierele DXF
        output_ifc_path: Calea de export pentru IFC
        project_name: Numele proiectului
        dxf_pattern: Pattern pentru filtrarea fișierelor DXF
        
    Returns:
        bool: True dacă conversia a reușit
    """
    
    try:
        # Găsește toate fișierele DXF din folder
        dxf_folder_path = Path(dxf_folder)
        dxf_files = list(dxf_folder_path.glob(dxf_pattern))
        
        if not dxf_files:
            print(f"[ERROR] No DXF files found in {dxf_folder} with pattern {dxf_pattern}")
            return False
        
        # Convertește path-urile în string-uri
        dxf_file_paths = [str(f) for f in dxf_files]
        
        # Generează numele proiectului din numele folderului dacă nu e specificat
        if not project_name:
            project_name = f"Building from {dxf_folder_path.name}"
        
        print(f"[DEBUG] Found {len(dxf_file_paths)} DXF files in {dxf_folder}")
        
        # Convertește toate fișierele
        return convert_multiple_dxf_to_single_ifc(
            dxf_file_paths,
            output_ifc_path,
            project_name
        )
        
    except Exception as e:
        print(f"[ERROR] Folder to IFC conversion failed: {e}")
        return False


def create_test_multi_dxf_ifc():
    """Creează un test cu multiple fișiere DXF convertite în IFC"""
    
    # Test data - simulează mai multe fișiere DXF
    test_files = [
        "ground_floor_0.00.dxf",
        "first_floor_3.00.dxf", 
        "second_floor_6.00.dxf"
    ]
    
    # În practică acestea ar fi fișiere reale DXF
    # Pentru test, folosim date simulate
    print("[DEBUG] Creating test multi-DXF to IFC conversion")
    
    # Dacă avem fișiere reale în workspace, le folosim
    workspace_dxf = []
    for test_file in test_files:
        if os.path.exists(test_file):
            workspace_dxf.append(test_file)
    
    if workspace_dxf:
        success = convert_multiple_dxf_to_single_ifc(
            workspace_dxf,
            "test_multi_level_direct.ifc",
            "Test Multi-Level Building"
        )
        
        if success:
            print("[SUCCESS] Multi-DXF to IFC test completed!")
        else:
            print("[ERROR] Multi-DXF to IFC test failed!")
    else:
        print("[INFO] No test DXF files found for multi-level test")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "test":
            create_test_multi_dxf_ifc()
        elif sys.argv[1] == "folder" and len(sys.argv) >= 4:
            # python ifc_integration.py folder <input_folder> <output.ifc> [project_name]
            input_folder = sys.argv[2]
            output_ifc = sys.argv[3]
            project_name = sys.argv[4] if len(sys.argv) > 4 else None
            
            success = convert_dxf_folder_to_ifc(input_folder, output_ifc, project_name)
            sys.exit(0 if success else 1)
        elif len(sys.argv) >= 3:
            # python ifc_integration.py <output.ifc> <file1.dxf> [file2.dxf] ...
            output_ifc = sys.argv[1]
            input_dxfs = sys.argv[2:]
            
            success = convert_multiple_dxf_to_single_ifc(input_dxfs, output_ifc)
            sys.exit(0 if success else 1)
    else:
        print("Usage:")
        print("  python ifc_integration.py test")
        print("  python ifc_integration.py <output.ifc> <file1.dxf> [file2.dxf] ...")
        print("  python ifc_integration.py folder <input_folder> <output.ifc> [project_name]")