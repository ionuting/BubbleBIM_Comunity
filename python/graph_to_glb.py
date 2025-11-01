# Required libraries:
# - ifcopenshell: For creating and manipulating IFC files. Install via: pip install ifcopenshell
# - shapely: For geometric operations like polygon offsetting. Install via: pip install shapely
# - xml.etree.ElementTree: Built-in Python library for parsing XML, no installation needed.
# Optional: numpy for numerical operations, but not strictly necessary here.

from datetime import time
import math
import re
import html
import ifcopenshell
from ifcopenshell import geom
import xml.etree.ElementTree as ET
from shapely.geometry import Polygon, LinearRing
from shapely.affinity import translate
import time
import numpy as np
import trimesh
import os
import json
from pathlib import Path

import re

def parse_xml_and_generate_ifc(xml_file_path=r"C:/Users/ionut.ciuntuc/Downloads/Diagram.xml", output_ifc_path="output_model.ifc"):
    # Step 1: Parse the XML file
    tree = ET.parse(xml_file_path)
    root = tree.getroot()

    # Find the diagram and graph model
    diagram = root.find('diagram')
    mxGraphModel = diagram.find('mxGraphModel')
    graph_root = mxGraphModel.find('root')

    # Step 2: Extract Axes (X and Y coordinates)
    axes_cell = None
    for cell in graph_root.findall('mxCell'):
        if cell.get('value') == 'Axes' and cell.get('style', '').startswith('swimlane'):
            axes_cell = cell
            break

    if not axes_cell:
        raise ValueError("Axes swimlane not found in XML.")

    # Extract X and Y from cells that contain coordinate data
    axes_text = ''
    for cell in graph_root.findall('mxCell'):
        cell_value = cell.get('value', '')
        if 'x=[' in cell_value and 'y=[' in cell_value:
            axes_text = cell_value
            break
    
    if not axes_text:
        raise ValueError("Could not find cell with X and Y coordinates.")
    
    # Clean HTML tags from axes_text
    axes_text = re.sub(r'<[^>]+>', '', axes_text)  # Remove HTML tags
    axes_text = axes_text.replace('&nbsp;', ' ').strip()  # Remove non-breaking spaces
    
    print(f"DEBUG: axes_text = '{axes_text}'")  # Debug
    
    # Parse X and Y lists (assuming format like x=[0.00, 4.00, ...] y=[0.00, 4.50, ...])
    x_start = axes_text.find('x=[') + 3
    x_end = axes_text.find(']', x_start)
    y_start = axes_text.find('y=[', x_end) + 3
    y_end = axes_text.find(']', y_start)
    
    x_coords = [float(v.strip()) for v in axes_text[x_start:x_end].split(',') if v.strip()]
    y_coords = [float(v.strip()) for v in axes_text[y_start:y_end].split(',') if v.strip()]

    if not x_coords or not y_coords:
        raise ValueError("Could not parse X or Y coordinates from Axes.")

    # Step 3: Generate matrix of points (combinations of x_i, y_j)
    points = []
    for j, y in enumerate(y_coords):
        for i, x in enumerate(x_coords):
            points.append((x, y, 0.0))  # Z=0 for base

    # Assuming nodes 0 to 15 are indexed as: point_index = i * len(x_coords) + j where i is y index, j is x index

    # Step 4: Extract Levels (storey elevations)
    levels = [0.00, 2.80, 5.60]  # Hardcoded from description, or parse similarly if dynamic

    # Step 5: Extract Nodes from the grid
    # Nodes are numbered 0,1,2,... as combinations of x_coords with y_coords
    # node_index = i * len(x_coords) + j where i is y index, j is x index
    nodes = {}
    for j, y in enumerate(y_coords):
        for i, x in enumerate(x_coords):
            node_index = j * len(x_coords) + i
            nodes[node_index] = (x, y, 0.0)  # Z=0 for base level
    
    print(f"DEBUG: Grid nodes: {nodes}")

    # Step 6: Extract Rooms from table
    rooms = {}
    print("DEBUG: Looking for tables in XML...")
    tables = []
    for cell in graph_root.findall('mxCell'):
        cell_value = cell.get('value', '')
        cell_style = cell.get('style', '')
        if 'shape=table' in cell_style:
            tables.append((cell_value, cell.get('id')))
            print(f"DEBUG: Found table: '{cell_value}' (id: {cell.get('id')})")
    
    # Find rooms table by name (contains 'rooms')
    rooms_table = None
    for cell in graph_root.findall('mxCell'):
        cell_value = cell.get('value', '').lower()
        if 'rooms' in cell_value and 'shape=table' in cell.get('style', ''):
            rooms_table = cell
            print(f"DEBUG: Found rooms table: '{cell.get('value')}'")
            break
    
    print(f"DEBUG: rooms_table found: {rooms_table is not None}")
    
    # Extract rooms from table rows
    if rooms_table:
        table_id = rooms_table.get('id')
        print(f"DEBUG: Processing table with id: {table_id}")
        
        # Find all table rows (children of the table)
        for row in graph_root.findall(f'.//mxCell[@parent="{table_id}"]'):
            if 'shape=tableRow' in row.get('style', ''):
                row_id = row.get('id')
                print(f"DEBUG: Processing row: {row_id}")
                
                # Find cells in this row
                cells = []
                for cell in graph_root.findall(f'.//mxCell[@parent="{row_id}"]'):
                    if 'shape=partialRectangle' in cell.get('style', ''):
                        cell_value = cell.get('value', '').strip()
                        if cell_value:  # Only add non-empty cells
                            cells.append(cell_value)
                
                print(f"DEBUG: Found cells in row: {cells}")
                
                # Parse room data: expect [code, name, height, levels]
                if len(cells) >= 3:
                    room_code = cells[0]
                    room_name = cells[1]
                    try:
                        room_height = float(cells[2])
                        # Parse levels if provided, otherwise default to [0]
                        levels = [0]
                        if len(cells) >= 4 and cells[3].strip():
                            try:
                                levels = [int(x.strip()) for x in cells[3].split(',')]
                            except ValueError:
                                print(f"DEBUG: Invalid levels value: {cells[3]}, using default [0]")
                        
                        rooms[room_code] = {
                            'name': room_name,
                            'height': room_height,
                            'points': [],  # Will be filled from connections
                            'levels': levels  # List of level indices
                        }
                        print(f"DEBUG: Added room {room_code}: {room_name}, height={room_height}, levels={levels}")
                    except ValueError:
                        print(f"DEBUG: Invalid height value: {cells[2]}")
    
    # Step 7: Extract level elevations from ellipses connected to levels
    level_elevations = {
        'Level01': 0.00,
        'Level02': 2.80,
        'Level03': 5.60
    }
    level_names = ['Level01', 'Level02', 'Level03']
    elevations = [0.00, 2.80, 5.60]
    
    print(f"DEBUG: Level elevations: {level_elevations}")
    
    # Step 8: Extract connections for each room to grid nodes
    print(f"DEBUG: Looking for room-to-node connections...")
    
    # First, find the individual room objects (not table cells)
    room_objects = {}
    for obj in graph_root.findall('object'):
        label = obj.get('label', '')
        if label and label.startswith('r') and label[1:].isdigit():
            room_code = label
            obj_id = obj.get('id')
            
            # Parse Levels from object attributes
            levels_str = obj.get('Levels', '')
            levels = [0]  # default
            if levels_str:
                try:
                    levels = [int(x.strip()) for x in levels_str.split(',')]
                except ValueError:
                    print(f"DEBUG: Invalid Levels attribute for {room_code}: {levels_str}, using default [0]")
            
            # Parse offset_interior if present
            offset_interior = float(obj.get('offset_interior', '0.125'))
            
            # Update room data
            if room_code in rooms:
                rooms[room_code]['levels'] = levels
                rooms[room_code]['offset_interior'] = offset_interior
                print(f"DEBUG: Updated room {room_code} with levels={levels}, offset_interior={offset_interior}")
            
            room_objects[room_code] = obj_id
            print(f"DEBUG: Found room object {room_code} with id {obj_id}")
    
    # Now find connections from room objects to nodes
    for room_code, obj_id in room_objects.items():
        if room_code not in rooms:
            continue
            
        connected_nodes = []
        for edge in graph_root.findall('mxCell[@edge="1"]'):
            if edge.get('source') == obj_id:
                target_id = edge.get('target')
                # Find the target object and get its label (node number)
                target_obj = graph_root.find(f'.//object[@id="{target_id}"]')
                if target_obj is not None:
                    node_label = target_obj.get('label', '')
                    try:
                        node_index = int(node_label)
                        if node_index in nodes:
                            connected_nodes.append(node_index)
                            print(f"DEBUG: Room {room_code} connected to node {node_index}: {nodes[node_index]}")
                    except ValueError:
                        pass
        
        # Sort nodes in counter-clockwise order for polygon creation
        if len(connected_nodes) >= 3:
            # Get node coordinates
            node_coords = [(nodes[node_idx][0], nodes[node_idx][1]) for node_idx in connected_nodes]
            
            # Calculate centroid
            centroid_x = sum(x for x, y in node_coords) / len(node_coords)
            centroid_y = sum(y for x, y in node_coords) / len(node_coords)
            
            # Sort by angle from centroid (counter-clockwise)
            def angle_from_centroid(point):
                x, y = point
                return math.atan2(y - centroid_y, x - centroid_x)
            
            node_coords.sort(key=angle_from_centroid)
            
            # Convert back to 2D points (Z will be set per level when creating spaces)
            rooms[room_code]['points'] = [(x, y) for x, y in node_coords]
            print(f"DEBUG: Room {room_code} final points (counter-clockwise): {rooms[room_code]['points']}")
    
    print(f"DEBUG: Final rooms: {[(k, len(v['points']), v.get('levels', [])) for k, v in rooms.items()]}")

    # Step 9: Create IFC file
    ifcfile = ifcopenshell.file(schema='IFC4')

    # Create basic entities
    person = ifcfile.createIfcPerson()
    person.Identification = 'User'
    org = ifcfile.createIfcOrganization()
    org.Name = 'Generated'
    person_org = ifcfile.createIfcPersonAndOrganization(person, org)
    application = ifcfile.createIfcApplication()
    application.ApplicationFullName = 'XML to IFC Generator'
    application.Version = '1.0'
    application.ApplicationIdentifier = 'XMLIFC'
    # Note: In IFC4, IfcApplication doesn't have Developer attribute
    owner_history = ifcfile.createIfcOwnerHistory()
    owner_history.OwningUser = person_org
    owner_history.OwningApplication = application
    owner_history.ChangeAction = 'ADDED'
    owner_history.CreationDate = int(time.time())

    # Units
    length_unit = ifcfile.createIfcSIUnit()
    length_unit.UnitType = 'LENGTHUNIT'
    length_unit.Name = 'METRE'
    unit_assignment = ifcfile.createIfcUnitAssignment([length_unit])

    # Project
    project = ifcfile.createIfcProject()
    project.Name = 'Generated Project'
    project.UnitsInContext = unit_assignment
    project.OwnerHistory = owner_history

    # Create geometric representation context
    context = ifcfile.createIfcGeometricRepresentationContext()
    context.ContextType = 'Model'
    context.ContextIdentifier = 'Body'
    context.CoordinateSpaceDimension = 3
    context.Precision = 1e-5
    context.WorldCoordinateSystem = ifcfile.createIfcAxis2Placement3D(ifcfile.createIfcCartesianPoint((0., 0., 0.)))
    context.TrueNorth = ifcfile.createIfcDirection((0., 1., 0.))
    project.RepresentationContexts = [context]

    # Site
    site = ifcfile.createIfcSite()
    site.Name = 'Site'
    site.OwnerHistory = owner_history
    ifcfile.createIfcRelAggregates(ifcopenshell.guid.new(), owner_history, None, None, project, [site])

    # Building
    building = ifcfile.createIfcBuilding()
    building.Name = 'Building01'
    building.OwnerHistory = owner_history
    ifcfile.createIfcRelAggregates(ifcopenshell.guid.new(), owner_history, None, None, site, [building])

    # Create Storeys with elevations from XML
    storeys = []
    storey_placements = {}  # Store placements for each storey
    for level_name, elevation in level_elevations.items():
        storey = ifcfile.createIfcBuildingStorey()
        storey.Name = level_name
        storey.Elevation = elevation
        storey.OwnerHistory = owner_history
        
        # Create placement for storey at its elevation
        storey_placement = ifcfile.createIfcLocalPlacement(
            None, 
            ifcfile.createIfcAxis2Placement3D(
                ifcfile.createIfcCartesianPoint((0., 0., elevation))
            )
        )
        storey.ObjectPlacement = storey_placement
        storey_placements[level_name] = storey_placement
        
        ifcfile.createIfcRelAggregates(ifcopenshell.guid.new(), owner_history, None, None, building, [storey])
        storeys.append(storey)
        print(f"DEBUG: Created storey {level_name} at elevation {elevation}")

    # Assign rooms to storeys (assuming based on connections, here simplistic: all to first storey)
    # For now, assume rooms are on Level01 (index 0), adjust based on XML connections if needed

    spaces_created = 0
    for room_id, room_data in rooms.items():
        if not room_data['points']:
            print(f"DEBUG: Skipping room {room_id} - no points")
            continue

        levels = room_data.get('levels', [0])
        offset = room_data.get('offset_interior', 0.125)
        
        for level_idx in levels:
            if level_idx < 0 or level_idx >= len(elevations):
                print(f"DEBUG: Invalid level index {level_idx} for room {room_id}, skipping")
                continue
                
            level_z = elevations[level_idx]
            storey_name = level_names[level_idx]
            
            print(f"DEBUG: Creating space for room {room_id} at level {level_idx} ({storey_name}) with elevation {level_z}, offset={offset}")

            # Points in counter-clockwise order as per description
            base_points = room_data['points']  # List of (x,y)

            # Create 2D polygon
            poly = Polygon(base_points)

            # Apply interior offset (negative buffer for interior)
            offset_poly = poly.buffer(-offset, join_style=2)  # join_style=2 for miter

            if not offset_poly.is_valid or offset_poly.is_empty:
                print(f"Warning: Invalid offset for {room_id} at level {level_idx}")
                continue

            # Get exterior coordinates (assuming simple polygon)
            offset_coords = list(offset_poly.exterior.coords)
            
            # Calculate dimensions and placement position
            min_x = min(x for x, y in offset_coords)
            max_x = max(x for x, y in offset_coords)
            min_y = min(y for x, y in offset_coords)
            max_y = max(y for x, y in offset_coords)
            width = max_x - min_x
            length = max_y - min_y
            
            print(f"DEBUG: Room {room_id} at level {level_idx} dimensions: {width:.2f} x {length:.2f} (min_x={min_x:.2f}, max_x={max_x:.2f}, min_y={min_y:.2f}, max_y={max_y:.2f})")

            # Translate profile to origin (relative coordinates)
            # The placement will position it at (min_x, min_y)
            relative_coords = [(x - min_x, y - min_y) for x, y in offset_coords]
            
            # Create IFC geometry for space
            # Create profile curve with relative coords (origin-based)
            points_ifc = [ifcfile.createIfcCartesianPoint((x, y)) for x, y in relative_coords]
            curve = ifcfile.createIfcPolyline(points_ifc)
            axis2placement = ifcfile.createIfcAxis2Placement2D(ifcfile.createIfcCartesianPoint((0., 0.)))
            profile = ifcfile.createIfcArbitraryClosedProfileDef('AREA', None, curve)

            # Extrusion
            direction = ifcfile.createIfcDirection((0., 0., 1.))
            extrude = ifcfile.createIfcExtrudedAreaSolid()
            extrude.SweptArea = profile
            extrude.Position = ifcfile.createIfcAxis2Placement3D(ifcfile.createIfcCartesianPoint((0., 0., 0.)))
            extrude.ExtrudedDirection = direction
            extrude.Depth = room_data['height']

            # Representation
            shape = ifcfile.createIfcShapeRepresentation()
            shape.ContextOfItems = ifcfile.by_type('IfcGeometricRepresentationContext')[0]
            shape.RepresentationIdentifier = 'Body'
            shape.RepresentationType = 'SweptSolid'
            shape.Items = [extrude]
            product_def = ifcfile.createIfcProductDefinitionShape(None, None, [shape])

            # Create IfcSpace
            space_name = f"{room_data['name']}_L{level_idx}"
            space = ifcfile.createIfcSpace()
            space.Name = space_name
            space.OwnerHistory = owner_history
            space.Representation = product_def

            # Placement (translate to base position with correct Z elevation)
            min_x = min(p[0] for p in base_points)
            min_y = min(p[1] for p in base_points)
            
            # Get the storey placement for this level
            storey_placement = storey_placements[storey_name]
            
            # Create placement relative to storey (Z=0 because storey already has elevation)
            placement = ifcfile.createIfcLocalPlacement(
                storey_placement, 
                ifcfile.createIfcAxis2Placement3D(
                    ifcfile.createIfcCartesianPoint((min_x, min_y, 0.))
                )
            )
            space.ObjectPlacement = placement
            
            print(f"DEBUG: Room {room_id} at level {level_idx} placed at world coordinates: ({min_x:.2f}, {min_y:.2f}, {level_z:.2f})")

            # Assign to correct storey
            assigned_to_storey = False
            for storey in storeys:
                if abs(storey.Elevation - level_z) < 0.01:  # Small tolerance for floating point comparison
                    ifcfile.createIfcRelContainedInSpatialStructure(ifcopenshell.guid.new(), owner_history, None, None, [space], storey)
                    assigned_to_storey = True
                    print(f"DEBUG: Assigned room {room_id} to storey {storey.Name} at elevation {storey.Elevation}")
                    break
            
            if not assigned_to_storey:
                # Fallback to first storey if no matching elevation found
                ifcfile.createIfcRelContainedInSpatialStructure(ifcopenshell.guid.new(), owner_history, None, None, [space], storeys[0])
                print(f"DEBUG: Assigned room {room_id} to first storey (fallback)")
            
            spaces_created += 1
    
    print(f"DEBUG: Created {spaces_created} spaces")

    # Write IFC file
    ifcfile.write(output_ifc_path)
    print(f"IFC file generated: {output_ifc_path}")
    
    return rooms, storeys, elevations, level_names

