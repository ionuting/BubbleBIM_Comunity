"""
IFC Direct Exporter - Construiește geometrie IFC nativă folosind IfcOpenShell
fără să treacă prin GLB. Fiecare fișier DXF devine un IfcStorey.
"""

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.geom
import numpy as np
from shapely.geometry import Polygon
import uuid
import os
from datetime import datetime

class IFCDirectExporter:
    def __init__(self, project_name="Multi-Level Building Project"):
        """
        Inițializează exportatorul IFC direct.
        
        Args:
            project_name: Numele proiectului IFC
        """
        self.project_name = project_name
        self.model = None
        self.site = None
        self.building = None
        self.storeys = {}  # Mapare filename -> IfcBuildingStorey
        self.elements = []  # Lista tuturor elementelor create
        
        # Cache pentru optimizare
        self.material_cache = {}
        self.profile_cache = {}
        
    def create_ifc_model(self):
        """Creează structura de bază a modelului IFC"""
        print(f"[DEBUG] Creating IFC model: {self.project_name}")
        
        # Creează modelul IFC
        self.model = ifcopenshell.file(schema="IFC4")
        
        # Creează entitățile de bază
        self._create_project_structure()
        
        return self.model
    
    def _create_project_structure(self):
        """Creează structura ierarhică de bază: Project -> Site -> Building"""
        
        # Creează aplicația care generează fișierul
        application = self.model.create_entity("IfcApplication",
            ApplicationDeveloper=self.model.create_entity("IfcOrganization", Name="Viewer2D"),
            Version="1.0",
            ApplicationFullName="Viewer2D DXF to IFC Converter",
            ApplicationIdentifier="viewer2d_converter"
        )
        
        # Creează persoana/organizația responsabilă
        person = self.model.create_entity("IfcPerson",
            FamilyName="System",
            GivenName="Converter"
        )
        
        organization = self.model.create_entity("IfcOrganization",
            Name="Viewer2D System"
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
        
        # Creează proiectul
        self.project = self.model.create_entity("IfcProject",
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=self.owner_history,
            Name=self.project_name,
            Description="Multi-level building from DXF files"
        )
        
        # Creează contextul geometric
        self.geometric_context = self.model.create_entity("IfcGeometricRepresentationContext",
            ContextType="Model",
            CoordinateSpaceDimension=3,
            Precision=1e-05,
            WorldCoordinateSystem=self.model.create_entity("IfcAxis2Placement3D",
                Location=self.model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))
            )
        )
        
        # Asociază contextul cu proiectul
        self.model.create_entity("IfcRelDeclares",
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=self.owner_history,
            RelatingContext=self.project,
            RelatedDefinitions=[self.geometric_context]
        )
        
        # Creează site-ul
        self.site = self.model.create_entity("IfcSite",
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=self.owner_history,
            Name="Building Site",
            Description="Site containing the building"
        )
        
        # Asociază site-ul cu proiectul
        self.model.create_entity("IfcRelAggregates",
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=self.owner_history,
            RelatingObject=self.project,
            RelatedObjects=[self.site]
        )
        
        # Creează clădirea
        self.building = self.model.create_entity("IfcBuilding",
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=self.owner_history,
            Name="Main Building",
            Description="Building from DXF conversion"
        )
        
        # Asociază clădirea cu site-ul
        self.model.create_entity("IfcRelAggregates",
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=self.owner_history,
            RelatingObject=self.site,
            RelatedObjects=[self.building]
        )
        
        print(f"[DEBUG] IFC project structure created")
    
    def add_storey_from_dxf(self, dxf_filename, global_z, elements_data):
        """
        Adaugă un nivel (IfcBuildingStorey) din datele DXF.
        
        Args:
            dxf_filename: Numele fișierului DXF (devine numele nivelului)
            global_z: Cota Z a nivelului 
            elements_data: Lista cu datele elementelor (din mapping)
        
        Returns:
            IfcBuildingStorey: Nivelul creat
        """
        
        # Extrage numele nivelului din filename
        storey_name = os.path.splitext(os.path.basename(dxf_filename))[0]
        
        print(f"[DEBUG] Creating storey: {storey_name} at Z={global_z}")
        
        # Creează nivelul
        storey = self.model.create_entity("IfcBuildingStorey",
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=self.owner_history,
            Name=storey_name,
            Description=f"Building storey from {dxf_filename}",
            Elevation=global_z
        )
        
        # Poziționează nivelul în Z
        storey_placement = self.model.create_entity("IfcLocalPlacement",
            RelativePlacement=self.model.create_entity("IfcAxis2Placement3D",
                Location=self.model.create_entity("IfcCartesianPoint", 
                    Coordinates=(0.0, 0.0, global_z)
                )
            )
        )
        
        storey.ObjectPlacement = storey_placement
        
        # Asociază nivelul cu clădirea
        self.model.create_entity("IfcRelAggregates",
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=self.owner_history,
            RelatingObject=self.building,
            RelatedObjects=[storey]
        )
        
        # Stochează nivelul pentru referință
        self.storeys[dxf_filename] = storey
        
        # Adaugă elementele la acest nivel
        storey_elements = []
        for element_data in elements_data:
            ifc_element = self._create_ifc_element_from_data(element_data, storey_placement)
            if ifc_element:
                storey_elements.append(ifc_element)
                self.elements.append(ifc_element)
        
        # Asociază elementele cu nivelul
        if storey_elements:
            self.model.create_entity("IfcRelContainedInSpatialStructure",
                GlobalId=ifcopenshell.guid.new(),
                OwnerHistory=self.owner_history,
                RelatingStructure=storey,
                RelatedElements=storey_elements
            )
        
        print(f"[DEBUG] Storey {storey_name} created with {len(storey_elements)} elements")
        
        return storey
    
    def _create_ifc_element_from_data(self, element_data, parent_placement=None):
        """
        Creează un element IFC din datele de mapping.
        
        Args:
            element_data: Dict cu datele elementului (din mapping JSON)
            parent_placement: Placement-ul părintelui (nivelul)
        
        Returns:
            IfcElement: Elementul IFC creat
        """
        
        try:
            # Extrage informațiile de bază
            mesh_name = element_data.get("mesh_name", "Unknown")
            ifc_type = element_data.get("ifc_type", "IfcBuildingElement")
            uuid_str = element_data.get("uuid", str(uuid.uuid4()))
            
            # Determină tipul IFC și creează elementul corespunzător
            ifc_element = self._create_typed_ifc_element(ifc_type, mesh_name, uuid_str)
            
            if not ifc_element:
                return None
            
            # Creează geometria
            geometry = self._create_geometry_from_element_data(element_data)
            if geometry:
                ifc_element.Representation = geometry
            
            # Creează placement-ul elementului  
            element_placement = self._create_element_placement(element_data, parent_placement)
            if element_placement:
                ifc_element.ObjectPlacement = element_placement
            
            # Adaugă proprietăți custom
            self._add_element_properties(ifc_element, element_data)
            
            return ifc_element
            
        except Exception as e:
            print(f"[ERROR] Failed to create IFC element from {element_data.get('mesh_name', 'unknown')}: {e}")
            return None
    
    def _create_typed_ifc_element(self, ifc_type, name, uuid_str):
        """Creează elementul IFC cu tipul corespunzător"""
        
        # Mapează tipurile IFC la constructorii corespunzători
        ifc_constructors = {
            "IfcWall": "IfcWall",
            "IfcColumn": "IfcColumn", 
            "IfcBeam": "IfcBeam",
            "IfcSlab": "IfcSlab",
            "IfcRoof": "IfcRoof",
            "IfcDoor": "IfcDoor",
            "IfcWindow": "IfcWindow",
            "IfcSpace": "IfcSpace",
            "IfcCovering": "IfcCovering",
            "IfcBuildingElementProxy": "IfcBuildingElementProxy"
        }
        
        constructor_name = ifc_constructors.get(ifc_type, "IfcBuildingElementProxy")
        
        try:
            ifc_element = self.model.create_entity(constructor_name,
                GlobalId=uuid_str,
                OwnerHistory=self.owner_history,
                Name=name,
                Description=f"Element from DXF - {ifc_type}"
            )
            
            print(f"[DEBUG] Created {constructor_name}: {name}")
            return ifc_element
            
        except Exception as e:
            print(f"[ERROR] Failed to create {constructor_name}: {e}")
            return None
    
    def _create_geometry_from_element_data(self, element_data):
        """
        Creează geometria IFC din datele elementului.
        
        Args:
            element_data: Dict cu datele elementului
            
        Returns:
            IfcProductDefinitionShape: Reprezentarea geometrică
        """
        
        try:
            # Extrage datele geometrice
            vertices_2d = element_data.get("vertices", [])
            height = element_data.get("height", 1.0)
            area = element_data.get("area", 0.0)
            volume = element_data.get("volume", 0.0)
            
            if not vertices_2d or len(vertices_2d) < 3:
                print(f"[WARNING] Insufficient vertices for {element_data.get('mesh_name', 'unknown')}")
                return None
            
            # Convertește vertex-urile în puncte IFC
            points_2d = []
            for vertex in vertices_2d:
                if len(vertex) >= 2:
                    points_2d.append(self.model.create_entity("IfcCartesianPoint", 
                        Coordinates=(float(vertex[0]), float(vertex[1]))
                    ))
            
            # Creează poliliniile pentru contur
            polyline = self.model.create_entity("IfcPolyline", Points=points_2d)
            
            # Închide poliliniile (adaugă primul punct la sfârșit dacă nu e deja închis)
            if len(points_2d) > 2 and (
                abs(vertices_2d[0][0] - vertices_2d[-1][0]) > 1e-6 or 
                abs(vertices_2d[0][1] - vertices_2d[-1][1]) > 1e-6
            ):
                polyline.Points = points_2d + [points_2d[0]]
            
            # Creează conturul 2D
            outer_bound = self.model.create_entity("IfcFaceBound",
                Bound=polyline,
                Orientation=True
            )
            
            # Creează fața 2D
            face = self.model.create_entity("IfcFace",
                Bounds=[outer_bound]
            )
            
            # Creează suprafața închisă
            closed_shell = self.model.create_entity("IfcClosedShell",
                CfsFaces=[face]
            )
            
            # Extrudează pe înălțimea specificată
            if height > 0:
                # Creează direcția de extrudare (Z)
                direction = self.model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
                
                # Creează solidul extrudat
                extruded_solid = self.model.create_entity("IfcExtrudedAreaSolid",
                    SweptArea=self.model.create_entity("IfcArbitraryClosedProfileDef",
                        ProfileType="AREA",
                        OuterCurve=polyline
                    ),
                    Position=self.model.create_entity("IfcAxis2Placement3D",
                        Location=self.model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))
                    ),
                    ExtrudedDirection=direction,
                    Depth=height
                )
                
                # Creează reprezentarea geometrică
                shape_representation = self.model.create_entity("IfcShapeRepresentation",
                    ContextOfItems=self.geometric_context,
                    RepresentationIdentifier="Body",
                    RepresentationType="SweptSolid",
                    Items=[extruded_solid]
                )
            else:
                # Pentru elemente fără înălțime (de ex. contururi)
                shape_representation = self.model.create_entity("IfcShapeRepresentation",
                    ContextOfItems=self.geometric_context,
                    RepresentationIdentifier="Curve2D", 
                    RepresentationType="Curve2D",
                    Items=[polyline]
                )
            
            # Creează definirea produsului
            product_shape = self.model.create_entity("IfcProductDefinitionShape",
                Representations=[shape_representation]
            )
            
            return product_shape
            
        except Exception as e:
            print(f"[ERROR] Failed to create geometry for {element_data.get('mesh_name', 'unknown')}: {e}")
            return None
    
    def _create_element_placement(self, element_data, parent_placement=None):
        """
        Creează placement-ul pentru element bazat pe datele sale.
        
        Args:
            element_data: Datele elementului
            parent_placement: Placement-ul părintelui
            
        Returns:
            IfcLocalPlacement: Placement-ul elementului
        """
        
        try:
            # Extrage poziția relativă din element_data
            z_relative = element_data.get("z_relative", 0.0)
            
            # Poziția insertion point (dacă există, pentru blocuri)
            insert_pos = element_data.get("insert_position", {})
            x_pos = insert_pos.get("x", 0.0)
            y_pos = insert_pos.get("y", 0.0)
            z_pos = z_relative  # Z relativ la nivelul părintelui
            
            # Creează placement-ul local
            placement = self.model.create_entity("IfcLocalPlacement",
                PlacementRelTo=parent_placement,
                RelativePlacement=self.model.create_entity("IfcAxis2Placement3D",
                    Location=self.model.create_entity("IfcCartesianPoint", 
                        Coordinates=(float(x_pos), float(y_pos), float(z_pos))
                    )
                )
            )
            
            return placement
            
        except Exception as e:
            print(f"[ERROR] Failed to create placement: {e}")
            return None
    
    def _add_element_properties(self, ifc_element, element_data):
        """
        Adaugă proprietățile custom la elementul IFC.
        
        Args:
            ifc_element: Elementul IFC
            element_data: Datele cu proprietățile
        """
        
        try:
            # Creează set-ul de proprietăți
            property_values = []
            
            # Proprietăți geometrice
            if "area" in element_data:
                property_values.append(
                    self.model.create_entity("IfcPropertySingleValue",
                        Name="Area",
                        NominalValue=self.model.create_entity("IfcAreaMeasure", wrappedValue=element_data["area"]),
                        Unit=self.model.create_entity("IfcSIUnit", UnitType="AREAUNIT", Name="SQUARE_METRE")
                    )
                )
            
            if "volume" in element_data:
                property_values.append(
                    self.model.create_entity("IfcPropertySingleValue",
                        Name="Volume", 
                        NominalValue=self.model.create_entity("IfcVolumeMeasure", wrappedValue=element_data["volume"]),
                        Unit=self.model.create_entity("IfcSIUnit", UnitType="VOLUMEUNIT", Name="CUBIC_METRE")
                    )
                )
            
            if "height" in element_data:
                property_values.append(
                    self.model.create_entity("IfcPropertySingleValue",
                        Name="Height",
                        NominalValue=self.model.create_entity("IfcLengthMeasure", wrappedValue=element_data["height"]),
                        Unit=self.model.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE")
                    )
                )
            
            # Proprietăți DXF specifice
            if "layer" in element_data:
                property_values.append(
                    self.model.create_entity("IfcPropertySingleValue",
                        Name="DXF_Layer",
                        NominalValue=self.model.create_entity("IfcLabel", wrappedValue=str(element_data["layer"]))
                    )
                )
            
            if "dxf_handle" in element_data:
                property_values.append(
                    self.model.create_entity("IfcPropertySingleValue",
                        Name="DXF_Handle",
                        NominalValue=self.model.create_entity("IfcIdentifier", wrappedValue=element_data["dxf_handle"])
                    )
                )
            
            # Proprietăți Z system
            for prop_name in ["global_z", "z_relative", "z_final"]:
                if prop_name in element_data:
                    property_values.append(
                        self.model.create_entity("IfcPropertySingleValue",
                            Name=prop_name,
                            NominalValue=self.model.create_entity("IfcLengthMeasure", wrappedValue=element_data[prop_name]),
                            Unit=self.model.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE")
                        )
                    )
            
            if property_values:
                # Creează set-ul de proprietăți
                property_set = self.model.create_entity("IfcPropertySet",
                    GlobalId=ifcopenshell.guid.new(),
                    OwnerHistory=self.owner_history,
                    Name=f"Viewer2D_Properties_{ifc_element.Name}",
                    HasProperties=property_values
                )
                
                # Asociază set-ul cu elementul
                self.model.create_entity("IfcRelDefinesByProperties",
                    GlobalId=ifcopenshell.guid.new(),
                    OwnerHistory=self.owner_history,
                    RelatedObjects=[ifc_element],
                    RelatingPropertyDefinition=property_set
                )
                
        except Exception as e:
            print(f"[ERROR] Failed to add properties to {ifc_element.Name}: {e}")
    
    def export_ifc(self, output_path):
        """
        Exportă modelul IFC la calea specificată.
        
        Args:
            output_path: Calea de export
            
        Returns:
            bool: True dacă exportul a reușit
        """
        
        try:
            print(f"[DEBUG] Exporting IFC model to: {output_path}")
            
            # Validează modelul
            if not self.model:
                print("[ERROR] No IFC model to export")
                return False
            
            # Scrie fișierul IFC
            self.model.write(output_path)
            
            # Statistici
            total_elements = len(self.elements)
            total_storeys = len(self.storeys)
            
            print(f"[SUCCESS] IFC model exported successfully:")
            print(f"  - File: {output_path}")
            print(f"  - Storeys: {total_storeys}")
            print(f"  - Elements: {total_elements}")
            
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to export IFC: {e}")
            return False
    
    def get_summary(self):
        """Returnează un rezumat al modelului creat"""
        
        summary = {
            "project_name": self.project_name,
            "total_storeys": len(self.storeys),
            "total_elements": len(self.elements),
            "storeys": {}
        }
        
        # Adaugă detalii pentru fiecare nivel
        for dxf_file, storey in self.storeys.items():
            storey_elements = [e for e in self.elements 
                             if hasattr(e, 'ContainedInStructure') and 
                             any(rel.RelatingStructure == storey 
                                 for rel in self.model.by_type("IfcRelContainedInSpatialStructure")
                                 if e in rel.RelatedElements)]
            
            summary["storeys"][dxf_file] = {
                "name": storey.Name,
                "elevation": storey.Elevation if hasattr(storey, 'Elevation') else 0.0,
                "element_count": len(storey_elements)
            }
        
        return summary


