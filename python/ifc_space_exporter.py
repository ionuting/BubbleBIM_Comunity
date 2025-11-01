#!/usr/bin/env python3
"""
IFC Space Exporter pentru Godot CAD Viewer
Exportă geometria și metadatele IfcSpace din Godot către un fișier IFC standard.
"""

import json
import sys
import os
import re
import numpy as np
from typing import Dict, List, Tuple, Any
import ifcopenshell
import ifcopenshell.api
import ifcopenshell.geom
import ifcopenshell.util.unit
import uuid as uuid_module
from datetime import datetime

def evaluate_math_formula(formula_str):
    """Evaluează o formulă matematică în siguranță pentru XDATA Opening_area"""
    
    if not isinstance(formula_str, str):
        return None
        
    # Înlătură = din început dacă există
    formula = formula_str.strip()
    if formula.startswith('='):
        formula = formula[1:]
    
    # Validează că conține doar caractere matematice sigure
    safe_pattern = r'^[0-9+\-*/.() ]+$'
    if not re.match(safe_pattern, formula):
        print(f'[WARNING] XDATA formula contains unsafe characters: {formula}')
        return None
    
    try:
        result = eval(formula)
        print(f'[DEBUG] Formula XDATA "{formula_str}" = {result}')
        return result
    except Exception as e:
        print(f'[ERROR] Eroare la evaluarea formulei XDATA "{formula_str}": {e}')
        return None

def process_xdata_for_space(space_data):
    """Procesează XDATA pentru un IfcSpace și calculează lateral_area ajustată"""
    
    if not isinstance(space_data, dict):
        return space_data
    
    # Verifică dacă are XDATA cu Opening_area
    xdata = space_data.get('xdata', {})
    if not xdata or not isinstance(xdata, dict):
        return space_data
    
    # Caută Opening_area în XDATA (poate fi în ACAD sau direct)
    opening_area_formula = None
    if 'ACAD' in xdata and isinstance(xdata['ACAD'], dict):
        opening_area_formula = xdata['ACAD'].get('Opening_area')
    else:
        opening_area_formula = xdata.get('Opening_area')
    
    if not opening_area_formula:
        return space_data
    
    print(f'[DEBUG] Processing XDATA Opening_area for {space_data.get("mesh_name", "Unknown")}')
    
    # Evaluează formula
    opening_area_value = evaluate_math_formula(opening_area_formula)
    
    if opening_area_value is not None:
        # Calculează lateral area ajustată
        original_lateral_area = space_data.get('lateral_area', 0)
        adjusted_lateral_area = original_lateral_area - opening_area_value
        
        print(f'[DEBUG] XDATA: {original_lateral_area} - {opening_area_value} = {adjusted_lateral_area}')
        
        # Actualizează datele (creează o copie modificată)
        processed_data = dict(space_data)
        processed_data['lateral_area'] = adjusted_lateral_area
        processed_data['_opening_area_calculated'] = opening_area_value  # Pentru debug
        
        return processed_data
    
    return space_data