def export_to_glb(xml_file_path=r"C:/Users/ionut.ciuntuc/Downloads/Diagram.xml", output_glb_path="output_model.glb", output_obj_path="output_model.obj"):
    """Export the building model to GLB format using trimesh"""
    
    # Parse XML to get room data
    tree = ET.parse(xml_file_path)
    root = tree.getroot()
    diagram = root.find('diagram')
    mxGraphModel = diagram.find('mxGraphModel')
    graph_root = mxGraphModel.find('root')
    
    # Extract Axes
    axes_text = ''
    for cell in graph_root.findall('mxCell'):
        cell_value = cell.get('value', '')
        if 'x=[' in cell_value and 'y=[' in cell_value:
            axes_text = cell_value
            break
    
    axes_text = re.sub(r'<[^>]+>', '', axes_text)
    axes_text = axes_text.replace('&nbsp;', ' ').strip()
    
    x_start = axes_text.find('x=[') + 3
    x_end = axes_text.find(']', x_start)
    y_start = axes_text.find('y=[', x_end) + 3
    y_end = axes_text.find(']', y_start)
    
    x_coords = [float(v.strip()) for v in axes_text[x_start:x_end].split(',') if v.strip()]
    y_coords = [float(v.strip()) for v in axes_text[y_start:y_end].split(',') if v.strip()]
    
    # Generate nodes
    nodes = {}
    for j, y in enumerate(y_coords):
        for i, x in enumerate(x_coords):
            node_index = j * len(x_coords) + i
            nodes[node_index] = (x, y, 0.0)
    
    # Extract rooms
    rooms = {}
    rooms_table = None
    for cell in graph_root.findall('mxCell'):
        cell_value = cell.get('value', '').lower()
        if 'rooms' in cell_value and 'shape=table' in cell.get('style', ''):
            rooms_table = cell
            break
    
    if rooms_table:
        table_id = rooms_table.get('id')
        for row in graph_root.findall(f'.//mxCell[@parent="{table_id}"]'):
            if 'shape=tableRow' in row.get('style', ''):
                row_id = row.get('id')
                cells = []
                for cell in graph_root.findall(f'.//mxCell[@parent="{row_id}"]'):
                    if 'shape=partialRectangle' in cell.get('style', ''):
                        cell_value = cell.get('value', '').strip()
                        if cell_value:
                            cells.append(cell_value)
                
                if len(cells) >= 3:
                    room_code = cells[0]
                    room_name = cells[1]
                    try:
                        room_height = float(cells[2])
                        levels = [0]
                        if len(cells) >= 4 and cells[3].strip():
                            try:
                                levels = [int(x.strip()) for x in cells[3].split(',')]
                            except ValueError:
                                pass
                        
                        rooms[room_code] = {
                            'name': room_name,
                            'height': room_height,
                            'points': [],
                            'levels': levels
                        }
                    except ValueError:
                        pass
    
    # Extract room objects and connections
    room_objects = {}
    for obj in graph_root.findall('object'):
        label = obj.get('label', '')
        if label and label.startswith('r') and label[1:].isdigit():
            room_code = label
            obj_id = obj.get('id')
            
            levels_str = obj.get('Levels', '')
            levels = [0]
            if levels_str:
                try:
                    levels = [int(x.strip()) for x in levels_str.split(',')]
                except ValueError:
                    pass
            
            offset_interior = float(obj.get('offset_interior', '0.125'))
            
            if room_code in rooms:
                rooms[room_code]['levels'] = levels
                rooms[room_code]['offset_interior'] = offset_interior
            
            room_objects[room_code] = obj_id
    
    # Extract connections
    for room_code, obj_id in room_objects.items():
        if room_code not in rooms:
            continue
            
        connected_nodes = []
        for edge in graph_root.findall('mxCell[@edge="1"]'):
            if edge.get('source') == obj_id:
                target_id = edge.get('target')
                target_obj = graph_root.find(f'.//object[@id="{target_id}"]')
                if target_obj is not None:
                    node_label = target_obj.get('label', '')
                    try:
                        node_index = int(node_label)
                        if node_index in nodes:
                            connected_nodes.append(node_index)
                    except ValueError:
                        pass
        
        if len(connected_nodes) >= 3:
            node_coords = [(nodes[node_idx][0], nodes[node_idx][1]) for node_idx in connected_nodes]
            
            centroid_x = sum(x for x, y in node_coords) / len(node_coords)
            centroid_y = sum(y for x, y in node_coords) / len(node_coords)
            
            def angle_from_centroid(point):
                x, y = point
                return math.atan2(y - centroid_y, x - centroid_x)
            
            node_coords.sort(key=angle_from_centroid)
            rooms[room_code]['points'] = [(x, y) for x, y in node_coords]
    
    # Level elevations
    level_elevations = [0.00, 2.80, 5.60]
    
    # Create meshes with trimesh
    scene_meshes = []
    
    for room_id, room_data in rooms.items():
        if not room_data['points']:
            continue
        
        levels = room_data.get('levels', [0])
        offset = room_data.get('offset_interior', 0.125)
        
        for level_idx in levels:
            if level_idx < 0 or level_idx >= len(level_elevations):
                continue
                
            level_z = level_elevations[level_idx]
            
            base_points = room_data['points']
            poly = Polygon(base_points)
            offset_poly = poly.buffer(-offset, join_style=2)
            
            if not offset_poly.is_valid or offset_poly.is_empty:
                continue
            
            offset_coords = list(offset_poly.exterior.coords)
            
            # Calculate placement
            min_x = min(x for x, y in offset_coords)
            min_y = min(y for x, y in offset_coords)
            
            # Translate to relative coordinates
            relative_coords = [(x - min_x, y - min_y) for x, y in offset_coords]
            
            # Create 3D vertices for extruded shape
            height = room_data['height']
            
            # Bottom vertices (Z = 0 in local coords)
            n_points = len(relative_coords) - 1  # Last point is duplicate
            vertices_bottom = [(x, y, 0.0) for x, y in relative_coords[:n_points]]
            
            # Top vertices (Z = height in local coords)
            vertices_top = [(x, y, height) for x, y in relative_coords[:n_points]]
            
            # Combine all vertices
            vertices = np.array(vertices_bottom + vertices_top)
            
            # Create faces with double-sided geometry (front and back faces)
            faces = []
            
            # Bottom face (triangulated) - both sides
            for i in range(1, n_points - 1):
                faces.append([0, i, i + 1])  # Front face (looking down)
                faces.append([0, i + 1, i])  # Back face (looking up)
            
            # Top face (triangulated) - both sides
            for i in range(1, n_points - 1):
                faces.append([n_points, n_points + i + 1, n_points + i])  # Front face (looking up)
                faces.append([n_points, n_points + i, n_points + i + 1])  # Back face (looking down)
            
            # Side faces - both sides
            for i in range(n_points):
                next_i = (i + 1) % n_points
                # Outer faces
                faces.append([i, next_i, n_points + i])
                faces.append([next_i, n_points + next_i, n_points + i])
                # Inner faces (reversed winding for double-sided)
                faces.append([i, n_points + i, next_i])
                faces.append([next_i, n_points + i, n_points + next_i])
            
            faces = np.array(faces)
            
            # Create mesh
            mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
            
            # Apply world transformation (translation to final position)
            translation_matrix = trimesh.transformations.translation_matrix([min_x, min_y, level_z])
            mesh.apply_transform(translation_matrix)
            
            # Add color based on level
            colors = [(200, 200, 200, 255), (180, 220, 180, 255), (180, 180, 220, 255)]
            color = colors[level_idx % 3]
            mesh.visual.vertex_colors = color
            
            # Create PBR material with double-sided rendering (no culling)
            material = trimesh.visual.material.PBRMaterial(
                name=f"Material_{room_id}_L{level_idx}",
                baseColorFactor=[color[0]/255.0, color[1]/255.0, color[2]/255.0, color[3]/255.0],
                doubleSided=True,  # Disable backface culling
                alphaMode='OPAQUE'
            )
            mesh.visual.material = material
            
            scene_meshes.append(mesh)
            
            print(f"DEBUG: Created mesh for {room_id} at level {level_idx}, {len(vertices)} vertices, {len(faces)} faces")
    
    # Combine all meshes into a scene
    scene = trimesh.Scene(scene_meshes)
    
    # Export to GLB
    scene.export(output_glb_path, file_type='glb')
    print(f"GLB file generated: {output_glb_path}")
    print(f"Total meshes: {len(scene_meshes)}")
    
    # Export to OBJ
    # Combine all meshes into a single mesh for OBJ export
    combined_mesh = trimesh.util.concatenate(scene_meshes)
    combined_mesh.export(output_obj_path, file_type='obj')
    print(f"OBJ file generated: {output_obj_path}")
    print(f"Total vertices: {len(combined_mesh.vertices)}, Total faces: {len(combined_mesh.faces)}")

