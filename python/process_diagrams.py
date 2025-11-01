#!/usr/bin/env python3
"""
Process Diagram.xml files and integrate them into the Godot viewer project.

Usage:
    python process_diagrams.py scan [root_folder]
    python process_diagrams.py load [manifest_path]
    python process_diagrams.py watch [root_folder]  # Watch for changes
"""

import sys
import os
import time
from pathlib import Path
import json
from graph_to_glb import scan_and_process_diagrams, generate_project_manifest, load_project_models


def scan_and_import(root_folder: str, project_root: str = None):
    """
    Scanează folderele pentru Diagram.xml și copiază GLB-urile în proiect
    
    Args:
        root_folder: Folderul pentru scanare
        project_root: Folderul rădăcină al proiectului Godot
    """
    if project_root is None:
        # Presupunem că scriptul e în python/, proiectul e în ../
        script_dir = Path(__file__).parent
        project_root = script_dir.parent
    
    project_root = Path(project_root)
    output_folder = project_root / "diagrams_output"
    output_folder.mkdir(exist_ok=True)
    
    print(f"[SCAN] Scanning: {root_folder}")
    print(f"[SCAN] Output to: {output_folder}")
    
    # Procesează toate Diagram.xml
    processed = scan_and_process_diagrams(root_folder, str(output_folder))
    
    if not processed:
        print("[SCAN] No Diagram.xml files found or processed")
        return
    
    # Generează manifest în folderul proiectului
    manifest_path = output_folder / "diagrams_manifest.json"
    manifest = generate_project_manifest(processed, str(manifest_path))
    
    print(f"\n[IMPORT] Processed {len(processed)} diagram files")
    print(f"[IMPORT] Manifest: {manifest_path}")
    print(f"[IMPORT] GLB files are ready to load in Godot viewer")
    
    return manifest


def watch_folder(root_folder: str, project_root: str = None, interval: int = 5):
    """
    Monitorizează folder-ul pentru modificări în Diagram.xml și re-procesează automat
    
    Args:
        root_folder: Folderul de monitorizat
        project_root: Folderul proiectului Godot
        interval: Interval de verificare în secunde
    """
    if project_root is None:
        script_dir = Path(__file__).parent
        project_root = script_dir.parent
    
    project_root = Path(project_root)
    root_path = Path(root_folder)
    
    print(f"[WATCH] Monitoring: {root_folder}")
    print(f"[WATCH] Press Ctrl+C to stop")
    
    # Stocăm timestamp-urile fișierelor
    file_timestamps = {}
    
    def get_diagram_files():
        return list(root_path.rglob("Diagram.xml"))
    
    def update_timestamps():
        files = get_diagram_files()
        timestamps = {}
        for f in files:
            try:
                timestamps[str(f)] = f.stat().st_mtime
            except Exception:
                pass
        return timestamps
    
    # Inițializează timestamp-urile
    file_timestamps = update_timestamps()
    print(f"[WATCH] Found {len(file_timestamps)} Diagram.xml files")
    
    # Procesează inițial
    scan_and_import(root_folder, str(project_root))
    
    try:
        while True:
            time.sleep(interval)
            
            # Verifică modificări
            current_timestamps = update_timestamps()
            
            # Verifică fișiere noi sau modificate
            changed = False
            for file_path, timestamp in current_timestamps.items():
                if file_path not in file_timestamps or file_timestamps[file_path] != timestamp:
                    print(f"\n[WATCH] Detected change: {file_path}")
                    changed = True
            
            # Verifică fișiere șterse
            for file_path in file_timestamps:
                if file_path not in current_timestamps:
                    print(f"\n[WATCH] Detected deletion: {file_path}")
                    changed = True
            
            if changed:
                print("[WATCH] Re-processing...")
                file_timestamps = current_timestamps
                scan_and_import(root_folder, str(project_root))
                print("[WATCH] Update complete")
    
    except KeyboardInterrupt:
        print("\n[WATCH] Stopped monitoring")


