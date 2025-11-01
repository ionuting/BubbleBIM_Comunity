import os
import time
import json
import subprocess
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class DXFHandler(FileSystemEventHandler):
    def __init__(self, watch_folder, output_folder, conversion_script, callback_file):
        self.watch_folder = Path(watch_folder)
        self.output_folder = Path(output_folder)
        self.conversion_script = Path(conversion_script)
        self.callback_file = Path(callback_file)
        self.processing = set()  # Pentru a evita procesarea multiplă
        
    def on_modified(self, event):
        if event.is_directory:
            return
            
        file_path = Path(event.src_path)
        if file_path.suffix.lower() == '.dxf':
            self._process_dxf_file(file_path)
    
    def on_created(self, event):
        if event.is_directory:
            return
            
        file_path = Path(event.src_path)
        if file_path.suffix.lower() == '.dxf':
            # Așteaptă ca fișierul să fie complet scris
            time.sleep(1.0)  # Delay mai mare
            self._process_dxf_file(file_path)
    
    def _process_dxf_file(self, dxf_path):
        if str(dxf_path) in self.processing:
            return
            
        self.processing.add(str(dxf_path))
        
        try:
            print(f"[WATCHDOG] DXF file changed: {dxf_path}")
            
            # Verifică că fișierul este complet scris
            self._wait_for_file_complete(dxf_path)
            
            # Calculează calea de output
            glb_path = self.output_folder / (dxf_path.stem + ".glb")
            
            # Șterge GLB-ul vechi și cache-ul Godot
            self._clear_old_files(glb_path)
            
            # Rulează conversia DXF → GLB
            print(f"[WATCHDOG] Converting {dxf_path} → {glb_path}")
            result = subprocess.run([
                "python", 
                str(self.conversion_script),
                str(dxf_path),
                str(glb_path)
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"[WATCHDOG] Conversion successful")
                
                # Așteaptă ca GLB-ul să fie complet scris
                self._wait_for_file_complete(glb_path)
                
                # Notifică Godot despre schimbare
                self._notify_godot_reload(dxf_path, glb_path)
            else:
                print(f"[WATCHDOG] Conversion failed: {result.stderr}")
                
        except Exception as e:
            print(f"[WATCHDOG] Error processing {dxf_path}: {e}")
        finally:
            self.processing.discard(str(dxf_path))
    
    def _wait_for_file_complete(self, file_path):
        """Așteaptă ca fișierul să fie complet scris verificând dimensiunea stabilă"""
        max_wait = 5  # secunde
        stable_time = 0.5  # secunde de stabilitate
        
        last_size = -1
        stable_start = None
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            try:
                current_size = file_path.stat().st_size
                if current_size == last_size:
                    if stable_start is None:
                        stable_start = time.time()
                    elif time.time() - stable_start >= stable_time:
                        print(f"[WATCHDOG] File stable: {file_path} ({current_size} bytes)")
                        return
                else:
                    stable_start = None
                    last_size = current_size
                
                time.sleep(0.1)
            except Exception:
                time.sleep(0.1)
        
        print(f"[WATCHDOG] File wait timeout: {file_path}")
    
    def _notify_godot_reload(self, dxf_path, glb_path):
        """Scrie un signal file pentru Godot să știe că trebuie să reîncarce"""
        signal_data = {
            "timestamp": time.time(),
            "dxf_file": str(dxf_path),
            "glb_file": str(glb_path),
            "action": "reload"
        }
        
        try:
            with open(self.callback_file, 'w') as f:
                json.dump(signal_data, f, indent=2)
            print(f"[WATCHDOG] Godot notified via {self.callback_file}")
        except Exception as e:
            print(f"[WATCHDOG] Failed to notify Godot: {e}")
    
    def _clear_old_files(self, glb_path):
        """Șterge fișierele vechi și cache-ul Godot complet"""
        files_deleted = []
        
        # Șterge GLB-ul vechi
        if glb_path.exists():
            glb_path.unlink()
            files_deleted.append(f"GLB: {glb_path.name}")
        
        # Șterge fișierul de import Godot (.glb.import)
        import_file = Path(str(glb_path) + ".import")
        if import_file.exists():
            import_file.unlink()
            files_deleted.append(f"Import: {import_file.name}")
        
        # Șterge fișierul de mapping JSON și import-ul său
        mapping_file = glb_path.with_suffix("_mapping.json")
        if mapping_file.exists():
            mapping_file.unlink()
            files_deleted.append(f"Mapping: {mapping_file.name}")
        
        mapping_import = Path(str(mapping_file) + ".import")
        if mapping_import.exists():
            mapping_import.unlink()
            files_deleted.append(f"Mapping import: {mapping_import.name}")
        
        # Încearcă să șteargă din .godot/imported/
        try:
            project_folder = glb_path.parent.parent  # Presupun că GLB e în subfolder
            godot_imported = project_folder / ".godot" / "imported"
            if godot_imported.exists():
                # Caută fișiere care conțin numele GLB-ului
                glb_stem = glb_path.stem
                for imported_file in godot_imported.iterdir():
                    if glb_stem in imported_file.name:
                        imported_file.unlink()
                        files_deleted.append(f"Godot cache: {imported_file.name}")
        except Exception as e:
            print(f"[WATCHDOG] Warning: Could not clean .godot/imported/: {e}")
        
        if files_deleted:
            print(f"[WATCHDOG] ✓ Cleaned files: {', '.join(files_deleted)}")
        else:
            print(f"[WATCHDOG] No old files to clean for: {glb_path.name}")

def main():
    # Configurație
    watch_folders = [
        r"C:\Users\ionut.ciuntuc\Documents\viewer2d\dxf_input",
        r"C:\Users\ionut.ciuntuc\Documents\viewer2d\python\dxf"
    ]
    output_folder = r"C:\Users\ionut.ciuntuc\Documents\viewer2d\glb_output" 
    conversion_script = r"C:\Users\ionut.ciuntuc\Documents\viewer2d\python\dxf_to_glb_trimesh.py"
    callback_file = r"C:\Users\ionut.ciuntuc\Documents\viewer2d\reload_signal.json"
    
    # Crează folderele dacă nu există
    for folder in watch_folders:
        Path(folder).mkdir(exist_ok=True)
    Path(output_folder).mkdir(exist_ok=True)
    
    # Configurează watchdog pentru fiecare folder
    observer = Observer()
    for watch_folder in watch_folders:
        event_handler = DXFHandler(watch_folder, output_folder, conversion_script, callback_file)
        observer.schedule(event_handler, watch_folder, recursive=True)
        print(f"[WATCHDOG] Starting monitoring of {watch_folder}")
    
    print(f"[WATCHDOG] Output folder: {output_folder}")
    print(f"[WATCHDOG] Press Ctrl+C to stop")
    
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("[WATCHDOG] Stopped")
    
    observer.join()

if __name__ == "__main__":
    main()