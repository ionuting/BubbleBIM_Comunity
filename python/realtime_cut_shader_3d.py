#!/usr/bin/env python3
# realtime_cut_shader_3d.py
# Scriptul Python pentru integrarea cut shader cu viewerul 3D Godot
import sys
import json
import os
from pathlib import Path
import numpy as np
import trimesh
import ezdxf
from ezdxf import colors
from ezdxf.math import Vec3
import time
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import argparse

@dataclass
class CutPlane3D:
    """Plan de secțiune 3D pentru viewerul CAD"""
    name: str
    origin: np.ndarray
    normal: np.ndarray
    active: bool = True
    depth_range: tuple = (0.0, 3.0)
    
    def __post_init__(self):
        # Asigură-te că origin și normal sunt numpy arrays
        if isinstance(self.origin, dict):
            self.origin = np.array([
                self.origin.get('x', 0),
                self.origin.get('y', 0), 
                self.origin.get('z', 0)
            ], dtype=np.float32)
        elif isinstance(self.origin, (list, tuple)):
            self.origin = np.array(self.origin, dtype=np.float32)
        
        if isinstance(self.normal, dict):
            self.normal = np.array([
                self.normal.get('x', 0),
                self.normal.get('y', 0),
                self.normal.get('z', 1)
            ], dtype=np.float32)
        elif isinstance(self.normal, (list, tuple)):
            self.normal = np.array(self.normal, dtype=np.float32)
        
        # Normalizează vectorul normal
        if np.linalg.norm(self.normal) > 0:
            self.normal = self.normal / np.linalg.norm(self.normal)

