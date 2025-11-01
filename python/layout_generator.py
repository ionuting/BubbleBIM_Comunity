#!/usr/bin/env python3
"""
Layout Generator - Generare planșe 2D din modele 3D
==================================================

Sistem complet nou pentru generarea de planșe arhitecturale din:
- GLB files (geometria 3D finală)
- JSON mapping (metadata și proprietăți)
- IFC files (structura logică)

Similar cu Revit/ArchiCAD layout system, dar independent de pipeline-ul existent.
"""

import json
import trimesh
import numpy as np
from typing import Dict, List, Any, Tuple, Optional
from pathlib import Path
import svgwrite
from dataclasses import dataclass
from enum import Enum

class ViewType(Enum):
    PLAN = "plan"
    SECTION = "section"
    ELEVATION = "elevation"
    DETAIL = "detail"
    
class LineWeight(Enum):
    THIN = 0.18
    MEDIUM = 0.35
    THICK = 0.7
    EXTRA_THICK = 1.0

@dataclass
class ViewDefinition:
    """Definește un view 2D dintr-un model 3D"""
    name: str
    view_type: ViewType
    camera_position: Tuple[float, float, float]
    camera_target: Tuple[float, float, float]
    camera_up: Tuple[float, float, float]
    scale: float = 100.0  # 1:100
    clipping_planes: List[Dict] = None
    visible_layers: List[str] = None
    annotation_scale: float = 1.0
    
    def __post_init__(self):
        if self.clipping_planes is None:
            self.clipping_planes = []
        if self.visible_layers is None:
            self.visible_layers = ["IfcWall", "IfcColumn", "IfcBeam", "IfcSlab"]

@dataclass 
class Viewport:
    """Un viewport pe o planșă"""
    view_definition: ViewDefinition
    position: Tuple[float, float]  # Position on sheet in mm
    size: Tuple[float, float]      # Size in mm
    border: bool = True
    title: str = ""

@dataclass
class Sheet:
    """O planșă completă"""
    id: str
    title: str
    size: str = "A1"  # A0, A1, A2, A3, A4
    scale: str = "1:100"
    viewports: List[Viewport] = None
    
    def __post_init__(self):
        if self.viewports is None:
            self.viewports = []

