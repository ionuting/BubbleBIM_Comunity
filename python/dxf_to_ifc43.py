import ezdxf
import ifcopenshell
import ifcopenshell.api
import uuid
import sys
import time
import numpy as np
from shapely.geometry import Polygon

# Map layer to IFC type (simplified)
LAYER_TO_IFC = {
    "Rooms": "IfcSpace",
    "column": "IfcColumn",
    "beam": "IfcBeam",
    "proxy": "IfcBuildingElementProxy",
    "void": "IfcOpeningElement",
    "default": "IfcBuildingElementProxy"
}

def parse_height_z(xdata):
    height, z = 1.0, 0.0
    if xdata and "QCAD" in xdata:
        for item in xdata["QCAD"]:
            if isinstance(item, list) and len(item) == 2:
                val = str(item[1])
                if val.startswith("height:"):
                    height = float(val.split(":")[1])
                elif val.startswith("z:"):
                    z = float(val.split(":")[1])
    return height, z

def create_profile(ifc, points):
    """Create an IfcArbitraryClosedProfileDef from points."""
    ifc_points = [ifc.createIfcCartesianPoint((p[0], p[1])) for p in points]
    polyline = ifc.createIfcPolyline(ifc_points)
    profile = ifc.createIfcArbitraryClosedProfileDef("AREA", None, polyline)
    return profile

def create_extruded_solid(ifc, profile, height, z_offset):
    """Create an IfcExtrudedAreaSolid."""
    direction = ifc.createIfcDirection((0.0, 0.0, 1.0))
    position = ifc.createIfcAxis2Placement3D(
        ifc.createIfcCartesianPoint((0.0, 0.0, z_offset)),
        ifc.createIfcDirection((0.0, 0.0, 1.0)),
        ifc.createIfcDirection((1.0, 0.0, 0.0))
    )
    solid = ifc.createIfcExtrudedAreaSolid(profile, position, direction, height)
    return solid