class IfcSpaceExporter:
    def __init__(self):
        self.model = None
        self.project = None
        self.site = None
        self.building = None
        self.storey = None
        self.owner_history = None
        self.context = None
        self.units = None
        
    def create_ifc_model(self, project_name: str = "Godot Exported Spaces"):
        """Creează un model IFC gol cu structurile de bază"""
        print(f"[DEBUG] Creating IFC model: {project_name}")
        
        # Creează modelul IFC 4
        self.model = ifcopenshell.file(schema="IFC4")
        
        # Creează contextul de aplicație
        application = self.model.create_entity("IfcApplication", 
            ApplicationDeveloper=self.model.create_entity("IfcOrganization", Name="Godot CAD Viewer"),
            Version="1.0",
            ApplicationFullName="Godot CAD Viewer Space Exporter",
            ApplicationIdentifier="GodotCADViewer"
        )
        
        # Creează persoana și organizația
        person = self.model.create_entity("IfcPerson",
            FamilyName="User",
            GivenName="Godot"
        )
        
        organization = self.model.create_entity("IfcOrganization",
            Name="Godot Project"
        )
        
        person_organization = self.model.create_entity("IfcPersonAndOrganization",
            ThePerson=person,
            TheOrganization=organization
        )
        
        # Creează owner history
        self.owner_history = self.model.create_entity("IfcOwnerHistory",
            OwningUser=person_organization,
            OwningApplication=application,
            ChangeAction="ADDED",
            CreationDate=int(datetime.now().timestamp())
        )
        
        # Creează unitățile
        self._create_units()
        
        # Creează contextul geometric
        self._create_geometric_context()
        
        # Creează proiectul
        self.project = self.model.create_entity("IfcProject",
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=self.owner_history,
            Name=project_name,
            Description="IFC model exported from Godot CAD Viewer containing IfcSpace elements",
            UnitsInContext=self.units,
            RepresentationContexts=[self.context]
        )
        
        # Creează site-ul
        self.site = self.model.create_entity("IfcSite",
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=self.owner_history,
            Name="Default Site",
            CompositionType="ELEMENT"
        )
        
        # Creează clădirea
        self.building = self.model.create_entity("IfcBuilding",
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=self.owner_history,
            Name="Default Building",
            CompositionType="ELEMENT"
        )
        
        # Creează etajul
        self.storey = self.model.create_entity("IfcBuildingStorey",
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=self.owner_history,
            Name="Default Storey",
            CompositionType="ELEMENT",
            Elevation=0.0
        )
        
        # Creează relațiile ierarhice
        self.model.create_entity("IfcRelAggregates",
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=self.owner_history,
            RelatingObject=self.project,
            RelatedObjects=[self.site]
        )
        
        self.model.create_entity("IfcRelAggregates",
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=self.owner_history,
            RelatingObject=self.site,
            RelatedObjects=[self.building]
        )
        
        self.model.create_entity("IfcRelAggregates",
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=self.owner_history,
            RelatingObject=self.building,
            RelatedObjects=[self.storey]
        )
        
        print("[DEBUG] IFC model structure created successfully")
        
    def _create_units(self):
        """Creează unitățile pentru model"""
        # Unitate pentru lungime (metri)
        length_unit = self.model.create_entity("IfcSIUnit",
            UnitType="LENGTHUNIT",
            Name="METRE"
        )
        
        # Unitate pentru arie (metri pătrați)
        area_unit = self.model.create_entity("IfcSIUnit",
            UnitType="AREAUNIT",
            Name="SQUARE_METRE"
        )
        
        # Unitate pentru volum (metri cubi)
        volume_unit = self.model.create_entity("IfcSIUnit",
            UnitType="VOLUMEUNIT",
            Name="CUBIC_METRE"
        )
        
        # Unitate pentru unghi (radiani)
        angle_unit = self.model.create_entity("IfcSIUnit",
            UnitType="PLANEANGLEUNIT",
            Name="RADIAN"
        )
        
        self.units = self.model.create_entity("IfcUnitAssignment",
            Units=[length_unit, area_unit, volume_unit, angle_unit]
        )
        
    def _create_geometric_context(self):
        """Creează contextul geometric pentru reprezentări 3D"""
        self.context = self.model.create_entity("IfcGeometricRepresentationContext",
            ContextType="Model",
            CoordinateSpaceDimension=3,
            Precision=1e-5,
            WorldCoordinateSystem=self.model.create_entity("IfcAxis2Placement3D",
                Location=self.model.create_entity("IfcCartesianPoint", Coordinates=[0.0, 0.0, 0.0]),
                Axis=self.model.create_entity("IfcDirection", DirectionRatios=[0.0, 0.0, 1.0]),
                RefDirection=self.model.create_entity("IfcDirection", DirectionRatios=[1.0, 0.0, 0.0])
            )
        )
        
    def create_space_from_data(self, space_data: Dict[str, Any]) -> Any:
        """Creează un IfcSpace din datele exportate din Godot"""
        mesh_name = space_data.get("mesh_name", "UnknownSpace")
        uuid = space_data.get("uuid", str(uuid_module.uuid4()))
        vertices = space_data.get("vertices", [])
        area = space_data.get("area", 0.0)
        perimeter = space_data.get("perimeter", 0.0)
        lateral_area = space_data.get("lateral_area", 0.0)
        volume = space_data.get("volume", 0.0)
        height = space_data.get("height", 2.8)
        
        print(f"[DEBUG] Creating IfcSpace: {mesh_name}")
        print(f"[DEBUG] - Area: {area:.2f}m², Perimeter: {perimeter:.2f}m, Volume: {volume:.3f}m³")
        
        # Creează IfcSpace
        space = self.model.create_entity("IfcSpace",
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=self.owner_history,
            Name=mesh_name,
            Description=f"Space exported from Godot CAD Viewer (UUID: {uuid})",
            CompositionType="ELEMENT",
            PredefinedType="INTERNAL",
            ElevationWithFlooring=0.0
        )
        
        # Adaugă proprietăți custom pentru valorile noastre
        self._add_space_properties(space, {
            "Area": area,
            "Perimeter": perimeter,
            "LateralArea": lateral_area,
            "Volume": volume,
            "Height": height,
            "GodotUUID": uuid,
            "VertexCount": len(vertices)
        })
        
        # Creează geometria dacă avem vertices
        if vertices and len(vertices) >= 3:
            self._create_space_geometry(space, vertices, height)
        
        # Adaugă spațiul la etaj
        self.model.create_entity("IfcRelContainedInSpatialStructure",
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=self.owner_history,
            RelatedElements=[space],
            RelatingStructure=self.storey
        )
        
        return space
    
    def _add_space_properties(self, space: Any, properties: Dict[str, Any]):
        """Adaugă proprietăți custom la IfcSpace"""
        # Creează property set pentru valorile noastre
        property_values = []
        
        for prop_name, prop_value in properties.items():
            if isinstance(prop_value, (int, float)):
                ifc_value = self.model.create_entity("IfcReal", prop_value)
                property_values.append(
                    self.model.create_entity("IfcPropertySingleValue",
                        Name=prop_name,
                        NominalValue=ifc_value
                    )
                )
            elif isinstance(prop_value, str):
                ifc_value = self.model.create_entity("IfcText", prop_value)
                property_values.append(
                    self.model.create_entity("IfcPropertySingleValue",
                        Name=prop_name,
                        NominalValue=ifc_value
                    )
                )
        
        # Creează property set
        property_set = self.model.create_entity("IfcPropertySet",
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=self.owner_history,
            Name="GodotSpaceProperties",
            Description="Properties exported from Godot CAD Viewer",
            HasProperties=property_values
        )
        
        # Leagă property set-ul de spațiu
        self.model.create_entity("IfcRelDefinesByProperties",
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=self.owner_history,
            RelatedObjects=[space],
            RelatingPropertyDefinition=property_set
        )
        
        # Adaugă și quantity set standard IFC pentru spații
        self._add_space_quantities(space, properties)
    
    def _add_space_quantities(self, space: Any, properties: Dict[str, Any]):
        """Adaugă quantity set standard IFC pentru spații"""
        quantities = []
        
        # Area quantity
        if properties.get("Area", 0) > 0:
            quantities.append(
                self.model.create_entity("IfcQuantityArea",
                    Name="NetFloorArea",
                    Description="Net floor area of the space",
                    AreaValue=properties["Area"]
                )
            )
        
        # Volume quantity
        if properties.get("Volume", 0) > 0:
            quantities.append(
                self.model.create_entity("IfcQuantityVolume",
                    Name="NetVolume",
                    Description="Net volume of the space",
                    VolumeValue=properties["Volume"]
                )
            )
        
        # Height quantity
        if properties.get("Height", 0) > 0:
            quantities.append(
                self.model.create_entity("IfcQuantityLength",
                    Name="Height",
                    Description="Height of the space",
                    LengthValue=properties["Height"]
                )
            )
        
        # Perimeter quantity
        if properties.get("Perimeter", 0) > 0:
            quantities.append(
                self.model.create_entity("IfcQuantityLength",
                    Name="Perimeter",
                    Description="Perimeter of the space",
                    LengthValue=properties["Perimeter"]
                )
            )
        
        # Lateral Area quantity (specific pentru CAD Viewer)
        if properties.get("LateralArea", 0) > 0:
            quantities.append(
                self.model.create_entity("IfcQuantityArea",
                    Name="LateralArea",
                    Description="Lateral area of the space (walls area)",
                    AreaValue=properties["LateralArea"]
                )
            )
        
        if quantities:
            # Creează quantity set
            quantity_set = self.model.create_entity("IfcElementQuantity",
                GlobalId=ifcopenshell.guid.new(),
                OwnerHistory=self.owner_history,
                Name="BaseQuantities",
                Description="Base quantities for space",
                Quantities=quantities
            )
            
            # Leagă quantity set-ul de spațiu
            self.model.create_entity("IfcRelDefinesByProperties",
                GlobalId=ifcopenshell.guid.new(),
                OwnerHistory=self.owner_history,
                RelatedObjects=[space],
                RelatingPropertyDefinition=quantity_set
            )
    
    def _create_space_geometry(self, space: Any, vertices: List[List[float]], height: float):
        """Creează geometria 3D pentru IfcSpace"""
        try:
            # Convertește vertices în IfcCartesianPoint
            ifc_points = []
            for vertex in vertices:
                if len(vertex) >= 2:
                    # Adaugă Z=0 pentru vertices 2D
                    point_coords = [float(vertex[0]), float(vertex[1]), 0.0]
                    ifc_points.append(
                        self.model.create_entity("IfcCartesianPoint", Coordinates=point_coords)
                    )
            
            if len(ifc_points) < 3:
                print(f"[WARNING] Not enough vertices for space geometry: {len(ifc_points)}")
                return
            
            # Închide poligonul dacă nu este deja închis
            if len(ifc_points) > 2:
                first_point = ifc_points[0].Coordinates
                last_point = ifc_points[-1].Coordinates
                if abs(first_point[0] - last_point[0]) > 1e-6 or abs(first_point[1] - last_point[1]) > 1e-6:
                    ifc_points.append(ifc_points[0])  # Închide poligonul
            
            # Creează polyline pentru conturul de bază
            polyline = self.model.create_entity("IfcPolyline", Points=ifc_points)
            
            # Creează curba composită
            composite_curve = self.model.create_entity("IfcCompositeCurve",
                Segments=[
                    self.model.create_entity("IfcCompositeCurveSegment",
                        Transition="CONTINUOUS",
                        SameSense=True,
                        ParentCurve=polyline
                    )
                ],
                SelfIntersect=False
            )
            
            # Creează conturul exterior
            outer_bound = self.model.create_entity("IfcFaceOuterBound",
                Bound=composite_curve,
                Orientation=True
            )
            
            # Creează fața
            face = self.model.create_entity("IfcFace", Bounds=[outer_bound])
            
            # Creează shell-ul închis prin extrudare
            closed_shell = self.model.create_entity("IfcClosedShell", CfsFaces=[face])
            
            # Creează reprezentarea geometrică prin extrudare
            direction = self.model.create_entity("IfcDirection", DirectionRatios=[0.0, 0.0, 1.0])
            
            extruded_solid = self.model.create_entity("IfcExtrudedAreaSolid",
                SweptArea=self.model.create_entity("IfcArbitraryClosedProfileDef",
                    ProfileType="AREA",
                    OuterCurve=composite_curve
                ),
                Position=self.model.create_entity("IfcAxis2Placement3D",
                    Location=self.model.create_entity("IfcCartesianPoint", Coordinates=[0.0, 0.0, 0.0])
                ),
                ExtrudedDirection=direction,
                Depth=height
            )
            
            # Creează reprezentarea
            representation = self.model.create_entity("IfcShapeRepresentation",
                ContextOfItems=self.context,
                RepresentationIdentifier="Body",
                RepresentationType="SweptSolid",
                Items=[extruded_solid]
            )
            
            # Creează product definition shape
            product_shape = self.model.create_entity("IfcProductDefinitionShape",
                Representations=[representation]
            )
            
            # Atașează geometria la spațiu
            space.Representation = product_shape
            
            print(f"[DEBUG] Created geometry for space with {len(vertices)} vertices, height {height}m")
            
        except Exception as e:
            print(f"[ERROR] Failed to create space geometry: {e}")
    
    def save_ifc_file(self, output_path: str):
        """Salvează modelul IFC în fișier"""
        try:
            self.model.write(output_path)
            print(f"[DEBUG] IFC file saved successfully: {output_path}")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to save IFC file: {e}")
            return False

