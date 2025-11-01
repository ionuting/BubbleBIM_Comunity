#!/usr/bin/env python3
"""
IFC Background Converter - Conversie automată și robustă în IFC
Convertește automat toate elementele din DXF în IFC în timpul procesării GLB,
cu mapare automată a layerelor și metadata complete.
"""

import json
import os
import re
import threading
import time
from typing import Dict, List, Tuple, Any, Optional
import ifcopenshell
import ifcopenshell.api
import ifcopenshell.util.unit
import uuid as uuid_module
from datetime import datetime

# Maparea layerelor către tipurile IFC
IFC_LAYER_MAPPING = {
    # Structural Elements
    'IfcWall': 'IfcWall',
    'IfcColumn': 'IfcColumn', 
    'IfcBeam': 'IfcBeam',
    'IfcSlab': 'IfcSlab',
    'IfcFooting': 'IfcFooting',
    'IfcPile': 'IfcPile',
    
    # Spaces and Zones
    'IfcSpace': 'IfcSpace',
    'IfcZone': 'IfcZone',
    
    # Building Elements
    'IfcDoor': 'IfcDoor',
    'IfcWindow': 'IfcWindow',
    'IfcStair': 'IfcStair',
    'IfcRamp': 'IfcRamp',
    'IfcRoof': 'IfcRoof',
    'IfcCurtainWall': 'IfcCurtainWall',
    
    # Building Service Elements
    'IfcPipe': 'IfcPipe',
    'IfcDuct': 'IfcDuct',
    'IfcCableCarrierFitting': 'IfcCableCarrierFitting',
    'IfcElectricAppliance': 'IfcElectricAppliance',
    
    # Furnishing Elements
    'IfcFurniture': 'IfcFurniture',
    'IfcSystemFurnitureElement': 'IfcSystemFurnitureElement',
    
    # Site Elements
    'IfcSite': 'IfcSite',
    'IfcBuilding': 'IfcBuilding',
    'IfcBuildingStorey': 'IfcBuildingStorey',
    
    # Generic
    'IfcBuildingElement': 'IfcBuildingElement',
    'IfcBuildingElementProxy': 'IfcBuildingElementProxy'
}

# Predefined Types pentru fiecare tip IFC
IFC_PREDEFINED_TYPES = {
    'IfcWall': ['STANDARD', 'POLYGONAL', 'SHEAR', 'CORE', 'PLASTERWALL', 'PARAPET', 'PARTITIONING', 'SOLIDWALL', 'RETAININGWALL', 'MOVABLE', 'ELEMENTEDWALL'],
    'IfcColumn': ['COLUMN', 'PILASTER', 'PIERSTEM', 'PIERSTEM_SEGMENT'],
    'IfcBeam': ['BEAM', 'JOIST', 'HOLLOWCORE', 'LINTEL', 'SPANDREL', 'T_BEAM'],
    'IfcSlab': ['FLOOR', 'ROOF', 'LANDING', 'BASESLAB'],
    'IfcSpace': ['INTERNAL', 'EXTERNAL', 'GFA', 'PARKING'],
    'IfcDoor': ['DOOR', 'GATE', 'TRAPDOOR'],
    'IfcWindow': ['WINDOW', 'SKYLIGHT', 'LIGHTDOME'],
    'IfcStair': ['STRAIGHT_RUN_STAIR', 'TWO_STRAIGHT_RUN_STAIR', 'QUARTER_WINDING_STAIR', 'QUARTER_TURN_STAIR', 'HALF_WINDING_STAIR', 'HALF_TURN_STAIR', 'TWO_QUARTER_WINDING_STAIR', 'TWO_QUARTER_TURN_STAIR', 'THREE_QUARTER_WINDING_STAIR', 'THREE_QUARTER_TURN_STAIR', 'SPIRAL_STAIR', 'DOUBLE_RETURN_STAIR', 'CURVED_RUN_STAIR', 'FREEFORM_STAIR'],
    'IfcRoof': ['FLAT_ROOF', 'SHED_ROOF', 'GABLE_ROOF', 'HIP_ROOF', 'HIPPED_GABLE_ROOF', 'GAMBREL_ROOF', 'MANSARD_ROOF', 'BARREL_ROOF', 'RAINBOW_ROOF', 'BUTTERFLY_ROOF', 'PAVILION_ROOF', 'DOME_ROOF', 'FREEFORM']
}

