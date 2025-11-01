"""
IFC GLB Converter - Conversie IFC bazată pe GLB + JSON Mapping
=============================================================

Această abordare este mai robustă și eficientă:
1. Citește meshurile finale din fișierul GLB (geometria finală după toate transformările)
2. Citește metadata din JSON mapping (calculele finale cu XDATA)
3. Conectează cele două folosind UUID-urile comune
4. Exportă doar elementele care au atât geometrie cât și metadata

Avantaje:
- Geometria finală din GLB (după boolean operations, trimming, etc.)
- Metadata calculată din JSON (cu XDATA Opening_area, perimeter, etc.)
- Sincronizare perfectă prin UUID-uri
- Exportă doar elementele cu geometrie reală
"""

import json
import trimesh
import ifcopenshell
import ifcopenshell.api
import ifcopenshell.guid
import uuid as uuid_module
from pathlib import Path
from typing import Dict, List, Any, Optional

# Maparea layerelor către tipurile IFC - copiată din background converter
LAYER_TO_IFC_TYPE = {
    # Spații
    "IfcSpace": "IfcSpace",
    "space": "IfcSpace", 
    "spaces": "IfcSpace",
    
    # Ziduri
    "IfcWall": "IfcWall",
    "wall": "IfcWall",
    "walls": "IfcWall",
    "zid": "IfcWall",
    "ziduri": "IfcWall",
    
    # Coloane
    "IfcColumn": "IfcColumn", 
    "column": "IfcColumn",
    "columns": "IfcColumn",
    "coloana": "IfcColumn",
    "coloane": "IfcColumn",
    
    # Plăci
    "IfcSlab": "IfcSlab",
    "slab": "IfcSlab",
    "slabs": "IfcSlab", 
    "placa": "IfcSlab",
    "placi": "IfcSlab",
    
    # Acoperișuri
    "IfcRoof": "IfcRoof",
    "roof": "IfcRoof",
    "roofs": "IfcRoof",
    "acoperis": "IfcRoof",
    
    # Scări
    "IfcStair": "IfcStair", 
    "stair": "IfcStair",
    "stairs": "IfcStair",
    "scara": "IfcStair",
    "scari": "IfcStair",
    
    # Uși
    "IfcDoor": "IfcDoor",
    "door": "IfcDoor", 
    "doors": "IfcDoor",
    "usa": "IfcDoor",
    "usi": "IfcDoor",
    
    # Ferestre
    "IfcWindow": "IfcWindow",
    "window": "IfcWindow",
    "windows": "IfcWindow",
    "fereastra": "IfcWindow",
    "ferestre": "IfcWindow",
}

def determine_ifc_type_from_name(mesh_name: str) -> str:
    """Determină tipul IFC din numele mesh-ului"""
    mesh_name_lower = mesh_name.lower()
    
    # Verifică layerul exact
    for layer_name, ifc_type in LAYER_TO_IFC_TYPE.items():
        if layer_name.lower() in mesh_name_lower:
            return ifc_type
    
    # Fallback la IfcProxy pentru elemente necunoscute
    return "IfcProxy"