class LayoutGenerator:
    """Generator principal pentru planșe 2D"""
    
    def __init__(self):
        self.paper_sizes = {
            "A0": (841, 1189),
            "A1": (594, 841), 
            "A2": (420, 594),
            "A3": (297, 420),
            "A4": (210, 297)
        }
        
        self.line_styles = {
            "cut_line": {"weight": LineWeight.THICK.value, "color": "black", "dash": None},
            "edge_line": {"weight": LineWeight.MEDIUM.value, "color": "black", "dash": None},
            "hidden_line": {"weight": LineWeight.THIN.value, "color": "gray", "dash": "3,2"},
            "center_line": {"weight": LineWeight.THIN.value, "color": "blue", "dash": "10,5,2,5"}
        }
        
        self.layer_styles = {
            "IfcWall": {"line_type": "cut_line", "hatch": "brick"},
            "IfcColumn": {"line_type": "cut_line", "hatch": "concrete"}, 
            "IfcBeam": {"line_type": "cut_line", "hatch": "concrete"},
            "IfcSlab": {"line_type": "cut_line", "hatch": "concrete"},
            "IfcWindow": {"line_type": "edge_line", "hatch": None},
            "IfcSpace": {"line_type": "hidden_line", "hatch": None}
        }
    
    def load_3d_data(self, glb_path: str, json_mapping_path: str) -> Dict[str, Any]:
        """Încarcă datele 3D din GLB și JSON mapping"""
        try:
            print(f"[DEBUG] Loading 3D data from: {glb_path}")
            
            # Verifică dacă fișierul există
            if not Path(glb_path).exists():
                print(f"[ERROR] GLB file not found: {glb_path}")
                return {'meshes': [], 'metadata': {}, 'bounds': None}
            
            # Încarcă GLB
            scene = trimesh.load(str(glb_path))
            meshes = []
            
            if hasattr(scene, 'geometry'):
                for name, mesh in scene.geometry.items():
                    if hasattr(mesh, 'vertices') and len(mesh.vertices) > 0:
                        # UUID will be matched by mesh name in JSON
                        meshes.append({
                            'name': name,
                            'vertices': mesh.vertices,
                            'faces': mesh.faces,
                            'bounds': mesh.bounds
                        })
            
            # Încarcă JSON mapping și asociază cu meshes
            metadata = {}
            if Path(json_mapping_path).exists():
                with open(json_mapping_path, 'r', encoding='utf-8') as f:
                    json_data = json.load(f)
                
                print(f"[DEBUG] JSON entries: {len(json_data)}")
                
                # Create mapping by mesh name
                name_to_metadata = {}
                for entry in json_data:
                    if 'mesh_name' in entry:
                        name_to_metadata[entry['mesh_name']] = entry
                        print(f"[DEBUG] Mapped: {entry['mesh_name']} -> {entry['uuid']}")
                
                # Associate meshes with metadata
                for mesh in meshes:
                    mesh_name = mesh['name']
                    print(f"[DEBUG] Looking for mesh: {mesh_name}")
                    if mesh_name in name_to_metadata:
                        mesh['metadata'] = name_to_metadata[mesh_name]
                        mesh['uuid'] = name_to_metadata[mesh_name]['uuid']
                        metadata[mesh['uuid']] = name_to_metadata[mesh_name]
                        print(f"[DEBUG] Found match: {mesh_name} -> {mesh['uuid']}")
                    else:
                        # Fallback: use mesh name as UUID if no mapping found
                        mesh['uuid'] = f"unknown-{mesh_name}"
                        print(f"[DEBUG] No mapping found for {mesh_name}, using fallback UUID")
            
            print(f"[DEBUG] Loaded {len(meshes)} meshes and {len(metadata)} metadata entries")
            
            return {
                'meshes': meshes,
                'metadata': metadata,
                'bounds': self._calculate_overall_bounds(meshes)
            }
            
        except Exception as e:
            print(f"[ERROR] Failed to load 3D data: {e}")
            return {'meshes': [], 'metadata': {}, 'bounds': None}
    
    def _calculate_overall_bounds(self, meshes: List[Dict]) -> Optional[np.ndarray]:
        """Calculează bounds-urile generale ale modelului"""
        if not meshes:
            return None
            
        all_bounds = [mesh['bounds'] for mesh in meshes if 'bounds' in mesh]
        if not all_bounds:
            return None
            
        min_coords = np.min([bounds[0] for bounds in all_bounds], axis=0)
        max_coords = np.max([bounds[1] for bounds in all_bounds], axis=0)
        
        return np.array([min_coords, max_coords])
    
    def create_plan_view(self, name: str, z_level: float = 1.5) -> ViewDefinition:
        """Creează un plan view la o anumită înălțime"""
        return ViewDefinition(
            name=name,
            view_type=ViewType.PLAN,
            camera_position=(0, 0, 100),  # Top view
            camera_target=(0, 0, 0),
            camera_up=(0, 1, 0),
            scale=100.0,
            clipping_planes=[
                {"type": "horizontal", "z": z_level, "direction": "below"}
            ],
            visible_layers=["IfcWall", "IfcColumn", "IfcBeam", "IfcWindow", "IfcSpace"]
        )
    
    def create_section_view(self, name: str, cut_line: List[Tuple[float, float]], direction: str = "north") -> ViewDefinition:
        """Creează un section view"""
        # Calculate camera position based on cut line and direction
        center_x = sum(p[0] for p in cut_line) / len(cut_line)
        center_y = sum(p[1] for p in cut_line) / len(cut_line)
        
        direction_offsets = {
            "north": (0, -10, 5),
            "south": (0, 10, 5), 
            "east": (10, 0, 5),
            "west": (-10, 0, 5)
        }
        
        offset = direction_offsets.get(direction, (0, -10, 5))
        
        return ViewDefinition(
            name=name,
            view_type=ViewType.SECTION,
            camera_position=(center_x + offset[0], center_y + offset[1], offset[2]),
            camera_target=(center_x, center_y, 2.5),
            camera_up=(0, 0, 1),
            scale=100.0,
            clipping_planes=[
                {"type": "vertical", "cut_line": cut_line, "direction": direction}
            ],
            visible_layers=["IfcWall", "IfcColumn", "IfcBeam", "IfcSlab"]
        )
    
    def project_to_2d(self, mesh_data: Dict, view_def: ViewDefinition) -> List[Dict]:
        """Proiectează un mesh 3D la 2D conform view definition"""
        vertices = mesh_data['vertices']
        faces = mesh_data['faces']
        
        # Apply clipping planes first
        if view_def.clipping_planes:
            vertices, faces = self._apply_clipping(vertices, faces, view_def.clipping_planes)
        
        if len(vertices) == 0:
            return []
        
        # Transform to view coordinate system
        view_matrix = self._create_view_matrix(view_def)
        vertices_2d = self._transform_to_view(vertices, view_matrix)
        
        # Generate 2D lines from faces
        lines_2d = self._extract_2d_lines(vertices_2d, faces)
        
        return lines_2d
    
    def _apply_clipping(self, vertices: np.ndarray, faces: np.ndarray, clipping_planes: List[Dict]) -> Tuple[np.ndarray, np.ndarray]:
        """Aplică clipping planes pe geometria 3D"""
        for plane in clipping_planes:
            if plane["type"] == "horizontal":
                z_level = plane["z"]
                if plane["direction"] == "below":
                    # Keep vertices above z_level
                    mask = vertices[:, 2] >= z_level
                    vertices = vertices[mask]
                    # TODO: Update faces accordingly
        
        return vertices, faces
    
    def _create_view_matrix(self, view_def: ViewDefinition) -> np.ndarray:
        """Creează matricea de transformare pentru view"""
        # Simplified orthographic projection
        if view_def.view_type == ViewType.PLAN:
            # Top view - project Z to 0, keep X,Y
            return np.array([
                [1, 0, 0],
                [0, 1, 0],
                [0, 0, 0]
            ])
        else:
            # For sections and elevations, more complex transformation needed
            return np.eye(3)
    
    def _transform_to_view(self, vertices: np.ndarray, view_matrix: np.ndarray) -> np.ndarray:
        """Transformă vertices 3D la coordonate 2D de view"""
        # Simple orthographic projection for now
        if len(vertices) == 0:
            return np.array([]).reshape(0, 2)
            
        # Extract X,Y coordinates (top view)
        return vertices[:, :2]
    
    def _extract_2d_lines(self, vertices_2d: np.ndarray, faces: np.ndarray) -> List[Dict]:
        """Extrage liniile 2D din faces"""
        lines = []
        
        if len(vertices_2d) == 0 or len(faces) == 0:
            return lines
            
        for face in faces:
            # Extract edges from face
            for i in range(len(face)):
                start_idx = face[i]
                end_idx = face[(i + 1) % len(face)]
                
                if start_idx < len(vertices_2d) and end_idx < len(vertices_2d):
                    start_point = vertices_2d[start_idx]
                    end_point = vertices_2d[end_idx]
                    
                    lines.append({
                        'start': start_point,
                        'end': end_point,
                        'type': 'edge_line'
                    })
        
        return lines
    
    def generate_svg(self, sheet: Sheet, data_3d: Dict, output_path: str):
        """Generează un SVG din sheet definition"""
        paper_size = self.paper_sizes.get(sheet.size, self.paper_sizes["A1"])
        
        # Create SVG with proper size (in mm)
        dwg = svgwrite.Drawing(output_path, size=f'{paper_size[0]}mm x {paper_size[1]}mm',
                              viewBox=f'0 0 {paper_size[0]} {paper_size[1]}')
        
        # Add title block
        self._add_title_block(dwg, sheet, paper_size)
        
        # Process each viewport
        for viewport in sheet.viewports:
            self._render_viewport(dwg, viewport, data_3d)
        
        # Save SVG
        dwg.save()
        print(f"[SUCCESS] Generated SVG: {output_path}")
    
    def _add_title_block(self, dwg, sheet: Sheet, paper_size: Tuple[int, int]):
        """Adaugă title block la sheet"""
        # Simple title block in bottom right
        x = paper_size[0] - 200
        y = paper_size[1] - 50
        
        # Border rectangle
        dwg.add(dwg.rect(insert=(x, y), size=(190, 40), 
                        fill='none', stroke='black', stroke_width=0.5))
        
        # Title text
        dwg.add(dwg.text(sheet.title, insert=(x + 5, y + 15), 
                        font_size='12', font_family='Arial'))
        
        # Sheet ID
        dwg.add(dwg.text(f"Sheet: {sheet.id}", insert=(x + 5, y + 30),
                        font_size='10', font_family='Arial'))
        
        # Scale
        dwg.add(dwg.text(f"Scale: {sheet.scale}", insert=(x + 100, y + 30),
                        font_size='10', font_family='Arial'))
    
    def _render_viewport(self, dwg, viewport: Viewport, data_3d: Dict):
        """Renderează un viewport pe sheet"""
        # Create viewport group
        vp_group = dwg.g()
        
        # Add viewport border if needed
        if viewport.border:
            vp_group.add(dwg.rect(insert=viewport.position, size=viewport.size,
                                 fill='none', stroke='black', stroke_width=0.3))
        
        # Process each mesh for this viewport
        for mesh in data_3d['meshes']:
            # Get layer info from metadata
            layer = "default"
            if mesh['uuid'] and mesh['uuid'] in data_3d['metadata']:
                layer = data_3d['metadata'][mesh['uuid']].get('layer', 'default')
            
            # Check if layer is visible in this view
            if layer not in viewport.view_definition.visible_layers:
                continue
            
            # Project mesh to 2D
            lines_2d = self.project_to_2d(mesh, viewport.view_definition)
            
            # Render lines
            for line in lines_2d:
                self._render_line(vp_group, line, layer, viewport)
        
        # Add viewport title if present
        if viewport.title:
            dwg.add(dwg.text(viewport.title, 
                           insert=(viewport.position[0], viewport.position[1] - 5),
                           font_size='10', font_family='Arial'))
        
        dwg.add(vp_group)
    
    def _render_line(self, group, line: Dict, layer: str, viewport: Viewport):
        """Renderează o linie 2D"""
        layer_style = self.layer_styles.get(layer, self.layer_styles.get("default", 
                                           {"line_type": "edge_line", "hatch": None}))
        line_style = self.line_styles[layer_style["line_type"]]
        
        # Transform coordinates to viewport space
        start = self._transform_to_viewport(line['start'], viewport)
        end = self._transform_to_viewport(line['end'], viewport)
        
        # Create line element
        line_elem = group.add(svgwrite.shapes.Line(start=start, end=end,
                                       stroke=line_style["color"],
                                       stroke_width=line_style["weight"]))
        
        # Add dash pattern if needed
        if line_style["dash"]:
            line_elem['stroke-dasharray'] = line_style["dash"]
    
    def _transform_to_viewport(self, point_2d: np.ndarray, viewport: Viewport) -> Tuple[float, float]:
        """Transformă coordonatele 2D la spațiul viewport-ului"""
        # Simple scaling and translation
        scale_factor = viewport.view_definition.scale / 1000.0  # mm per unit
        
        x = viewport.position[0] + point_2d[0] * scale_factor
        y = viewport.position[1] + viewport.size[1] - point_2d[1] * scale_factor  # Flip Y
        
        return (x, y)