def list_models(manifest_path: str = None):
    """
    Listează modelele din manifest
    """
    if manifest_path is None:
        script_dir = Path(__file__).parent
        project_root = script_dir.parent
        manifest_path = str(project_root / "diagrams_output" / "diagrams_manifest.json")
    
    models = load_project_models(manifest_path)
    
    if not models:
        print("[LIST] No models found in manifest")
        return
    
    print(f"\n[LIST] Found {len(models)} models:")
    for i, model in enumerate(models, 1):
        print(f"\n{i}. {model['name']}")
        print(f"   Source: {model['xml_source']}")
        print(f"   GLB: {model['glb_output']}")


def create_godot_autoload_script(project_root: str = None):
    """
    Creează un script GDScript pentru autoload în Godot care încarcă automat diagramele
    """
    if project_root is None:
        script_dir = Path(__file__).parent
        project_root = script_dir.parent
    
    project_root = Path(project_root)
    autoload_script = project_root / "diagram_loader.gd"
    
    script_content = '''# Auto-generated script for loading Diagram.xml models
extends Node

var models_loaded: bool = false
var models_info: Array = []

func _ready():
	print("[DiagramLoader] Ready to load diagram models")

func load_all_diagrams() -> Array:
	"""Load all diagram models from manifest"""
	var manifest_path = "res://diagrams_output/diagrams_manifest.json"
	
	if not FileAccess.file_exists(manifest_path):
		push_warning("Diagram manifest not found: %s" % manifest_path)
		return []
	
	var file = FileAccess.open(manifest_path, FileAccess.READ)
	if not file:
		push_error("Failed to open manifest: %s" % manifest_path)
		return []
	
	var json_text = file.get_as_text()
	file.close()
	
	var json = JSON.new()
	var parse_result = json.parse(json_text)
	
	if parse_result != OK:
		push_error("Failed to parse manifest JSON")
		return []
	
	var manifest = json.get_data()
	models_info = manifest.get("models", [])
	
	print("[DiagramLoader] Found %d diagram models" % models_info.size())
	models_loaded = true
	
	return models_info

func get_model_glb_path(model_name: String) -> String:
	"""Get GLB path for a specific model by name"""
	if not models_loaded:
		load_all_diagrams()
	
	for model in models_info:
		if model.get("name", "") == model_name:
			var glb_path = model.get("relative_path", "")
			if glb_path:
				return "res://" + glb_path.replace("\\\\", "/")
	
	return ""

func get_all_model_names() -> Array:
	"""Get list of all model names"""
	if not models_loaded:
		load_all_diagrams()
	
	var names = []
	for model in models_info:
		names.append(model.get("name", "Unknown"))
	
	return names
'''
    
    with open(autoload_script, 'w', encoding='utf-8') as f:
        f.write(script_content)
    
    print(f"[GODOT] Created autoload script: {autoload_script}")
    print("[GODOT] Add this to your project.godot:")
    print('         [autoload]')
    print('         DiagramLoader="*res://diagram_loader.gd"')


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python process_diagrams.py scan [root_folder] [project_root]")
        print("  python process_diagrams.py load [manifest_path]")
        print("  python process_diagrams.py watch [root_folder] [project_root]")
        print("  python process_diagrams.py godot-script [project_root]")
        return
    
    command = sys.argv[1]
    
    if command == "scan":
        root_folder = sys.argv[2] if len(sys.argv) > 2 else "."
        project_root = sys.argv[3] if len(sys.argv) > 3 else None
        scan_and_import(root_folder, project_root)
    
    elif command == "load":
        manifest_path = sys.argv[2] if len(sys.argv) > 2 else None
        list_models(manifest_path)
    
    elif command == "watch":
        root_folder = sys.argv[2] if len(sys.argv) > 2 else "."
        project_root = sys.argv[3] if len(sys.argv) > 3 else None
        watch_folder(root_folder, project_root)
    
    elif command == "godot-script":
        project_root = sys.argv[2] if len(sys.argv) > 2 else None
        create_godot_autoload_script(project_root)
    
    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