def dxf_to_ifc(dxf_path, ifc_path):
    print(f"[DEBUG] Start DXF to IFC: {dxf_path} -> {ifc_path}")
    start_time = time.time()
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    
    # Create IFC file
    ifc = ifcopenshell.api.run('project.create_file', version='IFC4X3')
    project = ifcopenshell.api.run('root.create_entity', ifc, ifc_class='IfcProject', name='DXF Project')
    
    # Create and assign units manually
    length_unit = ifc.createIfcSIUnit(None, 'LENGTHUNIT', None, 'METRE')
    area_unit = ifc.createIfcSIUnit(None, 'AREAUNIT', None, 'SQUARE_METRE')
    volume_unit = ifc.createIfcSIUnit(None, 'VOLUMEUNIT', None, 'CUBIC_METRE')
    angle_unit = ifc.createIfcSIUnit(None, 'PLANEANGLEUNIT', None, 'RADIAN')
    
    unit_assignment = ifc.createIfcUnitAssignment([length_unit, area_unit, volume_unit, angle_unit])
    project.UnitsInContext = unit_assignment
    
    # Create context
    context = ifcopenshell.api.run('context.add_context', ifc, context_type='Model')
    body_context = ifcopenshell.api.run('context.add_context', ifc, 
                                         context_type='Model', 
                                         context_identifier='Body', 
                                         target_view='MODEL_VIEW', 
                                         parent=context)
    
    # Create spatial structure
    site = ifcopenshell.api.run('root.create_entity', ifc, ifc_class='IfcSite', name='Site')
    building = ifcopenshell.api.run('root.create_entity', ifc, ifc_class='IfcBuilding', name='Building')
    storey = ifcopenshell.api.run('root.create_entity', ifc, ifc_class='IfcBuildingStorey', name='Storey')
    
    ifcopenshell.api.run('aggregate.assign_object', ifc, products=[site], relating_object=project)
    ifcopenshell.api.run('aggregate.assign_object', ifc, products=[building], relating_object=site)
    ifcopenshell.api.run('aggregate.assign_object', ifc, products=[storey], relating_object=building)

    element_count = 0
    # --- NOU: logica robustă cu solids/voids și asociere voids.assign_void ---
    element_count = 0
    solids = []
    voids = []
    for idx, e in enumerate(msp):
        ent_type = e.dxftype()
        handle = getattr(e.dxf, 'handle', None)
        layer = getattr(e.dxf, 'layer', 'default')
        # Parse XDATA
        xdata = {}
        if e.has_xdata:
            appids = []
            if hasattr(e, "get_xdata_appids"):
                appids = e.get_xdata_appids()
            if "QCAD" not in appids:
                appids.append("QCAD")
            for appid in appids:
                try:
                    data = e.get_xdata(appid)
                    if data:
                        xdata[appid] = [(code, value) for code, value in data]
                except Exception as ex:
                    print(f"[DEBUG] XDATA error for appid {appid}: {ex}")
        height, z = parse_height_z(xdata.get("QCAD", []))
        ifc_type = LAYER_TO_IFC.get(layer, LAYER_TO_IFC["default"])
        points = None
        # LWPOLYLINE
        if ent_type == "LWPOLYLINE" and hasattr(e, "get_points"):
            pts = [(float(p[0]), float(p[1])) for p in e.get_points()]
            closed = getattr(e, "closed", False)
            if closed and len(pts) >= 3:
                poly = Polygon(pts)
                if poly.is_valid and poly.is_simple and poly.area > 0:
                    points = pts
        # POLYLINE
        elif ent_type == "POLYLINE" and hasattr(e, "vertices"):
            pts = [(float(v.dxf.location.x), float(v.dxf.location.y)) for v in e.vertices()]
            closed = getattr(e, "is_closed", False)
            if closed and len(pts) >= 3:
                poly = Polygon(pts)
                if poly.is_valid and poly.is_simple and poly.area > 0:
                    points = pts
        # CIRCLE
        elif ent_type == "CIRCLE" and hasattr(e, "dxf"):
            center = (e.dxf.center.x, e.dxf.center.y)
            radius = e.dxf.radius
            segments = 32
            pts = [(
                center[0] + np.cos(2 * np.pi * i / segments) * radius,
                center[1] + np.sin(2 * np.pi * i / segments) * radius
            ) for i in range(segments)]
            poly = Polygon(pts)
            if poly.is_valid and poly.is_simple and poly.area > 0:
                points = pts
        # Stochează separat solidele și void-urile
        if points is not None:
            if layer == "void":
                voids.append({"points": points, "height": height, "z": z, "handle": handle, "idx": idx})
            else:
                solids.append({"points": points, "height": height, "z": z, "handle": handle, "idx": idx, "ifc_type": ifc_type})
    # Creează solidele
    solid_products = []
    for solid in solids:
        try:
            profile = create_profile(ifc, solid["points"])
            solid_geom = create_extruded_solid(ifc, profile, solid["height"], solid["z"])
            shape_representation = ifc.createIfcShapeRepresentation(
                body_context, 'Body', 'SweptSolid', [solid_geom]
            )
            product_shape = ifc.createIfcProductDefinitionShape(None, None, [shape_representation])
            guid = ifcopenshell.guid.compress(uuid.uuid4().hex)
            product = ifcopenshell.api.run('root.create_entity', ifc, 
                                          ifc_class=solid["ifc_type"], 
                                          name=f"{solid['ifc_type']}_{solid['handle'] or solid['idx']}", 
                                          guid=guid)
            product.Representation = product_shape
            ifcopenshell.api.run('spatial.assign_container', ifc, 
                                products=[product], 
                                relating_structure=storey)
            solid_products.append(product)
            element_count += 1
        except Exception as ex:
            print(f"[DEBUG] Error creating solid {solid['idx']}: {ex}")
            continue
    # Creează void-urile ca IfcOpeningElement și le asociază la primul solid intersectat (simplu)
    for void in voids:
        try:
            profile = create_profile(ifc, void["points"])
            void_geom = create_extruded_solid(ifc, profile, void["height"], void["z"])
            shape_representation = ifc.createIfcShapeRepresentation(
                body_context, 'Body', 'SweptSolid', [void_geom]
            )
            product_shape = ifc.createIfcProductDefinitionShape(None, None, [shape_representation])
            guid = ifcopenshell.guid.compress(uuid.uuid4().hex)
            opening = ifcopenshell.api.run('root.create_entity', ifc, 
                                           ifc_class='IfcOpeningElement', 
                                           name=f"Opening_{void['handle'] or void['idx']}", 
                                           guid=guid)
            opening.Representation = product_shape
            ifcopenshell.api.run('spatial.assign_container', ifc, 
                                products=[opening], 
                                relating_structure=storey)
            # Asociază la primul solid (simplu, pentru demo)
            if solid_products:
                ifcopenshell.api.run('voids.assign_void', ifc, opening=opening, element=solid_products[0])
        except Exception as ex:
            print(f"[DEBUG] Error creating void {void['idx']}: {ex}")
            continue
    
    ifc.write(ifc_path)
    elapsed = time.time() - start_time
    print(f"[DEBUG] Finished DXF to IFC in {elapsed:.2f} seconds.")
    print(f"[DEBUG] Created {element_count} IFC elements.")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python dxf_to_ifc43.py input.dxf output.ifc")
        sys.exit(1)
    dxf_path = sys.argv[1]
    ifc_path = sys.argv[2]
    dxf_to_ifc(dxf_path, ifc_path)
    print(f"Converted {dxf_path} to {ifc_path}")