class IfcBackgroundConverter:
    """Converter IFC care rulează în background în timpul procesării DXF→GLB"""
    
    def __init__(self, project_name: str = "Auto-Generated IFC"):
        self.project_name = project_name
        self.model = None
        self.project = None
        self.site = None
        self.building = None
        self.storey = None
        self.owner_history = None
        self.context = None
        self.units = None
        self.conversion_thread = None
        self.conversion_data = []
        self.conversion_complete = False
        
    def queue_element_for_conversion(self, element_data: Dict[str, Any]):
        """Adaugă un element în coada de conversie IFC"""
        self.conversion_data.append(element_data.copy())
        
    def start_background_conversion(self, output_ifc_path: str):
        """Pornește conversia IFC în background"""
        print(f"[DEBUG] Starting background IFC conversion to: {output_ifc_path}")
        
        self.conversion_thread = threading.Thread(
            target=self._background_conversion_worker,
            args=(output_ifc_path,),
            daemon=True
        )
        self.conversion_thread.start()
        
    def _background_conversion_worker(self, output_ifc_path: str):
        """Worker thread pentru conversia IFC în background"""
        try:
            print(f"[DEBUG] Background IFC conversion started with {len(self.conversion_data)} elements")
            
            # Creează modelul IFC
            self._create_ifc_model()
            
            # Procesează toate elementele din coadă
            for element_data in self.conversion_data:
                self._convert_element_to_ifc(element_data)
                
            # Salvează fișierul IFC
            self._save_ifc_file(output_ifc_path)
            
            self.conversion_complete = True
            print(f"[SUCCESS] Background IFC conversion completed: {output_ifc_path}")
            
        except Exception as e:
            print(f"[ERROR] Background IFC conversion failed: {e}")
            import traceback
            traceback.print_exc()
            
    def _create_ifc_model(self):
        """Creează modelul IFC cu structurile de bază"""
        print(f"[DEBUG] Creating IFC model: {self.project_name}")
        
        # Creează modelul IFC 4
        self.model = ifcopenshell.file(schema="IFC4")
        
        # Creează contextul de aplicație
        application = self.model.create_entity("IfcApplication", 
            ApplicationDeveloper=self.model.create_entity("IfcOrganization", Name="Godot CAD Viewer"),
            Version="2.0",
            ApplicationFullName="Godot CAD Viewer Background IFC Converter",
            ApplicationIdentifier="GodotCADViewer_BG"
        )
        
        # Creează persoana și organizația
        person = self.model.create_entity("IfcPerson",
            FamilyName="User",
            GivenName="Auto"
        )
        
        organization = self.model.create_entity("IfcOrganization",
            Name="Auto Generated"
        )
        
        person_and_organization = self.model.create_entity("IfcPersonAndOrganization",
            ThePerson=person,
            TheOrganization=organization
        )
        
        # Creează owner history
        self.owner_history = self.model.create_entity("IfcOwnerHistory",
            OwningUser=person_and_organization,
            OwningApplication=application,
            State="READWRITE",
            ChangeAction="ADDED",
            LastModifiedDate=int(time.time()),
            LastModifyingUser=person_and_organization,
            LastModifyingApplication=application,
            CreationDate=int(time.time())
        )
        
        # Creează unitățile
        self._create_units()
        
        # Creează contextul geometric
        self._create_geometric_context()
        
        # Creează ierarhia proiectului
        self._create_project_hierarchy()
        
    def _create_units(self):
        """Creează unitățile pentru modelul IFC"""
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
        
        # Creează assignment-ul unitățiilor
        self.units = self.model.create_entity("IfcUnitAssignment",
            Units=[length_unit, area_unit, volume_unit, angle_unit]
        )
        
    def _create_geometric_context(self):
        """Creează contextul geometric pentru modelul IFC"""
        # Context geometric 3D
        self.context = self.model.create_entity("IfcGeometricRepresentationContext",
            ContextType="Model",
            CoordinateSpaceDimension=3,
            Precision=1.0E-05,
            WorldCoordinateSystem=self.model.create_entity("IfcAxis2Placement3D",
                Location=self.model.create_entity("IfcCartesianPoint", Coordinates=[0., 0., 0.])
            ),
            TrueNorth=self.model.create_entity("IfcDirection", DirectionRatios=[0., 1., 0.])
        )
        
    def _create_project_hierarchy(self):
        """Creează ierarhia proiectului: Project → Site → Building → Storey"""
        # Creează proiectul
        self.project = self.model.create_entity("IfcProject",
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=self.owner_history,
            Name=self.project_name,
            Description="Auto-generated IFC from DXF via Godot CAD Viewer",
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
            Name="Ground Floor",
            CompositionType="ELEMENT",
            Elevation=0.0
        )
        
        # Creează relațiile ierarhice
        # Project agregă Site
        self.model.create_entity("IfcRelAggregates",
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=self.owner_history,
            RelatingObject=self.project,
            RelatedObjects=[self.site]
        )
        
        # Site agregă Building
        self.model.create_entity("IfcRelAggregates",
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=self.owner_history,
            RelatingObject=self.site,
            RelatedObjects=[self.building]
        )
        
        # Building agregă Storey
        self.model.create_entity("IfcRelAggregates",
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=self.owner_history,
            RelatingObject=self.building,
            RelatedObjects=[self.storey]
        )
        
    def _convert_element_to_ifc(self, element_data: Dict[str, Any]):
        """Convertește un element în entitate IFC"""
        try:
            layer = element_data.get('layer', 'Unknown')
            mesh_name = element_data.get('mesh_name', f'Element_{len(self.conversion_data)}')
            
            # Determină tipul IFC din layer
            ifc_type = self._determine_ifc_type(layer)
            
            print(f"[DEBUG] Converting {mesh_name} (layer: {layer}) to {ifc_type}")
            
            # Creează entitatea IFC corespunzătoare
            if ifc_type == 'IfcSpace':
                self._create_ifc_space(element_data, ifc_type)
            elif ifc_type == 'IfcProxy':
                self._create_ifc_proxy(element_data)
            else:
                self._create_ifc_building_element(element_data, ifc_type)
                
        except Exception as e:
            print(f"[ERROR] Failed to convert element {element_data.get('mesh_name', 'Unknown')}: {e}")
            
    def _determine_ifc_type(self, layer: str) -> str:
        """Determină tipul IFC din numele layerului"""
        # Verifică maparea directă
        if layer in IFC_LAYER_MAPPING:
            return IFC_LAYER_MAPPING[layer]
            
        # Verifică prefixe și pattern-uri comune
        layer_lower = layer.lower()
        
        if any(wall_pattern in layer_lower for wall_pattern in ['wall', 'zid', 'perete']):
            return 'IfcWall'
        elif any(column_pattern in layer_lower for column_pattern in ['column', 'coloana', 'stalp']):
            return 'IfcColumn'
        elif any(beam_pattern in layer_lower for beam_pattern in ['beam', 'grinda', 'joist']):
            return 'IfcBeam'
        elif any(slab_pattern in layer_lower for slab_pattern in ['slab', 'placa', 'floor', 'pardoseala']):
            return 'IfcSlab'
        elif any(door_pattern in layer_lower for door_pattern in ['door', 'usa', 'gate']):
            return 'IfcDoor'
        elif any(window_pattern in layer_lower for window_pattern in ['window', 'fereastra', 'geam']):
            return 'IfcWindow'
        elif any(space_pattern in layer_lower for space_pattern in ['space', 'spatiu', 'room', 'camera']):
            return 'IfcSpace'
        elif any(stair_pattern in layer_lower for stair_pattern in ['stair', 'scara', 'steps']):
            return 'IfcStair'
        elif any(roof_pattern in layer_lower for roof_pattern in ['roof', 'acoperis', 'cover']):
            return 'IfcRoof'
        else:
            return 'IfcProxy'  # Fallback pentru elemente nerecunoscute
            
    def _get_predefined_type(self, ifc_type: str, element_data: Dict[str, Any]) -> Optional[str]:
        """Determină PredefinedType pentru un tip IFC"""
        if ifc_type not in IFC_PREDEFINED_TYPES:
            return None
            
        available_types = IFC_PREDEFINED_TYPES[ifc_type]
        
        # Pentru IfcSpace, încearcă să determine tipul din context
        if ifc_type == 'IfcSpace':
            mesh_name = element_data.get('mesh_name', '').lower()
            if any(internal in mesh_name for internal in ['living', 'bedroom', 'kitchen', 'bathroom', 'office']):
                return 'INTERNAL'
            elif any(external in mesh_name for external in ['balcony', 'terrace', 'garden']):
                return 'EXTERNAL'
            else:
                return 'INTERNAL'  # Default
                
        # Pentru IfcWall
        elif ifc_type == 'IfcWall':
            return 'STANDARD'  # Default
            
        # Pentru IfcSlab
        elif ifc_type == 'IfcSlab':
            layer = element_data.get('layer', '').lower()
            if 'floor' in layer or 'pardoseala' in layer:
                return 'FLOOR'
            elif 'roof' in layer or 'acoperis' in layer:
                return 'ROOF'
            else:
                return 'FLOOR'  # Default
                
        # Default pentru alte tipuri
        return available_types[0] if available_types else None
        
    def _create_ifc_space(self, element_data: Dict[str, Any], ifc_type: str):
        """Creează o entitate IfcSpace"""
        mesh_name = element_data.get('mesh_name', 'Space')
        predefined_type = self._get_predefined_type(ifc_type, element_data)
        
        # Creează IfcSpace
        space = self.model.create_entity("IfcSpace",
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=self.owner_history,
            Name=mesh_name,
            CompositionType="ELEMENT",
            PredefinedType=predefined_type
        )
        
        # Adaugă spațiul la etaj
        self.model.create_entity("IfcRelContainedInSpatialStructure",
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=self.owner_history,
            RelatedElements=[space],
            RelatingStructure=self.storey
        )
        
        # Creează geometria dacă există
        if 'vertices' in element_data and 'triangles' in element_data:
            self._create_mesh_geometry(space, element_data)
            
        # Adaugă proprietățile
        self._add_element_properties(space, element_data)
        
    def _create_ifc_building_element(self, element_data: Dict[str, Any], ifc_type: str):
        """Creează o entitate IFC de tip building element"""
        mesh_name = element_data.get('mesh_name', 'Element')
        predefined_type = self._get_predefined_type(ifc_type, element_data)
        
        # Creează entitatea IFC
        element = self.model.create_entity(ifc_type,
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=self.owner_history,
            Name=mesh_name,
            PredefinedType=predefined_type
        )
        
        # Adaugă elementul la etaj
        self.model.create_entity("IfcRelContainedInSpatialStructure",
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=self.owner_history,
            RelatedElements=[element],
            RelatingStructure=self.storey
        )
        
        # Creează geometria dacă există
        if 'vertices' in element_data and 'triangles' in element_data:
            self._create_mesh_geometry(element, element_data)
            
        # Adaugă proprietățile
        self._add_element_properties(element, element_data)
        
    def _create_ifc_proxy(self, element_data: Dict[str, Any]):
        """Creează o entitate IfcProxy pentru elemente nerecunoscute"""
        mesh_name = element_data.get('mesh_name', 'Proxy')
        layer = element_data.get('layer', 'Unknown')
        
        # Creează IfcProxy
        proxy = self.model.create_entity("IfcProxy",
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=self.owner_history,
            Name=mesh_name,
            ProxyType="NOTDEFINED",
            Tag=layer  # Salvează layer-ul original în Tag
        )
        
        # Adaugă proxy-ul la etaj
        self.model.create_entity("IfcRelContainedInSpatialStructure",
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=self.owner_history,
            RelatedElements=[proxy],
            RelatingStructure=self.storey
        )
        
        # Creează geometria dacă există
        if 'vertices' in element_data and 'triangles' in element_data:
            self._create_mesh_geometry(proxy, element_data)
            
        # Adaugă proprietățile
        self._add_element_properties(proxy, element_data)
        
    def _create_mesh_geometry(self, ifc_element, element_data: Dict[str, Any]):
        """Creează geometria mesh pentru un element IFC"""
        try:
            vertices = element_data.get('vertices', [])
            triangles = element_data.get('triangles', [])
            
            if not vertices or not triangles:
                return
                
            # Creează punctele 3D
            points = []
            for vertex in vertices:
                if len(vertex) >= 3:
                    points.append(self.model.create_entity("IfcCartesianPoint", 
                                                        Coordinates=[float(vertex[0]), float(vertex[1]), float(vertex[2])]))
            
            # Creează fețele triunghiulare
            faces = []
            for triangle in triangles:
                if len(triangle) >= 3:
                    # Creează o față triunghiulară
                    face_bound = self.model.create_entity("IfcFaceOuterBound",
                        Bound=self.model.create_entity("IfcPolyLoop",
                            Polygon=[points[triangle[0]], points[triangle[1]], points[triangle[2]]]
                        ),
                        Orientation=True
                    )
                    
                    faces.append(self.model.create_entity("IfcFace",
                        Bounds=[face_bound]
                    ))
            
            if faces:
                # Creează shell-ul închis
                closed_shell = self.model.create_entity("IfcClosedShell",
                    CfsFaces=faces
                )
                
                # Creează reprezentarea geometrică
                solid = self.model.create_entity("IfcManifoldSolidBrep",
                    Outer=closed_shell
                )
                
                # Creează forma și reprezentarea
                shape_representation = self.model.create_entity("IfcShapeRepresentation",
                    ContextOfItems=self.context,
                    RepresentationIdentifier="Body",
                    RepresentationType="Brep",
                    Items=[solid]
                )
                
                # Asociază reprezentarea cu elementul
                product_representation = self.model.create_entity("IfcProductDefinitionShape",
                    Representations=[shape_representation]
                )
                
                ifc_element.Representation = product_representation
                
        except Exception as e:
            print(f"[WARNING] Failed to create geometry for {element_data.get('mesh_name', 'Unknown')}: {e}")
            
    def _add_element_properties(self, ifc_element, element_data: Dict[str, Any]):
        """Adaugă proprietățile calculate la un element IFC"""
        try:
            # Creează property set-ul
            properties = []
            
            # Proprietăți geometrice standard
            if 'area' in element_data:
                properties.append(self.model.create_entity("IfcPropertySingleValue",
                    Name="Area",
                    NominalValue=self.model.create_entity("IfcAreaMeasure", element_data['area'])
                ))
                
            if 'perimeter' in element_data:
                properties.append(self.model.create_entity("IfcPropertySingleValue",
                    Name="Perimeter", 
                    NominalValue=self.model.create_entity("IfcLengthMeasure", element_data['perimeter'])
                ))
                
            if 'lateral_area' in element_data:
                properties.append(self.model.create_entity("IfcPropertySingleValue",
                    Name="LateralArea",
                    NominalValue=self.model.create_entity("IfcAreaMeasure", element_data['lateral_area'])
                ))
                
            if 'volume' in element_data:
                properties.append(self.model.create_entity("IfcPropertySingleValue",
                    Name="Volume",
                    NominalValue=self.model.create_entity("IfcVolumeMeasure", element_data['volume'])
                ))
                
            if 'height' in element_data:
                properties.append(self.model.create_entity("IfcPropertySingleValue",
                    Name="Height",
                    NominalValue=self.model.create_entity("IfcLengthMeasure", element_data['height'])
                ))
                
            # Proprietăți custom
            if 'uuid' in element_data:
                properties.append(self.model.create_entity("IfcPropertySingleValue",
                    Name="GodotUUID",
                    NominalValue=self.model.create_entity("IfcText", element_data['uuid'])
                ))
                
            if 'layer' in element_data:
                properties.append(self.model.create_entity("IfcPropertySingleValue",
                    Name="OriginalLayer",
                    NominalValue=self.model.create_entity("IfcText", element_data['layer'])
                ))
                
            # Informații despre XDATA dacă există
            if '_opening_area_calculated' in element_data:
                properties.append(self.model.create_entity("IfcPropertySingleValue",
                    Name="OpeningAreaDeducted",
                    NominalValue=self.model.create_entity("IfcAreaMeasure", element_data['_opening_area_calculated'])
                ))
                
            if properties:
                # Creează property set-ul
                property_set = self.model.create_entity("IfcPropertySet",
                    GlobalId=ifcopenshell.guid.new(),
                    OwnerHistory=self.owner_history,
                    Name="AutoGeneratedProperties",
                    HasProperties=properties
                )
                
                # Asociază property set-ul cu elementul
                self.model.create_entity("IfcRelDefinesByProperties",
                    GlobalId=ifcopenshell.guid.new(),
                    OwnerHistory=self.owner_history,
                    RelatedObjects=[ifc_element],
                    RelatingPropertyDefinition=property_set
                )
                
        except Exception as e:
            print(f"[WARNING] Failed to add properties for {element_data.get('mesh_name', 'Unknown')}: {e}")
            
    def _save_ifc_file(self, output_path: str):
        """Salvează modelul IFC în fișier"""
        try:
            self.model.write(output_path)
            print(f"[DEBUG] IFC file saved: {output_path}")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to save IFC file: {e}")
            return False
            
    def wait_for_completion(self, timeout: float = 30.0):
        """Așteaptă finalizarea conversiei cu timeout"""
        if self.conversion_thread:
            self.conversion_thread.join(timeout=timeout)
            return self.conversion_complete
        return False
        
    def is_conversion_complete(self) -> bool:
        """Verifică dacă conversia s-a finalizat"""
        return self.conversion_complete


