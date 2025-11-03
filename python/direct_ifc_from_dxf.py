#!/usr/bin/env python3
"""
Direct IFC 4 Export from DXF with XDATA
Construiește geometria IFC direct din DXF-uri folosind IfcOpenShell, citind XDATA pentru proprietăți.
Cea mai simplă abordare pentru export IFC cu unități metric/imperial.
"""

import sys
import os
import ezdxf
import ifcopenshell
import ifcopenshell.api
import uuid
from datetime import datetime
from typing import List, Dict, Any
import math

# Verifică disponibilitatea IfcOpenShell
try:
    import ifcopenshell
    import ifcopenshell.api.root
    import ifcopenshell.api.unit
    import ifcopenshell.api.context
    import ifcopenshell.api.project
    import ifcopenshell.api.spatial
    import ifcopenshell.api.geometry
    IFC_AVAILABLE = True
    print("[DEBUG] IfcOpenShell loaded successfully")
except ImportError as e:
    print(f"[ERROR] IfcOpenShell not available: {e}")
    IFC_AVAILABLE = False


class DirectIfcExporter:
    """Exportor IFC direct din DXF cu XDATA"""
    
    def __init__(self, project_name: str = "Multi-Story Building", unit_system: str = "metric"):
        self.project_name = project_name
        self.unit_system = unit_system  # "metric" sau "imperial"
        self.model = None
        self.project = None
        self.site = None
        self.building = None
        self.storeys = {}  # filename -> storey
        self.elements_created = 0
        
        # Factori de conversie pentru imperial
        self.length_conversion = 1.0  # Default metric (meters)
        self.area_conversion = 1.0
        self.volume_conversion = 1.0
        
        if unit_system == "imperial":
            # Conversie din metri în feet
            self.length_conversion = 3.28084  # 1m = 3.28084 feet
            self.area_conversion = 10.7639    # 1m² = 10.7639 sq ft
            self.volume_conversion = 35.3147  # 1m³ = 35.3147 cu ft
    
    def create_ifc_model(self):
        """Creează modelul IFC 4 cu structura de bază"""
        print(f"[IFC] Creating IFC 4 model: {self.project_name} ({self.unit_system})")
        
        if not IFC_AVAILABLE:
            raise Exception("IfcOpenShell not available")
        
        # Creează modelul IFC 4
        self.model = ifcopenshell.file(schema="IFC4")
        
        # Creează proiectul
        self.project = ifcopenshell.api.root.create_entity(self.model, ifc_class="IfcProject", name=self.project_name)
        
        # Setează unitățile
        if self.unit_system == "metric":
            ifcopenshell.api.unit.assign_unit(self.model, length={"is_metric": True, "raw": "METRE"})
        else:  # imperial
            ifcopenshell.api.unit.assign_unit(self.model, length={"is_metric": False, "raw": "FOOT"})
        
        # Creează contextul geometric
        context = ifcopenshell.api.context.add_context(self.model, context_type="Model")
        body_context = ifcopenshell.api.context.add_context(
            self.model, 
            context_type="Model", 
            context_identifier="Body", 
            target_view="MODEL_VIEW", 
            parent=context
        )
        
        # Creează site-ul
        self.site = ifcopenshell.api.root.create_entity(self.model, ifc_class="IfcSite", name="Building Site")
        ifcopenshell.api.aggregate.assign_object(self.model, products=[self.site], relating_object=self.project)
        
        # Creează clădirea
        self.building = ifcopenshell.api.root.create_entity(self.model, ifc_class="IfcBuilding", name="Multi-Story Building")
        ifcopenshell.api.aggregate.assign_object(self.model, products=[self.building], relating_object=self.site)
        
        print(f"[IFC] Project structure created with {self.unit_system} units")
    
    def extract_global_z_from_filename(self, filename: str) -> float:
        """Extrage Z global din numele fișierului (ex: level_3.50.dxf -> 3.50)"""
        try:
            # Caută pattern-uri comune pentru Z în nume
            import re
            patterns = [
                r'[\._](-?\d+\.\d+)[\._]',  # level_3.50.dxf sau level.3.50.dxf
                r'[\._](-?\d+\.?\d*)[\._]', # level_3_50.dxf sau level_3.dxf
                r'_(-?\d+\.\d+)$',          # level_3.50
                r'_(-?\d+)$',               # level_3
            ]
            
            basename = os.path.splitext(os.path.basename(filename))[0]
            for pattern in patterns:
                match = re.search(pattern, basename)
                if match:
                    z_value = float(match.group(1))
                    print(f"[DXF] Extracted Z={z_value} from filename: {filename}")
                    return z_value
            
            print(f"[WARNING] No Z coordinate found in filename: {filename}, using 0.0")
            return 0.0
            
        except Exception as e:
            print(f"[ERROR] Failed to extract Z from filename {filename}: {e}")
            return 0.0
    
    def process_dxf_file(self, dxf_path: str):
        """Procesează un fișier DXF și creează un nivel în IFC cu suport pentru solid/void"""
        print(f"[DXF] Processing: {dxf_path}")
        
        try:
            # Încarcă DXF-ul
            doc = ezdxf.readfile(dxf_path)
            msp = doc.modelspace()
            
            # Extrage Z global din filename
            global_z = self.extract_global_z_from_filename(dxf_path)
            
            # Creează nivelul (IfcBuildingStorey)
            storey_name = os.path.splitext(os.path.basename(dxf_path))[0]
            storey = ifcopenshell.api.root.create_entity(self.model, ifc_class="IfcBuildingStorey", name=storey_name)
            
            # Setează elevația nivelului (convertită la unități corespunzătoare)
            storey.Elevation = global_z * self.length_conversion
            
            # Asociază nivelul cu clădirea (folosește aggregate pentru ierarhie spațială)
            ifcopenshell.api.aggregate.assign_object(self.model, products=[storey], relating_object=self.building)
            
            # Stochează nivelul
            self.storeys[dxf_path] = storey
            
            # Colectează elementele în funcție de flag-ul solid
            solid_elements = []  # solid=1 sau lipsă
            void_elements = []   # solid=0 (pentru cutting)
            
            # Procesează entitățile din DXF
            for entity in msp:
                xdata_props = self._extract_xdata_properties(entity)
                solid_flag = xdata_props.get('solid', 1)  # Default solid
                
                element_data = self._process_dxf_entity_geometry(entity, storey, global_z, xdata_props)
                
                if element_data:
                    if solid_flag == 0:
                        void_elements.append(element_data)
                        print(f"[DEBUG] Added VOID element: {element_data['name']} (layer: {element_data['layer']})")
                    else:
                        solid_elements.append(element_data)
            
            print(f"[DEBUG] Level {storey_name}: {len(solid_elements)} solids, {len(void_elements)} voids")
            
            # Aplică operațiile booleene: voids taie solids
            final_elements = self._apply_boolean_operations(solid_elements, void_elements, storey)
            
            elements_in_storey = len(final_elements)
            self.elements_created += elements_in_storey
            
            print(f"[IFC] Created storey '{storey_name}' at Z={global_z} with {elements_in_storey} elements")
            
        except Exception as e:
            print(f"[ERROR] Failed to process DXF {dxf_path}: {e}")
    
    def _process_dxf_entity_geometry(self, entity, storey, global_z: float, xdata_props: Dict) -> Dict:
        """Procesează geometria unei entități fără să creeze elementul IFC încă"""
        try:
            # Determină tipul IFC din layer
            layer = entity.dxf.layer if hasattr(entity.dxf, 'layer') else "default"
            ifc_type = self._determine_ifc_type(entity, layer)
            
            if ifc_type == "SKIP":
                return None
            
            # Returnează datele pentru procesare ulterioară
            element_name = f"{layer}_{entity.dxf.handle}" if hasattr(entity.dxf, 'handle') else f"{layer}_element"
            
            return {
                'entity': entity,
                'ifc_type': ifc_type,
                'name': element_name,
                'layer': layer,
                'xdata': xdata_props,
                'global_z': global_z
            }
            
        except Exception as e:
            print(f"[WARNING] Failed to process entity geometry: {e}")
            return None
    
    def _apply_boolean_operations(self, solid_elements: List[Dict], void_elements: List[Dict], storey) -> List:
        """Aplică operațiile booleene între solids și voids, apoi creează elementele IFC"""
        final_elements = []
        
        # Grupează void-urile pe tipul de layer țintă (similar cu logica din dxf_to_glb_trimesh.py)
        # IfcWindow voids taie doar IfcWall și IfcCovering
        # void layer (generic) taie toate
        window_voids = [v for v in void_elements if v['layer'] == 'IfcWindow']
        generic_voids = [v for v in void_elements if v['layer'] != 'IfcWindow']
        
        print(f"[DEBUG] Boolean ops: {len(solid_elements)} solids, {len(window_voids)} window voids, {len(generic_voids)} generic voids")
        
        # Procesează fiecare element solid
        for solid_data in solid_elements:
            try:
                # Creează elementul IFC
                ifc_element = ifcopenshell.api.root.create_entity(
                    self.model, 
                    ifc_class=solid_data['ifc_type'], 
                    name=solid_data['name']
                )
                
                # Asociază cu nivelul
                ifcopenshell.api.spatial.assign_container(
                    self.model, 
                    products=[ifc_element], 
                    relating_structure=storey
                )
                
                # Creează geometria de bază (cu height din XDATA)
                height = solid_data['xdata'].get('height', 0.1)
                self._create_ifc_geometry(solid_data['entity'], ifc_element, solid_data['global_z'], height)
                
                # Aplică voids dacă este cazul
                # IfcWindow voids taie doar IfcWall și IfcCovering
                target_layers_for_windows = ['IfcWall', 'IfcCovering']
                if solid_data['layer'] in target_layers_for_windows and window_voids:
                    print(f"[DEBUG] Applying {len(window_voids)} window voids to {solid_data['name']}")
                    # TODO: Aici ar trebui să aplicăm cutting prin IfcOpeningElement
                    # Pentru moment doar notăm că ar trebui tăiat
                    for void_data in window_voids:
                        self._apply_opening_to_element(ifc_element, void_data, solid_data['global_z'])
                
                # Generic voids taie tot
                if generic_voids:
                    print(f"[DEBUG] Applying {len(generic_voids)} generic voids to {solid_data['name']}")
                    for void_data in generic_voids:
                        self._apply_opening_to_element(ifc_element, void_data, solid_data['global_z'])
                
                # Adaugă proprietăți din XDATA
                self._add_properties_from_xdata(ifc_element, solid_data['xdata'], solid_data['layer'])
                
                final_elements.append(ifc_element)
                
            except Exception as e:
                print(f"[WARNING] Failed to create IFC element {solid_data['name']}: {e}")
        
        return final_elements
    
    def _apply_opening_to_element(self, ifc_element, void_data: Dict, global_z: float):
        """Aplică un opening (void) la un element IFC folosind IfcOpeningElement"""
        try:
            # Creează IfcOpeningElement pentru void
            opening = ifcopenshell.api.root.create_entity(
                self.model,
                ifc_class="IfcOpeningElement",
                name=f"Opening_{void_data['name']}"
            )
            
            # Creează geometria pentru opening (cu height din XDATA)
            height = void_data['xdata'].get('height', 0.1)
            self._create_ifc_geometry(void_data['entity'], opening, global_z, height)
            
            # Creează relația de void între element și opening
            ifcopenshell.api.run("void.add_opening", self.model,
                opening=opening,
                element=ifc_element
            )
            
            print(f"[DEBUG] Applied opening {void_data['name']} to {ifc_element.Name}")
            
        except Exception as e:
            print(f"[WARNING] Failed to apply opening: {e}")
    
    def _process_dxf_entity(self, entity, storey, global_z: float):
        """Procesează o entitate DXF și creează elementul IFC corespunzător"""
        try:
            # Determină tipul IFC din layer sau proprietăți
            layer = entity.dxf.layer if hasattr(entity.dxf, 'layer') else "default"
            ifc_type = self._determine_ifc_type(entity, layer)
            
            if ifc_type == "SKIP":
                return None
            
            # Extrage XDATA pentru proprietăți
            xdata_props = self._extract_xdata_properties(entity)
            
            # Creează elementul IFC
            element_name = f"{layer}_{entity.dxf.handle}" if hasattr(entity.dxf, 'handle') else f"{layer}_element"
            ifc_element = ifcopenshell.api.root.create_entity(self.model, ifc_class=ifc_type, name=element_name)
            
            # Asociază elementul cu nivelul
            ifcopenshell.api.spatial.assign_container(self.model, products=[ifc_element], relating_structure=storey)
            
            # Creează geometria dacă e posibil
            self._create_ifc_geometry(entity, ifc_element, global_z)
            
            # Adaugă proprietăți din XDATA
            self._add_properties_from_xdata(ifc_element, xdata_props, layer)
            
            return ifc_element
            
        except Exception as e:
            print(f"[WARNING] Failed to process entity {entity}: {e}")
            return None
    
    def _determine_ifc_type(self, entity, layer: str) -> str:
        """Determină tipul IFC din layer sau tip entitate"""
        # Mapare layer -> tip IFC
        layer_mapping = {
            "wall": "IfcWall",
            "walls": "IfcWall", 
            "muri": "IfcWall",
            "column": "IfcColumn",
            "columns": "IfcColumn",
            "stâlpi": "IfcColumn",
            "beam": "IfcBeam",
            "beams": "IfcBeam", 
            "grinzi": "IfcBeam",
            "slab": "IfcSlab",
            "slabs": "IfcSlab",
            "plăci": "IfcSlab",
            "door": "IfcDoor",
            "doors": "IfcDoor",
            "uși": "IfcDoor",
            "window": "IfcWindow",
            "windows": "IfcWindow",
            "ferestre": "IfcWindow",
            "space": "IfcSpace",
            "spaces": "IfcSpace",
            "spații": "IfcSpace",
            "ifcspace": "IfcSpace",
            "roof": "IfcRoof",
            "acoperis": "IfcRoof"
        }
        
        # Încearcă maparea pe layer
        layer_lower = layer.lower()
        for key, ifc_type in layer_mapping.items():
            if key in layer_lower:
                return ifc_type
        
        # Verifică tipul entității DXF
        entity_type = entity.dxftype()
        if entity_type in ["LWPOLYLINE", "POLYLINE", "LINE", "ARC", "CIRCLE"]:
            return "IfcBuildingElementProxy"
        elif entity_type in ["3DFACE", "3DSOLID", "MESH"]:
            return "IfcBuildingElementProxy"
        elif entity_type in ["TEXT", "MTEXT", "DIMENSION"]:
            return "SKIP"  # Skip text și dimensiuni
        
        # Default
        return "IfcBuildingElementProxy"
    
    def _extract_xdata_properties(self, entity) -> Dict[str, Any]:
        """Extrage proprietățile din XDATA inclusiv flag-ul solid și height pentru operații booleene"""
        properties = {}
        
        try:
            if hasattr(entity, 'has_xdata') and entity.has_xdata:
                # Obține lista de application IDs
                appids = []
                if hasattr(entity, 'get_xdata_appids'):
                    appids = list(entity.get_xdata_appids())
                
                # Dacă nu există QCAD, adaugă-l la listă pentru a încerca
                if "QCAD" not in appids:
                    appids.append("QCAD")
                
                for app_id in appids:
                    try:
                        xdata_list = entity.get_xdata(app_id)
                        if xdata_list:
                            # xdata_list este o listă de tuple-uri (code, value)
                            for item in xdata_list:
                                if isinstance(item, tuple) and len(item) >= 2:
                                    code, value = item[0], item[1]
                                    
                                    # Code 1000: String (folosit pentru height:VALUE, solid:VALUE, etc.)
                                    if code == 1000:
                                        sval = str(value)
                                        
                                        # Pattern-uri QCAD: "height:2.8", "solid:1", "Name:wall", etc.
                                        if sval.startswith("height:"):
                                            try:
                                                properties['height'] = float(sval.split(":")[1])
                                            except Exception:
                                                pass
                                        elif sval.startswith("solid:"):
                                            try:
                                                properties['solid'] = int(sval.split(":")[1])
                                            except Exception:
                                                pass
                                        elif sval.startswith("Name:"):
                                            properties['name'] = sval.split(":", 1)[1].strip()
                                        elif sval.startswith("z:"):
                                            try:
                                                properties['z_relative'] = float(sval.split(":")[1])
                                            except Exception:
                                                pass
                                        else:
                                            # Alte proprietăți string
                                            properties[f"xdata_{app_id}"] = value
                                    
                                    # Code 1040: Real (număr floating point)
                                    elif code == 1040:
                                        if 'height' not in properties:
                                            properties['height'] = float(value)
                                    
                                    # Code 1071: Integer (pentru flag-uri)
                                    elif code == 1071:
                                        if isinstance(value, int) and value in [0, 1]:
                                            if 'solid' not in properties:
                                                properties['solid'] = value
                    
                    except Exception as ex:
                        print(f"[DEBUG] XDATA error for appid {app_id}: {ex}")
        
        except Exception as e:
            print(f"[WARNING] Failed to extract XDATA: {e}")
        
        # Default height dacă nu e specificat (2.8m pentru pereți tipici)
        if 'height' not in properties:
            properties['height'] = 2.8
        
        # Default solid flag dacă nu e specificat
        if 'solid' not in properties:
            properties['solid'] = 1
        
        return properties
    
    def _create_ifc_geometry(self, entity, ifc_element, global_z: float, height: float = 0.1):
        """Creează geometria IFC pentru entitate cu height din XDATA"""
        try:
            entity_type = entity.dxftype()
            
            # Obține contextul geometric
            context = self.model.by_type("IfcGeometricRepresentationContext")[0]
            
            if entity_type == "LWPOLYLINE" and hasattr(entity, 'get_points'):
                # Extrage punctele polyliniei
                points = list(entity.get_points())
                if len(points) >= 2:
                    self._create_polyline_geometry(ifc_element, points, global_z, height, context)
            
            elif entity_type == "LINE":
                if hasattr(entity, 'dxf') and hasattr(entity.dxf, 'start') and hasattr(entity.dxf, 'end'):
                    points = [(entity.dxf.start.x, entity.dxf.start.y), (entity.dxf.end.x, entity.dxf.end.y)]
                    self._create_polyline_geometry(ifc_element, points, global_z, height, context)
            
            elif entity_type == "CIRCLE":
                if hasattr(entity.dxf, 'center') and hasattr(entity.dxf, 'radius'):
                    self._create_circle_geometry(ifc_element, entity.dxf.center, entity.dxf.radius, global_z, height, context)
            
            elif entity_type == "ARC":
                if hasattr(entity.dxf, 'center') and hasattr(entity.dxf, 'radius'):
                    self._create_arc_geometry(ifc_element, entity, global_z, height, context)
            
            # Pentru alte tipuri, creează o bounding box simplă
            elif entity_type in ["3DFACE", "3DSOLID", "MESH"]:
                try:
                    if hasattr(entity, 'bounding_box'):
                        bbox = entity.bounding_box
                        self._create_bbox_geometry(ifc_element, bbox, global_z, height, context)
                except:
                    pass
            
        except Exception as e:
            print(f"[WARNING] Failed to create geometry for {entity.dxftype()}: {e}")
    
    def _create_polyline_geometry(self, ifc_element, points, global_z: float, height: float, context):
        """Creează geometrie IFC pentru polyline/line - ca extrudare 3D vizibilă cu height din XDATA"""
        try:
            # Convertește punctele 2D în 3D cu Z global
            ifc_points_2d = []
            for pt in points:
                x = float(pt[0] * self.length_conversion if isinstance(pt, tuple) else pt.x * self.length_conversion)
                y = float(pt[1] * self.length_conversion if isinstance(pt, tuple) else pt.y * self.length_conversion)
                # Pentru profil, folosește coordonate 2D
                ifc_point = self.model.create_entity("IfcCartesianPoint", Coordinates=(x, y))
                ifc_points_2d.append(ifc_point)
            
            # Verifică dacă polyline-ul este închis (primul punct = ultimul punct)
            if len(ifc_points_2d) > 2:
                first_coords = ifc_points_2d[0].Coordinates
                last_coords = ifc_points_2d[-1].Coordinates
                is_closed = (abs(first_coords[0] - last_coords[0]) < 0.001 and 
                           abs(first_coords[1] - last_coords[1]) < 0.001)
                
                # Dacă nu e închis, adaugă primul punct la final
                if not is_closed:
                    x_first = float(ifc_points_2d[0].Coordinates[0])
                    y_first = float(ifc_points_2d[0].Coordinates[1])
                    closing_point = self.model.create_entity("IfcCartesianPoint", Coordinates=(x_first, y_first))
                    ifc_points_2d.append(closing_point)
            
            # Creează polyline ca profil 2D
            polyline = self.model.create_entity("IfcPolyline", Points=ifc_points_2d)
            
            # Creează un profil arbitrar cu polyline-ul
            profile = self.model.create_entity("IfcArbitraryClosedProfileDef",
                ProfileType="AREA",
                OuterCurve=polyline
            )
            
            # Creează poziția pentru extrudare
            z = float(global_z * self.length_conversion)
            placement_point = self.model.create_entity("IfcCartesianPoint", Coordinates=(0., 0., z))
            axis = self.model.create_entity("IfcDirection", DirectionRatios=(0., 0., 1.))
            ref_direction = self.model.create_entity("IfcDirection", DirectionRatios=(1., 0., 0.))
            placement = self.model.create_entity("IfcAxis2Placement3D",
                Location=placement_point,
                Axis=axis,
                RefDirection=ref_direction
            )
            
            # Creează extrudarea cu înălțimea din XDATA (convertită la unități)
            extrusion_direction = self.model.create_entity("IfcDirection", DirectionRatios=(0., 0., 1.))
            extruded_solid = self.model.create_entity("IfcExtrudedAreaSolid",
                SweptArea=profile,
                Position=placement,
                ExtrudedDirection=extrusion_direction,
                Depth=float(height * self.length_conversion)  # Folosește height din XDATA!
            )
            
            # Creează reprezentarea geometrică ca solid 3D
            shape_representation = self.model.create_entity("IfcShapeRepresentation",
                ContextOfItems=context,
                RepresentationIdentifier="Body",
                RepresentationType="SweptSolid",
                Items=[extruded_solid]
            )
            
            # Creează product definition shape
            product_shape = self.model.create_entity("IfcProductDefinitionShape",
                Representations=[shape_representation]
            )
            ifc_element.Representation = product_shape
            
        except Exception as e:
            print(f"[WARNING] Failed to create polyline geometry: {e}")
    
    def _create_circle_geometry(self, ifc_element, center, radius, global_z: float, context):
        """Creează geometrie IFC pentru cerc"""
        try:
            # Convertește centrul și raza
            x = center.x * self.length_conversion
            y = center.y * self.length_conversion
            z = global_z * self.length_conversion
            r = radius * self.length_conversion
            
            # Creează cerc ca extrudare
            center_point = self.model.createIfcCartesianPoint([x, y, z])
            circle = self.model.createIfcCircle(
                self.model.createIfcAxis2Placement3D(center_point), 
                r
            )
            
            # Creează reprezentarea
            shape_representation = self.model.createIfcShapeRepresentation(
                context, "FootPrint", "Curve2D", [circle]
            )
            
            product_shape = self.model.createIfcProductDefinitionShape(None, None, [shape_representation])
            ifc_element.Representation = product_shape
            
        except Exception as e:
            print(f"[WARNING] Failed to create circle geometry: {e}")
    
    def _create_arc_geometry(self, ifc_element, entity, global_z: float, context):
        """Creează geometrie IFC pentru arc"""
        try:
            # Similar cu cercul, dar trimmed
            x = entity.dxf.center.x * self.length_conversion
            y = entity.dxf.center.y * self.length_conversion
            z = global_z * self.length_conversion
            r = entity.dxf.radius * self.length_conversion
            
            # Aproximează arcul cu polyline pentru simplitate
            start_angle = math.radians(entity.dxf.start_angle) if hasattr(entity.dxf, 'start_angle') else 0
            end_angle = math.radians(entity.dxf.end_angle) if hasattr(entity.dxf, 'end_angle') else math.pi * 2
            
            # Generează puncte pe arc
            num_segments = 16
            points = []
            for i in range(num_segments + 1):
                t = i / num_segments
                angle = start_angle + (end_angle - start_angle) * t
                px = x + r * math.cos(angle)
                py = y + r * math.sin(angle)
                points.append(self.model.createIfcCartesianPoint([px, py, z]))
            
            polyline = self.model.createIfcPolyline(points)
            shape_representation = self.model.createIfcShapeRepresentation(
                context, "Axis", "Curve2D", [polyline]
            )
            
            product_shape = self.model.createIfcProductDefinitionShape(None, None, [shape_representation])
            ifc_element.Representation = product_shape
            
        except Exception as e:
            print(f"[WARNING] Failed to create arc geometry: {e}")
    
    def _create_bbox_geometry(self, ifc_element, bbox, global_z: float, context):
        """Creează geometrie IFC pentru bounding box"""
        try:
            # Creează un bounding box simplu
            min_pt = bbox.extmin
            max_pt = bbox.extmax
            
            # Convertește la IFC
            x1 = min_pt.x * self.length_conversion
            y1 = min_pt.y * self.length_conversion
            x2 = max_pt.x * self.length_conversion
            y2 = max_pt.y * self.length_conversion
            z = global_z * self.length_conversion
            
            # Creează poligon dreptunghi
            points = [
                self.model.createIfcCartesianPoint([x1, y1, z]),
                self.model.createIfcCartesianPoint([x2, y1, z]),
                self.model.createIfcCartesianPoint([x2, y2, z]),
                self.model.createIfcCartesianPoint([x1, y2, z]),
                self.model.createIfcCartesianPoint([x1, y1, z]),
            ]
            
            polyline = self.model.createIfcPolyline(points)
            shape_representation = self.model.createIfcShapeRepresentation(
                context, "FootPrint", "Curve2D", [polyline]
            )
            
            product_shape = self.model.createIfcProductDefinitionShape(None, None, [shape_representation])
            ifc_element.Representation = product_shape
            
        except Exception as e:
            print(f"[WARNING] Failed to create bbox geometry: {e}")
    
    def _calculate_polygon_area(self, vertices) -> float:
        """Calculează aria unui poligon din lista de vertices"""
        if len(vertices) < 3:
            return 0.0
        
        area = 0.0
        n = len(vertices)
        for i in range(n):
            j = (i + 1) % n
            area += vertices[i][0] * vertices[j][1]
            area -= vertices[j][0] * vertices[i][1]
        return abs(area) / 2.0
    
    def _add_properties_from_xdata(self, ifc_element, properties: Dict[str, Any], layer: str):
        """Adaugă proprietăți din XDATA la elementul IFC"""
        try:
            if not properties and not layer:
                return
            
            # Creează Pset cu proprietăți
            property_values = []
            
            # Adaugă layer-ul
            if layer:
                prop_value = self.model.create_entity("IfcPropertySingleValue")
                prop_value.Name = "Layer"
                prop_value.NominalValue = self.model.create_entity("IfcLabel", layer)
                property_values.append(prop_value)
            
            # Adaugă proprietățile din XDATA
            for key, value in properties.items():
                prop_value = self.model.create_entity("IfcPropertySingleValue")
                prop_value.Name = key
                
                if isinstance(value, (int, float)):
                    if self.unit_system == "imperial" and "area" in key.lower():
                        value = value * self.area_conversion
                    elif self.unit_system == "imperial" and any(dim in key.lower() for dim in ["length", "width", "height"]):
                        value = value * self.length_conversion
                    prop_value.NominalValue = self.model.create_entity("IfcReal", value)
                else:
                    prop_value.NominalValue = self.model.create_entity("IfcText", str(value))
                
                property_values.append(prop_value)
            
            # Adaugă aria calculată dacă există
            if hasattr(ifc_element, '_calculated_area'):
                prop_value = self.model.create_entity("IfcPropertySingleValue")
                prop_value.Name = "CalculatedArea"
                prop_value.NominalValue = self.model.create_entity("IfcAreaMeasure", ifc_element._calculated_area)
                property_values.append(prop_value)
            
            # Creează Property Set doar dacă avem proprietăți
            if property_values:
                pset = self.model.create_entity("IfcPropertySet")
                pset.GlobalId = ifcopenshell.guid.new()
                pset.Name = f"DXF_Properties_{layer}" if layer else "DXF_Properties"
                pset.HasProperties = property_values
                
                # Asociază cu elementul
                rel = self.model.create_entity("IfcRelDefinesByProperties")
                rel.GlobalId = ifcopenshell.guid.new()
                rel.RelatedObjects = [ifc_element]
                rel.RelatingPropertyDefinition = pset
                
        except Exception as e:
            print(f"[WARNING] Failed to add properties to {ifc_element}: {e}")
    
    def export_ifc(self, output_path: str) -> bool:
        """Exportă modelul IFC"""
        try:
            print(f"[IFC] Exporting to: {output_path}")
            self.model.write(output_path)
            
            print(f"[SUCCESS] IFC export completed:")
            print(f"  - File: {output_path}")
            print(f"  - Storeys: {len(self.storeys)}")
            print(f"  - Elements: {self.elements_created}")
            print(f"  - Unit System: {self.unit_system}")
            
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to export IFC: {e}")
            return False