def export_spaces_to_ifc(godot_data_path: str, mapping_data_path: str, output_ifc_path: str, project_name: str = "Godot Spaces") -> bool:
    """
    Funcția principală pentru exportul spațiilor în IFC
    
    Args:
        godot_data_path: Calea la fișierul JSON cu geometria din Godot
        mapping_data_path: Calea la fișierul JSON cu mapping-ul
        output_ifc_path: Calea de ieșire pentru fișierul IFC
        project_name: Numele proiectului IFC
    """
    try:
        print(f"[DEBUG] Starting IFC export for project: {project_name}")
        
        # Citește datele din Godot
        if not os.path.exists(godot_data_path):
            print(f"[ERROR] Godot data file not found: {godot_data_path}")
            return False
            
        with open(godot_data_path, 'r', encoding='utf-8') as f:
            godot_data = json.load(f)
        
        # Citește mapping-ul
        if not os.path.exists(mapping_data_path):
            print(f"[ERROR] Mapping data file not found: {mapping_data_path}")
            return False
            
        with open(mapping_data_path, 'r', encoding='utf-8') as f:
            mapping_data = json.load(f)
        
        # Creează exporter-ul
        exporter = IfcSpaceExporter()
        exporter.create_ifc_model(project_name)
        
        # Procesează toate geometriile IfcSpace din datele Godot
        space_count = 0
        for godot_entry in godot_data.get("spaces", []):
            if not isinstance(godot_entry, dict):
                continue
            
            # Încearcă să găsești metadatele corespunzătoare în mapping
            uuid = godot_entry.get("uuid", "")
            mesh_name = godot_entry.get("mesh_name", "")
            mapping_data_entry = None
            
            # Caută în mapping după UUID sau mesh_name (cu logică inteligentă)
            for entry in mapping_data:
                entry_uuid = entry.get("uuid", "")
                entry_mesh_name = entry.get("mesh_name", "")
                
                # Verificare directă UUID
                if entry_uuid and entry_uuid == uuid:
                    mapping_data_entry = entry
                    break
                    
                # Verificare directă mesh_name
                if entry_mesh_name and entry_mesh_name == mesh_name:
                    mapping_data_entry = entry
                    break
                
                # Verificare mesh_name fără sufixul _LAYER_*
                # Ex: IfcSpace_LivingRoom_1_LAYER_IfcSpace → IfcSpace_LivingRoom_1
                if mesh_name and "_LAYER_" in mesh_name:
                    clean_mesh_name = mesh_name.split("_LAYER_")[0]
                    if entry_mesh_name == clean_mesh_name:
                        mapping_data_entry = entry
                        print(f"[DEBUG] Found mapping match using clean name: {clean_mesh_name}")
                        break
                
                # Verificare inversă - dacă entry are suffix și godot nu
                if entry_mesh_name and "_LAYER_" in entry_mesh_name:
                    clean_entry_name = entry_mesh_name.split("_LAYER_")[0]
                    if clean_entry_name == mesh_name:
                        mapping_data_entry = entry
                        print(f"[DEBUG] Found mapping match using clean entry name: {clean_entry_name}")
                        break
            
            # Combină datele: începe cu geometria Godot, apoi adaugă metadatele din mapping
            space_data = dict(godot_entry)  # Copiază geometria Godot
            if mapping_data_entry:
                print(f"[DEBUG] Found mapping data for {mesh_name}: area={mapping_data_entry.get('area', 'N/A')}, volume={mapping_data_entry.get('volume', 'N/A')}")
                # Adaugă metadatele din mapping, dar păstrează geometria Godot
                for key, value in mapping_data_entry.items():
                    if key not in ["vertices", "triangles", "vertex_count"]:  # Nu suprascrie doar geometria
                        space_data[key] = value
                        print(f"[DEBUG] Copied {key}={value} from mapping to space_data")
            else:
                print(f"[WARNING] No mapping entry found for space: UUID={uuid}, mesh_name={mesh_name}")
                # Afișează ce avem disponibil în mapping pentru debug
                print(f"[DEBUG] Available mapping entries:")
                for i, entry in enumerate(mapping_data):
                    entry_uuid = entry.get("uuid", "N/A")
                    entry_mesh = entry.get("mesh_name", "N/A")
                    print(f"  [{i}] UUID: {entry_uuid}, mesh: {entry_mesh}")
                print(f"[WARNING] Could not find mapping data for space: {mesh_name}, using fallback values")
            
            # Procesează XDATA înainte de export
            space_data = process_xdata_for_space(space_data)
            
            # Asigură-te că are layer-ul corect
            space_data["layer"] = "IfcSpace"
            
            # Creează IfcSpace
            exporter.create_space_from_data(space_data)
            space_count += 1
        
        if space_count == 0:
            print("[WARNING] No IfcSpace elements found to export")
            return False
        
        # Salvează fișierul IFC
        success = exporter.save_ifc_file(output_ifc_path)
        
        if success:
            print(f"[SUCCESS] Exported {space_count} IfcSpace elements to: {output_ifc_path}")
        
        return success
        
    except Exception as e:
        print(f"[ERROR] IFC export failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python ifc_space_exporter.py <godot_data.json> <mapping_data.json> <output.ifc> [project_name]")
        print("")
        print("Arguments:")
        print("  godot_data.json    - JSON file with geometry data from Godot")
        print("  mapping_data.json  - JSON file with mapping metadata")
        print("  output.ifc         - Output IFC file path")
        print("  project_name       - Optional project name (default: 'Godot Spaces')")
        sys.exit(1)
    
    godot_data_path = sys.argv[1]
    mapping_data_path = sys.argv[2]
    output_ifc_path = sys.argv[3]
    project_name = sys.argv[4] if len(sys.argv) > 4 else "Godot Spaces"
    
    success = export_spaces_to_ifc(godot_data_path, mapping_data_path, output_ifc_path, project_name)
    sys.exit(0 if success else 1)