class CutShader3DProcessor:
    """Procesor optimizat pentru cut shader 3D în timp real"""
    
    def __init__(self):
        self.glb_cache = {}
        self.performance_mode = True
        self.max_vertices = 50000  # Limită pentru performanță
        
    def find_glb_files(self, search_paths: List[str] = None) -> List[str]:
        """Caută fișiere GLB în directoarele specificate"""
        if search_paths is None:
            search_paths = ["."]
        
        glb_files = []
        for search_path in search_paths:
            path = Path(search_path)
            if path.exists():
                # Caută recursive
                glb_files.extend(path.glob("**/*.glb"))
        
        return [str(f) for f in glb_files]
    
    def load_glb_optimized(self, glb_path: str) -> Optional[trimesh.Trimesh]:
        """Încarcă GLB cu optimizări pentru performanță"""
        try:
            # Verifică cache-ul
            if glb_path in self.glb_cache:
                print(f"[Cache] Using cached mesh: {Path(glb_path).name}")
                return self.glb_cache[glb_path]
            
            print(f"[Load] Loading GLB: {Path(glb_path).name}")
            
            # Încarcă fișierul
            scene = trimesh.load(glb_path)
            
            if isinstance(scene, trimesh.Scene):
                # Combină toate geometriile din scenă
                meshes = [geom for geom in scene.geometry.values() 
                         if isinstance(geom, trimesh.Trimesh)]
                
                if meshes:
                    if len(meshes) == 1:
                        mesh = meshes[0]
                    else:
                        mesh = trimesh.util.concatenate(meshes)
                else:
                    print(f"[Warning] No valid meshes found in {glb_path}")
                    return None
            else:
                mesh = scene
            
            if not isinstance(mesh, trimesh.Trimesh):
                print(f"[Warning] Invalid mesh type in {glb_path}")
                return None
            
            # Optimizează pentru performanță dacă mesh-ul e prea mare
            if len(mesh.vertices) > self.max_vertices:
                print(f"[Optimize] Simplifying large mesh: {len(mesh.vertices)} -> ", end="")
                mesh = mesh.simplify_quadric_decimation(self.max_vertices)
                print(f"{len(mesh.vertices)} vertices")
            
            # Adaugă în cache
            self.glb_cache[glb_path] = mesh
            
            return mesh
            
        except Exception as e:
            print(f"[Error] Failed to load {glb_path}: {e}")
            return None
    
    def apply_cut_shader_fast(self, mesh: trimesh.Trimesh, plane: CutPlane3D) -> Dict[str, Any]:
        """Aplică cut shader rapid pentru mesh"""
        if not isinstance(mesh, trimesh.Trimesh) or len(mesh.vertices) == 0:
            return {"edges": [], "points": [], "plane_name": plane.name}
        
        vertices = mesh.vertices
        faces = mesh.faces
        
        # Calculează distanțele la plan (vectorizat)
        plane_distances = np.dot(vertices - plane.origin, plane.normal)
        
        # Găsește fețele care intersectează planul
        face_distances = plane_distances[faces]  # Shape: (n_faces, 3)
        
        # Identifică fețele care traversează planul
        min_dists = np.min(face_distances, axis=1)
        max_dists = np.max(face_distances, axis=1)
        
        # Fețele care au vârfuri pe ambele părți ale planului
        crossing_mask = (min_dists <= 0.01) & (max_dists >= -0.01)
        crossing_faces = faces[crossing_mask]
        crossing_distances = face_distances[crossing_mask]
        
        if len(crossing_faces) == 0:
            return {"edges": [], "points": [], "plane_name": plane.name}
        
        # Extrage punctele și muchiile de intersecție
        intersection_points = []
        intersection_edges = []
        
        for face_idx, (face, dists) in enumerate(zip(crossing_faces, crossing_distances)):
            intersections = []
            
            # Verifică fiecare muchie a feței pentru intersecție
            for i in range(3):
                j = (i + 1) % 3
                d1, d2 = dists[i], dists[j]
                
                # Dacă distanțele au semne opuse, muchia intersectează planul
                if d1 * d2 < 0:
                    # Calculează punctul de intersecție
                    t = d1 / (d1 - d2)
                    v1, v2 = vertices[face[i]], vertices[face[j]]
                    intersection_point = v1 + t * (v2 - v1)
                    intersections.append(intersection_point)
            
            # Adaugă punctele și muchiile găsite
            if len(intersections) >= 2:
                start_idx = len(intersection_points)
                intersection_points.extend(intersections[:2])
                intersection_edges.append([start_idx, start_idx + 1])
        
        return {
            "edges": intersection_edges,
            "points": intersection_points,
            "plane_name": plane.name
        }
    
    def process_cut_shader_3d(self, planes: List[CutPlane3D], 
                             glb_files: List[str],
                             depth_layers: List[float] = None) -> Dict[str, Any]:
        """Procesează cut shader pentru toate planurile și mesh-urile"""
        
        if depth_layers is None:
            depth_layers = [1.0, 2.0, 3.0]
        
        print(f"[Process] Processing {len(planes)} planes with {len(glb_files)} GLB files")
        print(f"[Process] Depth layers: {depth_layers}")
        
        start_time = time.time()
        results = {}
        
        # Încarcă toate mesh-urile
        meshes = []
        for glb_file in glb_files:
            mesh = self.load_glb_optimized(glb_file)
            if mesh:
                meshes.append((glb_file, mesh))
        
        print(f"[Process] Loaded {len(meshes)} valid meshes")
        
        # Procesează fiecare plan
        for plane in planes:
            if not plane.active:
                continue
            
            plane_start = time.time()
            plane_results = []
            
            for glb_file, mesh in meshes:
                result = self.apply_cut_shader_fast(mesh, plane)
                
                if len(result["edges"]) > 0:
                    result["source_file"] = Path(glb_file).name
                    result["glb_path"] = glb_file
                    
                    # Adaugă informații despre straturile de adâncime
                    if result["points"]:
                        points = np.array(result["points"])
                        avg_z = np.mean(points[:, 2])
                        
                        # Determină stratul de adâncime
                        depth_layer = 0
                        for i, depth in enumerate(sorted(depth_layers)):
                            if avg_z <= depth:
                                depth_layer = i
                                break
                        
                        result["depth_layer"] = depth_layer
                        result["avg_depth"] = float(avg_z)
                    
                    plane_results.append(result)
            
            results[plane.name] = plane_results
            processing_time = time.time() - plane_start
            print(f"[Process] Plane '{plane.name}': {len(plane_results)} intersections in {processing_time:.2f}s")
        
        total_time = time.time() - start_time
        print(f"[Process] Total processing time: {total_time:.2f}s")
        
        return results
    
    def export_to_dxf_advanced(self, results: Dict[str, Any], 
                              output_path: str,
                              depth_layers: List[float] = None) -> str:
        """Exportă rezultatele în format DXF cu organizare avansată pe layere"""
        
        if depth_layers is None:
            depth_layers = [1.0, 2.0, 3.0]
        
        print(f"[DXF] Creating DXF file: {output_path}")
        
        # Creează documentul DXF
        doc = ezdxf.new('R2010')
        msp = doc.modelspace()
        
        # Definește layerele și culorile
        layer_config = {
            'SECTION_MAIN': {'color': colors.RED, 'description': 'Main section lines'},
            'SECTION_DETAIL': {'color': colors.YELLOW, 'description': 'Detail lines'},
            'SECTION_HIDDEN': {'color': colors.CYAN, 'description': 'Hidden edges'},
            'SECTION_CUT': {'color': colors.WHITE, 'description': 'Cut edges'},
        }
        
        # Adaugă layere pentru fiecare nivel de adâncime
        for i, depth in enumerate(sorted(depth_layers)):
            layer_name = f'DEPTH_{depth:.1f}'
            # Folosește culori standard ACI în loc de by_aci()
            color_index = 40 + (i * 20) % 200  # Asigură că indexul e în limitele ACI
            layer_config[layer_name] = {
                'color': color_index,  # Folosește direct indexul ACI
                'description': f'Depth layer at Z={depth:.1f}'
            }
        
        # Creează layerele în DXF
        for layer_name, config in layer_config.items():
            doc.layers.new(
                name=layer_name,
                dxfattribs={'color': config['color']}
            )
        
        entity_count = 0
        total_points = 0
        
        # Procesează rezultatele pentru fiecare plan
        for plane_name, plane_results in results.items():
            print(f"[DXF] Processing plane: {plane_name}")
            
            for mesh_result in plane_results:
                edges = mesh_result.get("edges", [])
                points = mesh_result.get("points", [])
                depth_layer = mesh_result.get("depth_layer", 0)
                source_file = mesh_result.get("source_file", "unknown")
                
                if not edges or not points:
                    continue
                
                # Determină layer-ul bazat pe adâncime
                if depth_layer < len(depth_layers):
                    layer_name = f'DEPTH_{depth_layers[depth_layer]:.1f}'
                else:
                    layer_name = 'SECTION_MAIN'
                
                # Convertește punctele la numpy array dacă nu sunt deja
                if not isinstance(points, np.ndarray):
                    points = np.array(points)
                
                # Adaugă liniile în DXF
                for edge in edges:
                    if len(edge) >= 2:
                        try:
                            start_point = points[edge[0]]
                            end_point = points[edge[1]]
                            
                            # Adaugă linia la DXF
                            msp.add_line(
                                start=(float(start_point[0]), float(start_point[1])),
                                end=(float(end_point[0]), float(end_point[1])),
                                dxfattribs={
                                    'layer': layer_name
                                }
                            )
                            entity_count += 1
                            
                        except (IndexError, ValueError) as e:
                            print(f"[Warning] Skipping invalid edge: {e}")
                            continue
                
                total_points += len(points)
        
        # Adaugă text cu informații despre secțiune
        info_text = f"Cut Shader Section Export - Planes: {len(results)} - Entities: {entity_count} - Points: {total_points}"
        text_entity = msp.add_text(
            info_text,
            dxfattribs={
                'layer': 'SECTION_MAIN',
                'height': 2.5
            }
        )
        text_entity.set_placement((10, 10))
        
        # Salvează fișierul DXF
        doc.saveas(output_path)
        
        # Statistici finale
        file_size = Path(output_path).stat().st_size
        print(f"[DXF] Export complete:")
        print(f"  - File: {output_path}")
        print(f"  - Size: {file_size} bytes") 
        print(f"  - Entities: {entity_count}")
        print(f"  - Layers: {len(layer_config)}")
        
        return output_path