# Funcții helper pentru integrarea cu procesarea existentă
def create_background_converter(project_name: str = None) -> IfcBackgroundConverter:
    """Creează un converter IFC pentru background processing"""
    if not project_name:
        project_name = f"Auto_IFC_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    return IfcBackgroundConverter(project_name)

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
        return None
    
    try:
        result = eval(formula)
        return result
    except Exception:
        return None

def process_xdata_for_element(element_data):
    """Procesează XDATA pentru un element și calculează proprietățile ajustate"""
    if not isinstance(element_data, dict):
        return element_data
    
    # Verifică dacă are XDATA cu Opening_area
    xdata = element_data.get('xdata', {})
    if not xdata or not isinstance(xdata, dict):
        return element_data
    
    # Caută Opening_area în XDATA
    opening_area_formula = None
    if 'ACAD' in xdata and isinstance(xdata['ACAD'], dict):
        opening_area_formula = xdata['ACAD'].get('Opening_area')
    else:
        opening_area_formula = xdata.get('Opening_area')
    
    if not opening_area_formula:
        return element_data
    
    # Evaluează formula
    opening_area_value = evaluate_math_formula(opening_area_formula)
    
    if opening_area_value is not None:
        # Calculează lateral area ajustată
        original_lateral_area = element_data.get('lateral_area', 0)
        adjusted_lateral_area = original_lateral_area - opening_area_value
        
        # Actualizează datele
        processed_data = dict(element_data)
        processed_data['lateral_area'] = adjusted_lateral_area
        processed_data['_opening_area_calculated'] = opening_area_value
        
        return processed_data
    
    return element_data