def create_multi_level_ifc_from_dxf_data(dxf_data_list, output_path, project_name="Multi-Level Building"):
    """
    Creează un model IFC cu multiple nivele din mai multe seturi de date DXF.
    
    Args:
        dxf_data_list: Lista de dict-uri cu date DXF:
                      [{"filename": "level1.dxf", "global_z": 0.0, "elements": [...]}, ...]
        output_path: Calea de export pentru fișierul IFC
        project_name: Numele proiectului
        
    Returns:
        dict: Rezumatul exportului
    """
    
    try:
        # Creează exportatorul
        exporter = IFCDirectExporter(project_name)
        
        # Creează modelul IFC
        exporter.create_ifc_model()
        
        # Adaugă fiecare nivel DXF
        for dxf_data in dxf_data_list:
            filename = dxf_data["filename"]
            global_z = dxf_data["global_z"] 
            elements = dxf_data["elements"]
            
            exporter.add_storey_from_dxf(filename, global_z, elements)
        
        # Exportă modelul
        success = exporter.export_ifc(output_path)
        
        if success:
            return exporter.get_summary()
        else:
            return None
            
    except Exception as e:
        print(f"[ERROR] Multi-level IFC creation failed: {e}")
        return None


# Test function
def test_direct_ifc_export():
    """Test pentru exportul IFC direct"""
    
    # Date simulate pentru test
    test_data = [
        {
            "filename": "ground_floor_0.00.dxf",
            "global_z": 0.0,
            "elements": [
                {
                    "mesh_name": "Ground_Wall_1",
                    "ifc_type": "IfcWall",
                    "uuid": "test-uuid-1",
                    "vertices": [[0, 0], [5, 0], [5, 0.3], [0, 0.3]],
                    "height": 3.0,
                    "area": 1.5,
                    "volume": 4.5,
                    "layer": "wall",
                    "dxf_handle": "123",
                    "global_z": 0.0,
                    "z_relative": 0.0
                }
            ]
        },
        {
            "filename": "first_floor_3.00.dxf", 
            "global_z": 3.0,
            "elements": [
                {
                    "mesh_name": "First_Wall_1",
                    "ifc_type": "IfcWall",
                    "uuid": "test-uuid-2",
                    "vertices": [[0, 0], [5, 0], [5, 0.3], [0, 0.3]],
                    "height": 3.0,
                    "area": 1.5,
                    "volume": 4.5,
                    "layer": "wall",
                    "dxf_handle": "456", 
                    "global_z": 3.0,
                    "z_relative": 0.0
                }
            ]
        }
    ]
    
    # Testează exportul
    result = create_multi_level_ifc_from_dxf_data(
        test_data,
        "test_multi_level.ifc",
        "Test Multi-Level Building"
    )
    
    if result:
        print("Test successful!")
        print(f"Summary: {result}")
    else:
        print("Test failed!")


if __name__ == "__main__":
    test_direct_ifc_export()