def load_parameters_from_godot(json_path: str) -> Dict[str, Any]:
    """Încarcă parametrii din fișierul JSON generat de Godot"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print(f"[Params] Loaded parameters from: {json_path}")
        print(f"[Params] Planes: {len(data.get('planes', []))}")
        print(f"[Params] Depth layers: {data.get('depth_layers', [])}")
        
        return data
        
    except Exception as e:
        print(f"[Error] Failed to load parameters: {e}")
        return {}

def convert_godot_planes(godot_planes: List[Dict]) -> List[CutPlane3D]:
    """Convertește planurile din formatul Godot în CutPlane3D"""
    cut_planes = []
    
    for i, plane_data in enumerate(godot_planes):
        try:
            cut_plane = CutPlane3D(
                name=plane_data.get("name", f"Section_{i}"),
                origin=plane_data.get("origin", {"x": 0, "y": 0, "z": 0}),
                normal=plane_data.get("normal", {"x": 0, "y": 0, "z": 1}),
                active=plane_data.get("active", True),
                depth_range=tuple(plane_data.get("depth_range", [0.0, 3.0]))
            )
            
            cut_planes.append(cut_plane)
            print(f"[Convert] Plane '{cut_plane.name}': origin={cut_plane.origin}, normal={cut_plane.normal}")
            
        except Exception as e:
            print(f"[Warning] Failed to convert plane {i}: {e}")
            continue
    
    return cut_planes

def main():
    parser = argparse.ArgumentParser(description="Cut Shader 3D processor for Godot integration")
    parser.add_argument("params_file", help="JSON parameters file from Godot")
    parser.add_argument("--preview", action="store_true", help="Preview mode (faster processing)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    print(f"[Main] Cut Shader 3D processor starting...")
    print(f"[Main] Parameters file: {args.params_file}")
    print(f"[Main] Preview mode: {args.preview}")
    
    # Încarcă parametrii
    params = load_parameters_from_godot(args.params_file)
    if not params:
        print("[Error] No valid parameters loaded")
        return 1
    
    # Inițializează procesorul
    processor = CutShader3DProcessor()
    processor.performance_mode = args.preview
    
    # Convertește planurile
    godot_planes = params.get("planes", [])
    cut_planes = convert_godot_planes(godot_planes)
    
    if not cut_planes:
        print("[Error] No valid cut planes found")
        return 1
    
    # Caută fișiere GLB
    glb_files = processor.find_glb_files(["."])
    if not glb_files:
        print("[Warning] No GLB files found in current directory")
        # Încearcă în subdirectoare comune
        common_dirs = ["models", "assets", "glb", "meshes"]
        for dir_name in common_dirs:
            if Path(dir_name).exists():
                glb_files.extend(processor.find_glb_files([dir_name]))
    
    if not glb_files:
        print("[Error] No GLB files found")
        return 1
    
    print(f"[Main] Found {len(glb_files)} GLB files")
    if args.verbose:
        for glb_file in glb_files[:10]:  # Show first 10
            print(f"  - {glb_file}")
    
    # Procesează cut shader
    depth_layers = params.get("depth_layers", [1.0, 2.0, 3.0])
    results = processor.process_cut_shader_3d(cut_planes, glb_files, depth_layers)
    
    if not results:
        print("[Warning] No results generated")
        return 0
    
    # Exportă rezultatele
    output_dir = Path(params.get("output_dir", "."))
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = int(time.time())
    mode_suffix = "preview" if args.preview else "export"
    output_file = output_dir / f"cut_shader_3d_{mode_suffix}_{timestamp}.dxf"
    
    try:
        result_path = processor.export_to_dxf_advanced(
            results,
            str(output_file),
            depth_layers
        )
        
        # Output pentru Godot
        print(f"RESULT_FILE:{result_path}")
        print(f"SUCCESS:Cut shader 3D {'preview' if args.preview else 'export'} completed successfully")
        
        return 0
        
    except Exception as e:
        print(f"[Error] Export failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())