def scan_and_process_diagrams(root_folder, output_folder=None):
    """
    Scanează folderele pentru fișiere Diagram.xml și le procesează în GLB
    
    Args:
        root_folder: Folderul rădăcină pentru scanare
        output_folder: Folder opțional pentru output GLB (implicit: același folder cu XML-ul)
    
    Returns:
        dict: Dicționar cu căi GLB generate {xml_path: glb_path}
    """
    root_path = Path(root_folder)
    processed_files = {}
    
    # Caută toate fișierele Diagram.xml recursiv
    diagram_files = list(root_path.rglob("Diagram.xml"))
    
    print(f"[SCAN] Found {len(diagram_files)} Diagram.xml files in {root_folder}")
    
    for xml_path in diagram_files:
        try:
            print(f"\n[PROCESS] Processing: {xml_path}")
            
            # Determină calea de output
            if output_folder:
                output_dir = Path(output_folder)
                output_dir.mkdir(parents=True, exist_ok=True)
                # Creează nume unic bazat pe calea relativă
                rel_path = xml_path.relative_to(root_path)
                output_name = str(rel_path.parent).replace(os.sep, '_')
                glb_path = output_dir / f"{output_name}_model.glb"
            else:
                # Salvează în același folder cu XML-ul
                glb_path = xml_path.parent / "model.glb"
            
            # Procesează XML -> GLB
            export_to_glb(
                xml_file_path=str(xml_path),
                output_glb_path=str(glb_path),
                output_obj_path=str(glb_path.with_suffix('.obj'))
            )
            
            processed_files[str(xml_path)] = str(glb_path)
            print(f"[SUCCESS] Generated: {glb_path}")
            
        except Exception as e:
            print(f"[ERROR] Failed to process {xml_path}: {e}")
            import traceback
            traceback.print_exc()
    
    return processed_files