def create_standard_sheets(data_3d: Dict) -> List[Sheet]:
    """Creează sheet-uri standard pentru un proiect"""
    generator = LayoutGenerator()
    sheets = []
    
    # Ground Floor Plan
    plan_view = generator.create_plan_view("Ground Floor Plan", z_level=1.5)
    plan_viewport = Viewport(
        view_definition=plan_view,
        position=(50, 100),
        size=(400, 300),
        title="Ground Floor Plan - Scale 1:100"
    )
    
    ground_floor_sheet = Sheet(
        id="A101",
        title="Ground Floor Plan", 
        size="A1",
        scale="1:100",
        viewports=[plan_viewport]
    )
    sheets.append(ground_floor_sheet)
    
    # Section A-A
    section_view = generator.create_section_view("Section A-A", 
                                               cut_line=[(0, 0), (10, 0)], 
                                               direction="north")
    section_viewport = Viewport(
        view_definition=section_view,
        position=(50, 450),
        size=(400, 200),
        title="Section A-A - Scale 1:100"
    )
    
    section_sheet = Sheet(
        id="A201", 
        title="Building Sections",
        size="A1",
        scale="1:100", 
        viewports=[section_viewport]
    )
    sheets.append(section_sheet)
    
    return sheets

if __name__ == "__main__":
    import sys
    
    # Default filesC:\Users\ionut.ciuntuc\Documents\viewer2d\python\math_test.py
    glb_file = "C:/Users/ionut.ciuntuc/Documents/viewer2d/python/dxf/0First_floor.glb"
    json_file = "C:/Users/ionut.ciuntuc/Documents/viewer2d/python/dxf/0First_floor_mapping.json"
    
    if len(sys.argv) > 1:
        base_name = sys.argv[1]
        glb_file = f"{base_name}.glb"
        json_file = f"{base_name}_mapping.json"
    
    print("=== Layout Generator Test ===")
    print(f"GLB: {glb_file}")
    print(f"JSON: {json_file}")
    
    generator = LayoutGenerator()
    
    # Load 3D data
    data_3d = generator.load_3d_data(glb_file, json_file)
    
    if not data_3d['meshes']:
        print("❌ No 3D data found")
        sys.exit(1)
    
        # Debug: Print mesh data info
    print(f"[DEBUG] Loaded meshes: {len(data_3d['meshes'])}")
    for i, mesh in enumerate(data_3d['meshes'][:3]):  # Show first 3
        print(f"  Mesh {i}: {mesh['name']}, vertices: {len(mesh['vertices'])}, uuid: {mesh['uuid']}")
        if mesh['uuid'] in data_3d['metadata']:
            meta = data_3d['metadata'][mesh['uuid']]
            print(f"    Layer: {meta.get('layer', 'Unknown')}")
    
    # Generate standard sheets
    sheets = create_standard_sheets(data_3d)
    
    # Generate SVG for each sheet
    for sheet in sheets:
        output_file = f"layout_{sheet.id}_{sheet.title.replace(' ', '_')}.svg"
        generator.generate_svg(sheet, data_3d, output_file)
    
    print(f"✅ Generated {len(sheets)} layout sheets")