class IfcGlbConverter:
    """Converter IFC bazat pe GLB + JSON Mapping"""
    
    def __init__(self):
        self.model = None
        self.project = None
        self.site = None
        self.building = None
        self.storey = None
        self.material_cache = {}  # Cache pentru materiale și material layer sets
        self.layer_materials_config = self._load_layer_materials_config()
    
    def _load_layer_materials_config(self) -> Dict[str, Any]:
        """Încarcă configurația materialelor din layer_materials.json"""
        try:
            config_path = Path(__file__).parent.parent / "layer_materials.json"
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[WARNING] Failed to load layer materials config: {e}")
            return {}
    
    def _create_material_layer_set(self, layer_name: str, element_name: str) -> Optional[Any]:
        """Creează un IfcMaterialLayerSet pentru un layer specificat"""
        if layer_name not in self.layer_materials_config:
            return None
        
        config = self.layer_materials_config[layer_name]
        if 'material_layers' not in config:
            return None
        
        # Verifică cache-ul
        cache_key = f"layerset_{layer_name}"
        if cache_key in self.material_cache:
            return self.material_cache[cache_key]
        
        print(f"[DEBUG] Creating IfcMaterialLayerSet for {layer_name}")
        
        # Creează material layer set
        material_set = ifcopenshell.api.run("material.add_material_set", self.model,
                                          name=f"{layer_name}_LayerSet", set_type="IfcMaterialLayerSet")
        
        # Creează materialele și layerele
        for layer_def in config['material_layers']:
            # Creează materialul dacă nu există
            material_key = f"material_{layer_def['material']}"
            if material_key not in self.material_cache:
                material = ifcopenshell.api.run("material.add_material", self.model, 
                                              name=layer_def['material'], 
                                              category=layer_def.get('category', 'generic'))
                self.material_cache[material_key] = material
            else:
                material = self.material_cache[material_key]
            
            # Creează layer-ul și îl adaugă la set
            layer = ifcopenshell.api.run("material.add_layer", self.model, 
                                       layer_set=material_set, material=material)
            ifcopenshell.api.run("material.edit_layer", self.model, layer=layer, 
                               attributes={"LayerThickness": layer_def['thickness']})
            
            print(f"[DEBUG] Added layer {layer_def['name']}: {layer_def['thickness']}m thick")
        
        # Cache layer set-ul
        self.material_cache[cache_key] = material_set
        return material_set
    
    def _create_simple_material(self, layer_name: str) -> Optional[Any]:
        """Creează un material simplu pentru layere fără material_layers"""
        if layer_name not in self.layer_materials_config:
            return None
        
        cache_key = f"simple_{layer_name}"
        if cache_key in self.material_cache:
            return self.material_cache[cache_key]
        
        print(f"[DEBUG] Creating simple IfcMaterial for {layer_name}")
        
        material = ifcopenshell.api.run("material.add_material", self.model,
                                      name=f"{layer_name}_Material",
                                      category=layer_name.lower())
        
        self.material_cache[cache_key] = material
        return material
    
    def _assign_material_to_element(self, element, layer_name: str, element_name: str):
        """Atribuie material sau material layer set la element"""
        try:
            if not layer_name:
                return
            
            # Încearcă să creeze material layer set
            material_set = self._create_material_layer_set(layer_name, element_name)
            
            if material_set:
                # Folosește material layer set
                print(f"[DEBUG] Assigning IfcMaterialLayerSet to {element_name}")
                ifcopenshell.api.run("material.assign_material", self.model,
                                   products=[element], material=material_set)
            else:
                # Fallback la material simplu
                simple_material = self._create_simple_material(layer_name)
                if simple_material:
                    print(f"[DEBUG] Assigning simple IfcMaterial to {element_name}")
                    ifcopenshell.api.run("material.assign_material", self.model,
                                       products=[element], material=simple_material)
                else:
                    print(f"[WARNING] No material configuration found for layer: {layer_name}")
            
        except Exception as e:
            print(f"[ERROR] Failed to assign material to {element_name}: {e}")
        
    def convert_glb_to_ifc(self, glb_path: str, json_mapping_path: str, output_ifc_path: str) -> bool:
        """
        Convertește un fișier GLB + JSON mapping în IFC
        
        Args:
            glb_path: Calea către fișierul GLB cu meshurile finale
            json_mapping_path: Calea către JSON mapping cu metadata
            output_ifc_path: Calea unde să salveze fișierul IFC
            
        Returns:
            True dacă conversia a fost cu succes
        """
        try:
            print(f"[DEBUG] Loading GLB mesh data from: {glb_path}")
            glb_meshes = self._load_glb_meshes(glb_path)
            
            print(f"[DEBUG] Loading JSON mapping from: {json_mapping_path}")
            json_mapping = self._load_json_mapping(json_mapping_path)
            
            print(f"[DEBUG] Found {len(glb_meshes)} meshes in GLB and {len(json_mapping)} entries in JSON")
            
            # Creează modelul IFC
            self._create_ifc_model(Path(glb_path).stem)
            
            # Procesează fiecare mesh cu metadata asociată
            converted_count = 0
            for mesh_data in glb_meshes:
                mesh_uuid = mesh_data.get('uuid')
                if not mesh_uuid:
                    print(f"[WARNING] Mesh without UUID: {mesh_data.get('name', 'Unknown')}")
                    continue
                
                # Găsește metadata asociată prin UUID
                metadata = self._find_metadata_by_uuid(json_mapping, mesh_uuid)
                if not metadata:
                    print(f"[WARNING] No metadata found for mesh UUID: {mesh_uuid}")
                    continue
                
                # Convertește mesh-ul cu metadata în element IFC
                if self._convert_mesh_to_ifc(mesh_data, metadata):
                    converted_count += 1
            
            print(f"[DEBUG] Converted {converted_count} elements to IFC")
            
            # Salvează fișierul IFC
            self.model.write(output_ifc_path)
            print(f"[SUCCESS] IFC file saved: {output_ifc_path}")
            
            return True
            
        except Exception as e:
            print(f"[ERROR] GLB to IFC conversion failed: {e}")
            return False
    
    def _load_glb_meshes(self, glb_path: str) -> List[Dict[str, Any]]:
        """Încarcă meshurile din fișierul GLB cu UUID-urile lor"""
        try:
            scene = trimesh.load(glb_path)
            meshes = []
            
            if hasattr(scene, 'geometry'):
                # Scene cu mai multe geometrii
                for name, geometry in scene.geometry.items():
                    mesh_data = {
                        'name': name,
                        'geometry': geometry,
                        'uuid': geometry.metadata.get('uuid') if hasattr(geometry, 'metadata') else None,
                        'vertices_count': len(geometry.vertices) if hasattr(geometry, 'vertices') else 0,
                        'faces_count': len(geometry.faces) if hasattr(geometry, 'faces') else 0
                    }
                    meshes.append(mesh_data)
            else:
                # Scene cu o singură geometrie
                mesh_data = {
                    'name': getattr(scene, 'metadata', {}).get('name', 'Mesh'),
                    'geometry': scene,
                    'uuid': scene.metadata.get('uuid') if hasattr(scene, 'metadata') else None,
                    'vertices_count': len(scene.vertices) if hasattr(scene, 'vertices') else 0,
                    'faces_count': len(scene.faces) if hasattr(scene, 'faces') else 0
                }
                meshes.append(mesh_data)
            
            # Filtrează meshurile fără UUID sau geometrie
            valid_meshes = [m for m in meshes if m['uuid'] and m['vertices_count'] > 0]
            print(f"[DEBUG] Loaded {len(valid_meshes)} valid meshes from GLB")
            
            return valid_meshes
            
        except Exception as e:
            print(f"[ERROR] Failed to load GLB file: {e}")
            return []
    
    def _load_json_mapping(self, json_path: str) -> List[Dict[str, Any]]:
        """Încarcă metadata din JSON mapping"""
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # JSON mapping este o listă de dicționare cu UUID-uri și metadata
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and 'elements' in data:
                return data['elements']
            else:
                print(f"[WARNING] Unexpected JSON structure in {json_path}")
                return []
                
        except Exception as e:
            print(f"[ERROR] Failed to load JSON mapping: {e}")
            return []
    
    def _find_metadata_by_uuid(self, json_mapping: List[Dict[str, Any]], target_uuid: str) -> Optional[Dict[str, Any]]:
        """Găsește metadata pentru un UUID specific"""
        for entry in json_mapping:
            if entry.get('uuid') == target_uuid:
                return entry
        return None
    
    def _create_ifc_model(self, project_name: str):
        """Creează structura de bază a modelului IFC"""
        # Creează fișierul IFC nou
        self.model = ifcopenshell.file()
        
        # Creează proiectul
        self.project = ifcopenshell.api.run("root.create_entity", 
                                           self.model,
                                           ifc_class="IfcProject", 
                                           name=f"Project_{project_name}")
        
        # Adaugă unitățile de măsură (necesar pentru Blender Bonsai)
        ifcopenshell.api.run("unit.assign_unit", self.model, length={"is_metric": True, "raw": "METERS"})
        
        # Creează structura ierarhică standard
        context = ifcopenshell.api.run("context.add_context", self.model, context_type="Model")
        body_context = ifcopenshell.api.run("context.add_context", self.model, 
                                          context_type="Model", context_identifier="Body", 
                                          target_view="MODEL_VIEW", parent=context)
        
        self.site = ifcopenshell.api.run("root.create_entity", self.model, 
                                        ifc_class="IfcSite", name="Site")
        self.building = ifcopenshell.api.run("root.create_entity", self.model, 
                                           ifc_class="IfcBuilding", name="Building")
        self.storey = ifcopenshell.api.run("root.create_entity", self.model, 
                                         ifc_class="IfcBuildingStorey", name="Ground Floor")
        
        # Stabilește relațiile ierarhice
        ifcopenshell.api.run("aggregate.assign_object", self.model, 
                           products=[self.site], relating_object=self.project)
        ifcopenshell.api.run("aggregate.assign_object", self.model, 
                           products=[self.building], relating_object=self.site)
        ifcopenshell.api.run("aggregate.assign_object", self.model, 
                           products=[self.storey], relating_object=self.building)
    
    def _convert_mesh_to_ifc(self, mesh_data: Dict[str, Any], metadata: Dict[str, Any]) -> bool:
        """Convertește un mesh cu metadata în element IFC"""
        try:
            mesh_name = mesh_data['name']
            mesh_uuid = mesh_data['uuid']
            geometry = mesh_data['geometry']
            
            # Determină tipul IFC
            ifc_type = determine_ifc_type_from_name(mesh_name)
            
            print(f"[DEBUG] Converting {mesh_name} (UUID: {mesh_uuid}) to {ifc_type}")
            
            # Creează elementul IFC
            element = ifcopenshell.api.run("root.create_entity", self.model, 
                                         ifc_class=ifc_type, name=mesh_name)
            
            # Încearcă să atașeze elementul la storey
            try:
                ifcopenshell.api.run("spatial.assign_container", self.model,
                                   products=[element], relating_structure=self.storey)
            except Exception as e:
                print(f"[WARNING] Could not attach {mesh_name} to storey: {e}")
            
            # Adaugă proprietățile din metadata
            self._add_properties_to_element(element, metadata, mesh_uuid)
            
            # Adaugă materialele pe baza layer-ului
            self._assign_material_to_element(element, metadata.get('layer', ''), mesh_name)
            
            # Adaugă geometria 3D din meshul GLB
            self._add_geometry_to_element(element, mesh_data, ifc_type)
            
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to convert mesh {mesh_data.get('name', 'Unknown')}: {e}")
            return False
    
    def _add_properties_to_element(self, element, metadata: Dict[str, Any], mesh_uuid: str):
        """Adaugă proprietățile din metadata la elementul IFC"""
        try:
            # Creează property set pentru proprietățile de bază
            pset = ifcopenshell.api.run("pset.add_pset", self.model, 
                                      product=element, name="Pset_ElementProperties")
            
            # Adaugă proprietățile din metadata
            for key, value in metadata.items():
                if key == 'uuid':
                    continue  # UUID-ul e deja adăugat separat
                
                # Convertește valoarea la tipul potrivit pentru IFC
                if isinstance(value, (int, float)):
                    ifc_value = self.model.create_entity("IfcReal", float(value))
                elif isinstance(value, bool):
                    ifc_value = self.model.create_entity("IfcBoolean", value)
                else:
                    ifc_value = self.model.create_entity("IfcText", str(value))
                
                # Creează proprietatea
                prop = self.model.create_entity("IfcPropertySingleValue",
                                              Name=key,
                                              NominalValue=ifc_value)
                
                # Adaugă proprietatea la property set
                current_props = list(pset.HasProperties) if pset.HasProperties else []
                current_props.append(prop)
                pset.HasProperties = tuple(current_props)
            
            # Adaugă UUID-ul ca proprietate specială pentru Godot
            uuid_prop = self.model.create_entity("IfcPropertySingleValue",
                                               Name="GodotUUID",
                                               NominalValue=self.model.create_entity("IfcText", mesh_uuid))
            current_props = list(pset.HasProperties) if pset.HasProperties else []
            current_props.append(uuid_prop)
            pset.HasProperties = tuple(current_props)
            
            print(f"[DEBUG] Added {len(metadata)} properties to {element.Name}")
            
        except Exception as e:
            print(f"[ERROR] Failed to add properties: {e}")
    
    def _add_geometry_to_element(self, element, mesh_data: Dict[str, Any], ifc_type: str):
        """Adaugă geometria 3D din mesh la elementul IFC"""
        try:
            geometry = mesh_data['geometry']
            
            # Verifică dacă meshul are vertices și faces
            if not hasattr(geometry, 'vertices') or not hasattr(geometry, 'faces'):
                print(f"[WARNING] Mesh {mesh_data['name']} has no valid geometry")
                return
            
            vertices = geometry.vertices
            faces = geometry.faces
            
            if len(vertices) == 0 or len(faces) == 0:
                print(f"[WARNING] Mesh {mesh_data['name']} has empty geometry")
                return
            
            print(f"[DEBUG] Adding geometry to {mesh_data['name']}: {len(vertices)} vertices, {len(faces)} faces")
            
            # Creează contextul geometric
            context = self.model.by_type("IfcGeometricRepresentationContext")[0]
            
            # Convertește vertices în IfcCartesianPoint  
            ifc_points = []
            for vertex in vertices:
                point = self.model.create_entity("IfcCartesianPoint", Coordinates=[float(v) for v in vertex])
                ifc_points.append(point)
            
            # Convertește faces în IfcTriangleFace (pentru IfcTriangulatedFaceSet)
            ifc_faces = []
            for face in faces:
                # IFC folosește indexare bazată pe 1, nu pe 0
                face_indices = [int(idx + 1) for idx in face]
                ifc_faces.append(tuple(face_indices))
            
            # Creează IfcTriangulatedFaceSet
            triangulated_face_set = self.model.create_entity(
                "IfcTriangulatedFaceSet",
                Coordinates=self.model.create_entity(
                    "IfcCartesianPointList3D",
                    CoordList=[[float(v) for v in vertex] for vertex in vertices]
                ),
                CoordIndex=ifc_faces
            )
            
            # Creează reprezentarea geometrică
            shape_representation = self.model.create_entity(
                "IfcShapeRepresentation",
                ContextOfItems=context,
                RepresentationIdentifier="Body",
                RepresentationType="Tessellation",
                Items=[triangulated_face_set]
            )
            
            # Atașează reprezentarea la element prin IfcProductDefinitionShape
            product_definition_shape = self.model.create_entity(
                "IfcProductDefinitionShape",
                Representations=[shape_representation]
            )
            
            # Atașează geometria la element
            element.Representation = product_definition_shape
            
            print(f"[DEBUG] Successfully added geometry to {mesh_data['name']}")
            
        except Exception as e:
            print(f"[ERROR] Failed to add geometry to {mesh_data.get('name', 'Unknown')}: {e}")