def generate_project_manifest(processed_files, output_path="project_manifest.json"):
    """
    Generează un manifest JSON cu toate fișierele GLB procesate
    
    Args:
        processed_files: Dicționar {xml_path: glb_path}
        output_path: Calea fișierului manifest
    """
    manifest = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_files": len(processed_files),
        "models": []
    }
    
    for xml_path, glb_path in processed_files.items():
        xml_path_obj = Path(xml_path)
        glb_path_obj = Path(glb_path)
        
        manifest["models"].append({
            "name": xml_path_obj.parent.name,
            "xml_source": str(xml_path),
            "glb_output": str(glb_path),
            "relative_path": str(glb_path_obj.relative_to(Path.cwd())) if glb_path_obj.is_relative_to(Path.cwd()) else str(glb_path)
        })
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    
    print(f"\n[MANIFEST] Generated manifest: {output_path}")
    print(f"[MANIFEST] Total models: {len(processed_files)}")
    
    return manifest


def load_project_models(manifest_path="project_manifest.json"):
    """
    Încarcă informațiile despre modelele din manifest
    
    Args:
        manifest_path: Calea către fișierul manifest
    
    Returns:
        list: Lista de dicționare cu informații despre modele
    """
    if not os.path.exists(manifest_path):
        print(f"[ERROR] Manifest not found: {manifest_path}")
        return []
    
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    
    print(f"[LOAD] Loaded {len(manifest['models'])} models from manifest")
    return manifest['models']