def main():
    """Funcția principală pentru export IFC din DXF cu XDATA"""
    if len(sys.argv) < 4:
        print("Usage: python direct_ifc_from_dxf.py <output.ifc> <unit_system> <file1.dxf> [file2.dxf] ...")
        print("Unit systems: 'metric' or 'imperial'")
        sys.exit(1)
    
    if not IFC_AVAILABLE:
        print("[ERROR] IfcOpenShell not available. Please install: pip install ifcopenshell")
        sys.exit(1)
    
    output_ifc = sys.argv[1]
    unit_system = sys.argv[2]
    dxf_files = sys.argv[3:]
    
    if unit_system not in ["metric", "imperial"]:
        print("[ERROR] Unit system must be 'metric' or 'imperial'")
        sys.exit(1)
    
    print(f"[DEBUG] Starting direct IFC export ({unit_system}) to: {output_ifc}")
    print(f"[DEBUG] Processing {len(dxf_files)} DXF files")
    
    try:
        # Creează exportatorul
        exporter = DirectIfcExporter(project_name="Multi-Story Building", unit_system=unit_system)
        
        # Creează modelul IFC
        exporter.create_ifc_model()
        
        # Procesează fiecare DXF
        for dxf_file in dxf_files:
            if os.path.exists(dxf_file):
                exporter.process_dxf_file(dxf_file)
            else:
                print(f"[WARNING] DXF file not found: {dxf_file}")
        
        # Exportă IFC-ul
        if exporter.export_ifc(output_ifc):
            sys.exit(0)
        else:
            sys.exit(1)
            
    except Exception as e:
        print(f"[ERROR] Export failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()