def convert_glb_to_ifc(glb_path: str, json_mapping_path: str, output_ifc_path: str) -> bool:
    """
    Funcție de utilitate pentru conversia GLB + JSON mapping → IFC
    
    Args:
        glb_path: Calea către fișierul GLB
        json_mapping_path: Calea către JSON mapping
        output_ifc_path: Calea pentru fișierul IFC rezultat
        
    Returns:
        True dacă conversia a fost cu succes
    """
    converter = IfcGlbConverter()
    return converter.convert_glb_to_ifc(glb_path, json_mapping_path, output_ifc_path)

if __name__ == "__main__":
    # Test cu fișierele din directorul curent
    import sys
    import os
    
    if len(sys.argv) >= 2:
        base_name = sys.argv[1]
    else:
        base_name = "test_grid"
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    
    # Încearcă mai întâi cu _out, apoi fără
    glb_path = os.path.join(parent_dir, f"{base_name}_out.glb")
    json_path = os.path.join(parent_dir, f"{base_name}_out_mapping.json")
    
    if not os.path.exists(glb_path):
        glb_path = os.path.join(parent_dir, f"{base_name}.glb")
    if not os.path.exists(json_path):
        json_path = os.path.join(parent_dir, f"{base_name}_mapping.json")
    
    ifc_path = os.path.join(parent_dir, f"{base_name}_from_glb.ifc")
    
    print("=== IFC GLB Converter Test ===")
    print(f"GLB: {glb_path}")
    print(f"JSON: {json_path}")
    print(f"IFC: {ifc_path}")
    
    if convert_glb_to_ifc(glb_path, json_path, ifc_path):
        print(f"✅ Conversion successful: {ifc_path}")
    else:
        print("❌ Conversion failed")