# Usage example:
# parse_xml_and_generate_ifc()  # Folosește calea hardcodată
# parse_xml_and_generate_ifc('custom_input.xml', 'custom_output.ifc')  # Folosește căi personalizate

if __name__ == "__main__":
    import sys
    
    # Verifică argumentele din linia de comandă
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "scan":
            # Scanează și procesează toate Diagram.xml din folder
            root_folder = sys.argv[2] if len(sys.argv) > 2 else "."
            output_folder = sys.argv[3] if len(sys.argv) > 3 else None
            
            print(f"[SCAN MODE] Scanning folder: {root_folder}")
            processed = scan_and_process_diagrams(root_folder, output_folder)
            
            # Generează manifest
            manifest_path = os.path.join(output_folder if output_folder else root_folder, "project_manifest.json")
            generate_project_manifest(processed, manifest_path)
            
        elif command == "load":
            # Încarcă și afișează informații din manifest
            manifest_path = sys.argv[2] if len(sys.argv) > 2 else "project_manifest.json"
            models = load_project_models(manifest_path)
            
            print("\n[MODELS]")
            for i, model in enumerate(models, 1):
                print(f"{i}. {model['name']}: {model['glb_output']}")
        
        else:
            print("Unknown command. Usage:")
            print("  python graph_to_glb.py scan [root_folder] [output_folder]")
            print("  python graph_to_glb.py load [manifest_path]")
    else:
        # Mod default: procesează fișierul hardcodat
        try:
            # Generate IFC
            parse_xml_and_generate_ifc()
            print("IFC Conversion completed successfully!")
            
            # Generate GLB and OBJ
            print("\nGenerating 3D formats (GLB & OBJ)...")
            export_to_glb()
            print("3D Conversion completed successfully!")
            
        except Exception as e:
            print(f"Eroare: {e}")
            import traceback
            traceback.print_exc()