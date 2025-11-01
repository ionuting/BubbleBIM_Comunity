import ezdxf
import trimesh
import numpy as np
from trimesh.creation import extrude_polygon
from shapely.geometry import Polygon
import uuid
import sys
import time
import json
import os
import re
from trimesh.exchange import gltf

# Import pentru conversia IFC în background
try:
    from ifc_background_converter import (
        create_background_converter, 
        process_xdata_for_element,
        IfcBackgroundConverter
    )
    IFC_CONVERSION_AVAILABLE = True
    print("[DEBUG] IFC Background Converter disponibil")
except ImportError as e:
    print(f"[WARNING] IFC Background Converter indisponibil: {e}")
    IFC_CONVERSION_AVAILABLE = False

# Import pentru conversia IFC bazată pe GLB
try:
    from ifc_glb_converter import convert_glb_to_ifc
    IFC_GLB_CONVERSION_AVAILABLE = True
    print("[DEBUG] IFC GLB Converter disponibil")
except ImportError as e:
    print(f"[WARNING] IFC GLB Converter indisponibil: {e}")
    IFC_GLB_CONVERSION_AVAILABLE = False

# Import pentru procesorul door/window
try:
    from door_window_processor import DoorWindowProcessor
    DOOR_WINDOW_PROCESSOR_AVAILABLE = True
    print("[DEBUG] Door/Window Processor disponibil")
except ImportError as e:
    print(f"[WARNING] Door/Window Processor indisponibil: {e}")
    DOOR_WINDOW_PROCESSOR_AVAILABLE = False

# -----------------------------
# Extragerea Z global din numele fișierului
# -----------------------------
def extract_global_z_from_filename(file_path):
    """
    Extrage valoarea Z globală din numele fișierului DXF.
    Caută ultimul număr după ultimul '_' în numele fișierului.
    
    Args:
        file_path: calea către fișierul DXF
    
    Returns:
        float: Valoarea Z globală sau 0.0 dacă nu poate fi extrasă
    
    Examples:
        "nivel1_2.80.dxf" -> 2.80
        "etaj2_-1.75.dxf" -> -1.75
        "basement_0.00.dxf" -> 0.00
        "multiple_underscores_3.25.dxf" -> 3.25
        "simple.dxf" -> 0.0 (fallback)
    """
    try:
        # Extrage numele fișierului fără extensie
        filename = os.path.splitext(os.path.basename(file_path))[0]
        
        # Caută ultimul '_' în numele fișierului
        underscore_pos = filename.rfind('_')
        if underscore_pos == -1:
            print(f"[DEBUG] No underscore found in filename '{filename}', using Z global = 0.0")
            return 0.0
        
        # Extrage partea după ultimul '_'
        z_part = filename[underscore_pos + 1:]
        
        # Încearcă să parseze ca număr float
        # Poate fi format ca "-1.75" sau "2.80" etc.
        global_z = float(z_part)
        
        print(f"[DEBUG] Extracted global Z from filename '{filename}': {global_z}")
        return global_z
        
    except (ValueError, IndexError) as e:
        print(f"[DEBUG] Could not extract global Z from filename '{file_path}': {e}")
        print(f"[DEBUG] Using default global Z = 0.0")
        return 0.0

# -----------------------------
# Evaluare formule matematice
# -----------------------------
def evaluate_math_formula(formula_str):
    """
    Evaluează o formulă matematică de tip '=2.1*0.9+1.2*1.2'
    Returnează valoarea calculată sau 0.0 în caz de eroare.
    """
    if not formula_str or not isinstance(formula_str, str):
        return 0.0
    
    # Elimină spațiile și semnul '=' de la început
    formula = formula_str.strip()
    if formula.startswith('='):
        formula = formula[1:]
    
    # Verifică că formula conține doar caractere sigure pentru evaluare matematică
    # Permite doar cifre, puncte, +, -, *, /, paranteze și spații
    if not re.match(r'^[\d\.\+\-\*\/\(\)\s]+$', formula):
        print(f"[DEBUG] Opening_area formula contains invalid characters: {formula_str}")
        return 0.0
    
    try:
        # Evaluează formula într-un context restricționat
        result = eval(formula, {"__builtins__": {}}, {})
        if isinstance(result, (int, float)):
            print(f"[DEBUG] Opening_area formula evaluated: '{formula_str}' = {result}")
            return float(result)
        else:
            print(f"[DEBUG] Opening_area formula does not return a number: {formula_str}")
            return 0.0
    except Exception as e:
        print(f"[DEBUG] Eroare la evaluarea formulei Opening_area '{formula_str}': {e}")
        return 0.0

# -----------------------------
# Materiale din JSON
# -----------------------------
def load_layer_materials(json_path):
    materials = {}
    if not os.path.exists(json_path):
        return materials
    with open(json_path, 'r', encoding='utf-8') as jsonfile:
        data = json.load(jsonfile)
        for layer, config in data.items():
            if isinstance(config, dict) and 'color' in config and 'alpha' in config:
                # Format JSON: {"color": [r, g, b], "alpha": a}
                materials[layer] = config['color'] + [config['alpha']]
            elif isinstance(config, list) and len(config) == 4:
                # Format direct array: [r, g, b, a]
                materials[layer] = config
    return materials

LAYER_MATERIALS = load_layer_materials(
    os.path.join(os.path.dirname(__file__), "../layer_materials.json")
)

def get_material(layer):
    if layer in LAYER_MATERIALS:
        return LAYER_MATERIALS[layer]
    return LAYER_MATERIALS.get("default", [0.5, 1.0, 0.0, 1.0])

# -----------------------------
# Funcții pentru control spațial cu cercuri
# -----------------------------
def read_control_circles(doc, layer="control", global_z=0.0):
    """
    Citește cercurile de control cu Z din XDATA pentru formele spațiale.
    Z-ul din XDATA este relativ la global_z din numele fișierului.
    """
    msp = doc.modelspace()
    control_points = []

    circles = list(msp.query(f"CIRCLE[layer=='{layer}']"))
    print(f"[DEBUG] Cercuri de control gasite pe layer '{layer}': {len(circles)}")

    for c in circles:
        x, y = float(c.dxf.center[0]), float(c.dxf.center[1])
        z_relative = 0.0  # Z relativ din XDATA

        if c.has_xdata:
            try:
                xdata = c.get_xdata("QCAD")
                for code, value in xdata:
                    if code == 1000 and isinstance(value, str) and value.startswith("z:"):
                        z_relative = float(value.split(":")[1])
            except Exception as e:
                print(f"[DEBUG] Eroare XDATA pentru cerc de control ({x:.2f}, {y:.2f}): {e}")

        # Calculează Z final: global_z + z_relative
        z_final = global_z + z_relative
        control_points.append((x, y, z_final))
        print(f"[DEBUG] Cerc de control ({x:.2f}, {y:.2f}) -> z_relative={z_relative:.2f}, z_final={z_final:.2f} (global_z={global_z:.2f})")

    return control_points

def get_z_at_point_from_controls(control_points, x, y):
    """
    Calculează Z pentru un punct (x,y) folosind interpolarea din cercurile de control.
    Folosește distanța inversă ponderată (inverse distance weighting).
    """
    if not control_points:
        return 0.0
    
    if len(control_points) == 1:
        return control_points[0][2]
    
    # Calculează distanțele la toate cercurile de control
    distances = []
    weights = []
    
    for cx, cy, cz in control_points:
        dist = np.sqrt((x - cx)**2 + (y - cy)**2)
        
        # Dacă punctul este foarte aproape de un cerc de control, returnează Z-ul lui
        if dist < 1e-6:
            return cz
        
        distances.append(dist)
        weights.append(1.0 / (dist**2))  # Pondere inversă cu distanța la pătrat
    
    # Interpolarea ponderată
    total_weight = sum(weights)
    weighted_z = sum(w * control_points[i][2] for i, w in enumerate(weights))
    
    return weighted_z / total_weight

def create_spatial_mesh_from_contour(points, control_points, height):
    """
    Creează un mesh spațial din conturul 2D folosind cercurile de control pentru Z.
    
    Args:
        points: lista de puncte (x, y) care definesc conturul
        control_points: lista de cercuri de control (x, y, z)
        height: înălțimea extrudării
    
    Returns:
        mesh rezultat sau None dacă nu se poate crea
    """
    if len(points) < 3:
        return None
    
    try:
        # Calculează Z pentru fiecare punct din contur
        base_vertices_3d = []
        for x, y in points:
            z = get_z_at_point_from_controls(control_points, x, y)
            base_vertices_3d.append([x, y, z])
        
        base_vertices_3d = np.array(base_vertices_3d)
        
        # Pentru control_points, extrudarea se face pe axa Z globală (verticală)
        normal = np.array([0, 0, 1])  # Axa Z globală
        
        # Creează vârfurile de sus prin extrudarea pe axa Z globală
        top_vertices_3d = base_vertices_3d + height * normal
        
        # Combină toate vârfurile
        all_vertices = np.vstack([base_vertices_3d, top_vertices_3d])
        num_points = len(points)
        
        # Creează fețele
        faces = []
        
        # Triangulează poligonul de bază și de sus (triangulare în ventilator)
        if num_points > 3:
            # Fața de jos (poligonul de bază)
            for i in range(1, num_points - 1):
                faces.append([0, i + 1, i])
            
            # Fața de sus (poligonul extrudat) - orientare inversă
            for i in range(1, num_points - 1):
                faces.append([num_points, num_points + i, num_points + i + 1])
        else:
            # Pentru triunghiuri
            faces.append([0, 2, 1])  # Fața de jos
            faces.append([num_points, num_points + 1, num_points + 2])  # Fața de sus
        
        # Fețele laterale
        for i in range(num_points):
            next_i = (i + 1) % num_points
            # Două triunghiuri pentru fiecare latură
            faces.append([i, next_i, next_i + num_points])
            faces.append([i, next_i + num_points, i + num_points])
        
        # Creează mesh-ul
        mesh = trimesh.Trimesh(vertices=all_vertices, faces=faces)
        
        # Verifică și repară mesh-ul
        try:
            if not mesh.is_watertight:
                print(f"[DEBUG] Mesh spatial nu este watertight, incerc repararea...")
            mesh.fix_normals()
        except Exception as ex:
            print(f"[DEBUG] Avertisment validare mesh spatial: {ex}")
        
        base_z_avg = np.mean(base_vertices_3d[:, 2])
        top_z_avg = np.mean(top_vertices_3d[:, 2])
        print(f"[DEBUG] Mesh spatial creat: vertices={len(all_vertices)}, faces={len(faces)}, Z_base_avg={base_z_avg:.2f}, Z_top_avg={top_z_avg:.2f}")
        
        return mesh
        
    except Exception as ex:
        print(f"[DEBUG] Crearea mesh-ului spatial a esuat: {ex}")
        return None

# -----------------------------
# Funcții pentru arce
# -----------------------------
def discretize_arc(start, end, bulge, segments=16):
    """
    Convertește un arc definit prin bulge în puncte discrete.
    
    Args:
        start: (x, y) punct de start
        end: (x, y) punct de final
        bulge: valoarea bulge din DXF
        segments: numărul de segmente pentru arc
    
    Returns:
        Lista de puncte (x, y) care aproximează arcul
    """
    if abs(bulge) < 1e-6:
        return [start, end]
    
    # Calculează parametrii cercului
    start = np.array(start)
    end = np.array(end)
    
    chord = end - start
    chord_length = np.linalg.norm(chord)
    
    if chord_length < 1e-6:
        return [start]
    
    # Unghi total al arcului
    angle = 4 * np.arctan(bulge)
    
    # Raza cercului
    radius = chord_length * (1 + bulge**2) / (4 * abs(bulge))
    
    # Centrul cercului
    sagitta = bulge * chord_length / 2
    chord_mid = (start + end) / 2
    chord_dir = chord / chord_length
    perp = np.array([-chord_dir[1], chord_dir[0]])
    center = chord_mid + perp * (radius - abs(sagitta)) * np.sign(bulge)
    
    # Unghiuri de start și end
    start_angle = np.arctan2(start[1] - center[1], start[0] - center[0])
    
    # Generează puncte pe arc
    points = []
    for i in range(segments + 1):
        t = i / segments
        current_angle = start_angle + angle * t
        point = center + radius * np.array([np.cos(current_angle), np.sin(current_angle)])
        points.append(tuple(point))
    
    return points[:-1]  # Excludem ultimul punct pentru a evita duplicarea

def lwpolyline_to_points(entity, arc_segments=16):
    """
    Convertește LWPOLYLINE în listă de puncte, discretizând arcele.
    
    Args:
        entity: entitatea LWPOLYLINE din ezdxf
        arc_segments: număr de segmente pentru fiecare arc
    
    Returns:
        Lista de puncte (x, y)
    """
    points = []
    lwpoints = list(entity.lwpoints)
    
    for i in range(len(lwpoints)):
        x, y, start_width, end_width, bulge = lwpoints[i]
        start_point = (float(x), float(y))
        
        if i < len(lwpoints) - 1:
            next_x, next_y = lwpoints[i + 1][:2]
            end_point = (float(next_x), float(next_y))
        elif entity.closed:
            next_x, next_y = lwpoints[0][:2]
            end_point = (float(next_x), float(next_y))
        else:
            points.append(start_point)
            break
        
        if abs(bulge) > 1e-6:
            # Arc prezent
            arc_points = discretize_arc(start_point, end_point, bulge, arc_segments)
            points.extend(arc_points)
        else:
            # Segment drept
            points.append(start_point)
    
    return points

def polyline_to_points(entity, arc_segments=16):
    """
    Convertește POLYLINE în listă de puncte, discretizând arcele.
    
    Args:
        entity: entitatea POLYLINE din ezdxf
        arc_segments: număr de segmente pentru fiecare arc
    
    Returns:
        Lista de puncte (x, y)
    """
    points = []
    vertices = list(entity.vertices)
    
    for i in range(len(vertices)):
        vertex = vertices[i]
        start_point = (float(vertex.dxf.location.x), float(vertex.dxf.location.y))
        bulge = getattr(vertex.dxf, 'bulge', 0.0)
        
        if i < len(vertices) - 1:
            next_vertex = vertices[i + 1]
            end_point = (float(next_vertex.dxf.location.x), float(next_vertex.dxf.location.y))
        elif entity.is_closed:
            next_vertex = vertices[0]
            end_point = (float(next_vertex.dxf.location.x), float(next_vertex.dxf.location.y))
        else:
            points.append(start_point)
            break
        
        if abs(bulge) > 1e-6:
            # Arc prezent
            arc_points = discretize_arc(start_point, end_point, bulge, arc_segments)
            points.extend(arc_points)
        else:
            # Segment drept
            points.append(start_point)
    
    return points

# -----------------------------
# Funcții pentru rotația în jurul primului segment
# -----------------------------

def is_special_angle(angle_degrees):
    """
    Verifică dacă unghiul este unul dintre unghiurile speciale: 90°, 180°, 270°
    Pentru aceste unghiuri se folosește rotația 3D directă, nu proiecția pe plan.
    """
    # Normalizează unghiul în intervalul [0, 360)
    normalized_angle = angle_degrees % 360
    
    # Lista unghiurilor speciale
    special_angles = [90, 180, 270]
    
    # Verifică cu toleranță pentru erori de float
    for special in special_angles:
        if abs(normalized_angle - special) < 1e-6:
            return True
    
    return False

def create_projected_rotated_mesh(points, height, angle_degrees):
    """
    Creează un mesh prin proiectarea conturului pe un plan înclinat și extrudarea pe normala planului.
    NOUA IMPLEMENTARE: Pentru unghiuri diferite de 90°, 180°, 270°
    
    Args:
        points: lista de puncte (x, y) care definesc poligonul
        height: înălțimea extrudării
        angle_degrees: unghiul de rotație în grade în jurul primului segment
    
    Returns:
        mesh rezultat sau None dacă nu se poate crea
    """
    if len(points) < 3:
        return None
        
    try:
        # Primul segment este între punctele 0 și 1
        p1 = np.array([points[0][0], points[0][1], 0])  # Primul punct
        p2 = np.array([points[1][0], points[1][1], 0])  # Al doilea punct
        
        # Calculează vectorul primului segment
        segment_vector = p2 - p1
        segment_length = np.linalg.norm(segment_vector)
        
        if segment_length < 1e-6:
            print(f"[DEBUG] Primul segment prea scurt pentru proiectie: {segment_length}")
            return None
        
        # Normalizează vectorul pentru a obține axa de rotație
        rotation_axis = segment_vector / segment_length
        
        # Convertește unghiul din grade în radiani
        angle_radians = np.radians(angle_degrees)
        
        # Creează matricea de rotație folosind formula Rodriguez
        cos_angle = np.cos(angle_radians)
        sin_angle = np.sin(angle_radians)
        
        # Matricea antisimetrică pentru vectorul axei
        axis_cross_matrix = np.array([
            [0, -rotation_axis[2], rotation_axis[1]],
            [rotation_axis[2], 0, -rotation_axis[0]],
            [-rotation_axis[1], rotation_axis[0], 0]
        ])
        
        # Formula Rodriguez pentru matricea de rotație
        rotation_matrix = (np.eye(3) + 
                          sin_angle * axis_cross_matrix + 
                          (1 - cos_angle) * np.dot(axis_cross_matrix, axis_cross_matrix))
        
        # Calculează normala planului înclinat
        # Începem cu normala verticală (0, 0, 1) și o rotim
        original_normal = np.array([0, 0, 1])
        inclined_normal = rotation_matrix @ original_normal
        
        # PROIECȚIA: Proiectează punctele pe planul înclinat
        # Pentru fiecare punct, calculează proiecția pe planul care trece prin primul punct
        projected_points_3d = []
        
        for point in points:
            # Punctul în spațiul 3D
            point_3d = np.array([point[0], point[1], 0])
            
            # Calculează distanța de la punct la planul înclinat
            # Planul trece prin p1 și are normala inclined_normal
            to_point = point_3d - p1
            distance_to_plane = np.dot(to_point, inclined_normal)
            
            # Proiectează punctul pe planul înclinat
            projected_point = point_3d - distance_to_plane * inclined_normal
            projected_points_3d.append(projected_point)
        
        # Creează mesh-ul din punctele proiectate
        num_points = len(projected_points_3d)
        
        # Punctele de bază (pe planul înclinat)
        base_vertices = np.array(projected_points_3d)
        
        # Punctele de sus (extrudate pe direcția normală a planului înclinat)
        top_vertices = base_vertices + height * inclined_normal
        
        # Combină toate vertexurile
        all_vertices = np.vstack([base_vertices, top_vertices])
        
        # Creează fețele folosind triangulare pentru poligoanele de bază și sus
        faces = []
        
        # Triangulează poligonul de bază și de sus
        if num_points > 3:
            # Fața de jos (poligonul proiectat) - triangulare în ventilator
            for i in range(1, num_points - 1):
                faces.append([0, i + 1, i])  # Orientarea corectă pentru fața de jos
            
            # Fața de sus (poligonul extrudat) - triangulare în ventilator
            for i in range(1, num_points - 1):
                faces.append([num_points, num_points + i, num_points + i + 1])  # Orientarea corectă pentru fața de sus
        else:
            # Pentru triunghiuri, fețele sunt simple
            faces.append([0, 2, 1])  # Fața de jos
            faces.append([num_points, num_points + 1, num_points + 2])  # Fața de sus
        
        # Fețele laterale - triunghiuri între bază și sus
        for i in range(num_points):
            next_i = (i + 1) % num_points
            # Două triunghiuri pentru fiecare latură
            faces.append([i, next_i, next_i + num_points])
            faces.append([i, next_i + num_points, i + num_points])
        
        # Creează mesh-ul
        mesh = trimesh.Trimesh(vertices=all_vertices, faces=faces)
        
        # Verifică și repară mesh-ul dacă este necesar
        try:
            if not mesh.is_watertight:
                print(f"[DEBUG] Mesh not watertight dupa proiectia pe planul inclinat")
            mesh.fix_normals()
        except Exception as ex:
            print(f"[DEBUG] Mesh validation warning: {ex}")
        
        print(f"[DEBUG] Created projected rotated mesh: angle={angle_degrees}°, projected_normal={inclined_normal}, vertices={len(all_vertices)}, faces={len(faces)}")
        return mesh
        
    except Exception as ex:
        print(f"[DEBUG] Projected rotated mesh creation failed: {ex}")
        return None

def create_inclined_mesh(points, height, angle_degrees):
    """
    FUNCȚIE MENȚINUTĂ PENTRU COMPATIBILITATE
    Creează un mesh prin proiectarea conturului pe un plan înclinat și extrudarea pe normala planului.
    
    Args:
        points: lista de puncte (x, y) care definesc poligonul
        height: înălțimea extrudării
        angle_degrees: unghiul de înclinare în grade (pozitiv = antiorar, negativ = orar)
    
    Returns:
        mesh rezultat sau None dacă nu se poate crea
    """
    if len(points) < 3:
        return None
        
    try:
        # Primul segment este între punctele 0 și 1
        p1 = np.array([points[0][0], points[0][1], 0])  # Primul punct
        p2 = np.array([points[1][0], points[1][1], 0])  # Al doilea punct
        
        # Calculează vectorul primului segment (axa de rotație)
        segment_vector = p2 - p1
        segment_length = np.linalg.norm(segment_vector)
        
        if segment_length < 1e-6:
            print(f"[DEBUG] Primul segment prea scurt pentru inclinare: {segment_length}")
            return None
        
        # Normalizează vectorul pentru a obține axa de rotație
        rotation_axis = segment_vector / segment_length
        
        # Convertește unghiul din grade în radiani
        angle_radians = np.radians(angle_degrees)
        
        # Creează matricea de rotație folosind formula Rodriguez
        cos_angle = np.cos(angle_radians)
        sin_angle = np.sin(angle_radians)
        
        # Matricea antisimetrică pentru vectorul axei
        axis_cross_matrix = np.array([
            [0, -rotation_axis[2], rotation_axis[1]],
            [rotation_axis[2], 0, -rotation_axis[0]],
            [-rotation_axis[1], rotation_axis[0], 0]
        ])
        
        # Formula Rodriguez pentru matricea de rotație
        rotation_matrix = (np.eye(3) + 
                          sin_angle * axis_cross_matrix + 
                          (1 - cos_angle) * np.dot(axis_cross_matrix, axis_cross_matrix))
        
        # Calculează normala planului înclinat
        # Începem cu normala verticală (0, 0, 1) și o rotim
        original_normal = np.array([0, 0, 1])
        inclined_normal = rotation_matrix @ original_normal
        
        # Proiectează punctele pe planul înclinat
        # Pentru fiecare punct, calculează proiecția pe planul care trece prin primul punct
        projected_points_3d = []
        
        for point in points:
            # Punctul în spațiul 3D
            point_3d = np.array([point[0], point[1], 0])
            
            # Calculează distanța de la punct la planul înclinat
            # Planul trece prin p1 și are normala inclined_normal
            to_point = point_3d - p1
            distance_to_plane = np.dot(to_point, inclined_normal)
            
            # Proiectează punctul pe planul înclinat
            projected_point = point_3d - distance_to_plane * inclined_normal
            projected_points_3d.append(projected_point)
        
        # Creează poligonul din punctele proiectate
        # Pentru a crea un mesh valid, avem nevoie să definim fețele
        num_points = len(projected_points_3d)
        
        # Punctele de bază (pe planul înclinat)
        base_vertices = np.array(projected_points_3d)
        
        # Punctele de sus (extrudate pe direcția normală)
        top_vertices = base_vertices + height * inclined_normal
        
        # Combină toate vertexurile
        all_vertices = np.vstack([base_vertices, top_vertices])
        
        # Creează fețele folosind triangulare pentru poligoanele de bază și sus
        faces = []
        
        # Triangulează poligonul de bază și de sus
        # Pentru simplitate, folosim triangulare în ventilator din primul punct
        if num_points > 3:
            # Fața de jos (poligonul de bază) - triangulare în ventilator
            for i in range(1, num_points - 1):
                faces.append([0, i + 1, i])  # Orientarea corectă pentru fața de jos
            
            # Fața de sus (poligonul extrudat) - triangulare în ventilator
            for i in range(1, num_points - 1):
                faces.append([num_points, num_points + i, num_points + i + 1])  # Orientarea corectă pentru fața de sus
        else:
            # Pentru triunghiuri, fețele sunt simple
            faces.append([0, 2, 1])  # Fața de jos
            faces.append([num_points, num_points + 1, num_points + 2])  # Fața de sus
        
        # Fețele laterale - triunghiuri între bază și sus
        for i in range(num_points):
            next_i = (i + 1) % num_points
            # Două triunghiuri pentru fiecare latură
            faces.append([i, next_i, next_i + num_points])
            faces.append([i, next_i + num_points, i + num_points])
        
        # Creează mesh-ul
        mesh = trimesh.Trimesh(vertices=all_vertices, faces=faces)
        
        # Verifică și repară mesh-ul dacă este necesar
        try:
            if not mesh.is_watertight:
                print(f"[DEBUG] Mesh not watertight dupa proiectia pe planul inclinat")
            mesh.fix_normals()
        except Exception as ex:
            print(f"[DEBUG] Mesh validation warning: {ex}")
        
        print(f"[DEBUG] Created inclined mesh: angle={angle_degrees}°, normal={inclined_normal}, vertices={len(all_vertices)}, faces={len(faces)}")
        return mesh
        
    except Exception as ex:
        print(f"[DEBUG] Inclined mesh creation failed: {ex}")
        return None

def create_rotated_90_mesh(points, height):
    """
    Rotește poligonul cu 90° în jurul primului segment și extrudează pe normala feței rotite.
    
    Args:
        points: lista de puncte (x, y) care definesc poligonul
        height: înălțimea extrudării
    
    Returns:
        mesh rezultat sau None dacă nu se poate crea
    """
    if len(points) < 3:
        return None
        
    try:
        # Primul segment este între punctele 0 și 1
        p1 = np.array([points[0][0], points[0][1], 0])  # Primul punct
        p2 = np.array([points[1][0], points[1][1], 0])  # Al doilea punct
        
        # Calculează vectorul primului segment (axa de rotație)
        segment_vector = p2 - p1
        segment_length = np.linalg.norm(segment_vector)
        
        if segment_length < 1e-6:
            print(f"[DEBUG] Primul segment prea scurt pentru rotatie 90°: {segment_length}")
            return None
        
        # Normalizează vectorul pentru a obține axa de rotație
        rotation_axis = segment_vector / segment_length
        
        # Rotație fixă de 90° (π/2 radiani)
        angle_radians = np.pi / 2
        
        # Creează matricea de rotație folosind formula Rodriguez pentru 90°
        cos_angle = np.cos(angle_radians)  # cos(90°) = 0
        sin_angle = np.sin(angle_radians)  # sin(90°) = 1
        
        # Matricea antisimetrică pentru vectorul axei
        axis_cross_matrix = np.array([
            [0, -rotation_axis[2], rotation_axis[1]],
            [rotation_axis[2], 0, -rotation_axis[0]],
            [-rotation_axis[1], rotation_axis[0], 0]
        ])
        
        # Formula Rodriguez pentru matricea de rotație cu 90°
        rotation_matrix = (np.eye(3) + 
                          sin_angle * axis_cross_matrix + 
                          (1 - cos_angle) * np.dot(axis_cross_matrix, axis_cross_matrix))
        
        # Rotește toate punctele în jurul primului segment
        rotated_points_3d = []
        
        for point in points:
            # Punctul în spațiul 3D
            point_3d = np.array([point[0], point[1], 0])
            
            # Translează punctul la origine (relativ la p1)
            translated_point = point_3d - p1
            
            # Aplică rotația
            rotated_point = rotation_matrix @ translated_point
            
            # Translează înapoi
            final_point = rotated_point + p1
            rotated_points_3d.append(final_point)
        
        # Calculează normala feței rotite folosind primele 3 puncte
        if len(rotated_points_3d) >= 3:
            v1 = rotated_points_3d[1] - rotated_points_3d[0]
            v2 = rotated_points_3d[2] - rotated_points_3d[0]
            face_normal = np.cross(v1, v2)
            face_normal_length = np.linalg.norm(face_normal)
            
            if face_normal_length > 1e-6:
                face_normal = face_normal / face_normal_length
            else:
                face_normal = np.array([0, 0, 1])  # Fallback
        else:
            face_normal = np.array([0, 0, 1])
        
        # Punctele de bază (pe fața rotită)
        base_vertices = np.array(rotated_points_3d)
        
        # Punctele de sus (extrudate pe direcția normalei feței rotite)
        top_vertices = base_vertices + height * face_normal
        
        # Combină toate vertexurile
        all_vertices = np.vstack([base_vertices, top_vertices])
        num_points = len(points)
        
        # Creează fețele folosind aceeași logică ca în create_inclined_mesh
        faces = []
        
        # Triangulează poligonul de bază și de sus
        if num_points > 3:
            # Fața de jos (poligonul rotit) - triangulare în ventilator
            for i in range(1, num_points - 1):
                faces.append([0, i + 1, i])  # Orientarea corectă pentru fața de jos
            
            # Fața de sus (poligonul extrudat) - triangulare în ventilator
            for i in range(1, num_points - 1):
                faces.append([num_points, num_points + i, num_points + i + 1])  # Orientarea corectă pentru fața de sus
        else:
            # Pentru triunghiuri, fețele sunt simple
            faces.append([0, 2, 1])  # Fața de jos
            faces.append([num_points, num_points + 1, num_points + 2])  # Fața de sus
        
        # Fețele laterale - triunghiuri între bază și sus
        for i in range(num_points):
            next_i = (i + 1) % num_points
            # Două triunghiuri pentru fiecare latură
            faces.append([i, next_i, next_i + num_points])
            faces.append([i, next_i + num_points, i + num_points])
        
        # Creează mesh-ul
        mesh = trimesh.Trimesh(vertices=all_vertices, faces=faces)
        
        # Verifică și repară mesh-ul dacă este necesar
        try:
            if not mesh.is_watertight:
                print(f"[DEBUG] Mesh 90° rotit nu este watertight, incerc repararea...")
            mesh.fix_normals()
        except Exception as ex:
            print(f"[DEBUG] Mesh 90° validation warning: {ex}")
        
        print(f"[DEBUG] Created 90° rotated mesh: normal={face_normal}, vertices={len(all_vertices)}, faces={len(faces)}")
        return mesh
        
    except Exception as ex:
        print(f"[DEBUG] 90° rotated mesh creation failed: {ex}")
        return None

def create_angle_based_mesh(points, height, angle_degrees):
    """
    Creează mesh bazat pe tipul unghiului:
    - Pentru 90°, 180°, 270°: folosește rotația 3D directă (funcția existentă)
    - Pentru alte unghiuri: folosește proiecția pe planul rotit (noua implementare)
    
    Args:
        points: lista de puncte (x, y) care definesc poligonul
        height: înălțimea extrudării  
        angle_degrees: unghiul de rotație în grade
    
    Returns:
        mesh rezultat sau None dacă nu se poate crea
    """
    if len(points) < 3:
        return None
    
    # Verifică dacă unghiul este special (90°, 180°, 270°)
    if is_special_angle(angle_degrees):
        print(f"[DEBUG] Unghi special {angle_degrees}° - folosesc rotatia 3D directa")
        # Pentru unghiurile speciale, folosește implementarea existentă create_inclined_mesh
        return create_inclined_mesh(points, height, angle_degrees)
    else:
        print(f"[DEBUG] Unghi arbitrar {angle_degrees}° - folosesc proiectia pe planul rotit")
        # Pentru unghiurile arbitrare, folosește noua implementare cu proiecție
        return create_projected_rotated_mesh(points, height, angle_degrees)

# -----------------------------
# Funcții pentru tăierea elementelor la acoperiș
# -----------------------------
def trim_elements_to_roof(solids, mapping):
    """
    Taie elementele structurale (IfcWall, IfcCovering, IfcColumn) la fața inferioară a acoperișului.
    
    Args:
        solids: lista de mesh-uri
        mapping: lista de dicționare cu informații despre mesh-uri
    
    Returns:
        tuple: (solids_trimmed, mapping_updated)
    """
    # Identifică elementele de acoperiș și elementele de tăiat
    roof_meshes = []
    structural_elements = []
    other_elements = []
    
    uuid_to_mesh = {mesh.metadata.get("uuid"): mesh for mesh in solids}
    uuid_to_entry = {entry["uuid"]: entry for entry in mapping}
    
    for mesh in solids:
        layer = mesh.metadata.get("layer", "")
        
        # Identifică acoperișurile (pot avea diverse denumiri)
        if any(roof_keyword in layer.lower() for roof_keyword in ["roof", "slab", "ifcslab"]):
            roof_meshes.append(mesh)
            print(f"[DEBUG] Found roof element: {mesh.metadata.get('name', 'unknown')} on layer {layer}")
        
        # Identifică elementele structurale care trebuie tăiate
        # REGULA: IfcColumn și IfcBeam NU se taie de plăci/acoperișuri, doar de alte coloane/grinzi cu solid:0
        elif layer in ["IfcWall", "IfcCovering"]:
            structural_elements.append(mesh)
            print(f"[DEBUG] Found structural element to trim: {mesh.metadata.get('name', 'unknown')} on layer {layer}")
        
        # IfcColumn și IfcBeam nu se trimit la structural trimming
        elif layer in ["IfcColumn", "IfcBeam"]:
            other_elements.append(mesh)
            print(f"[DEBUG] IfcColumn/IfcBeam preserved from trimming: {mesh.metadata.get('name', 'unknown')} on layer {layer}")
        
        else:
            other_elements.append(mesh)
    
    if not roof_meshes:
        print("[DEBUG] No roof elements found, skipping structural trimming")
        return solids, mapping
    
    if not structural_elements:
        print("[DEBUG] No structural elements found to trim")
        return solids, mapping
    
    print(f"[DEBUG] Trimming {len(structural_elements)} structural elements to {len(roof_meshes)} roof elements")
    
    trimmed_elements = []
    updated_mapping = []
    
    # Procesează fiecare element structural
    for struct_mesh in structural_elements:
        struct_uuid = struct_mesh.metadata.get("uuid")
        struct_entry = uuid_to_entry.get(struct_uuid)
        
        if not struct_entry:
            trimmed_elements.append(struct_mesh)
            continue
        
        # Găsește intersecțiile cu toate acoperișurile
        intersections_found = False
        final_mesh = struct_mesh
        
        for roof_mesh in roof_meshes:
            try:
                # Calculează bounding box-urile pentru verificare rapidă
                struct_bounds = struct_mesh.bounds
                roof_bounds = roof_mesh.bounds
                
                # Verifică dacă există overlap în planul XY
                xy_overlap = not (
                    struct_bounds[1][0] < roof_bounds[0][0] or  # struct la stânga de roof
                    struct_bounds[0][0] > roof_bounds[1][0] or  # struct la dreapta de roof
                    struct_bounds[1][1] < roof_bounds[0][1] or  # struct în față de roof
                    struct_bounds[0][1] > roof_bounds[1][1]     # struct în spate de roof
                )
                
                if not xy_overlap:
                    continue
                
                # Calculează Z-ul minim al acoperișului (fața inferioară)
                roof_bottom_z = roof_bounds[0][2]
                struct_top_z = struct_bounds[1][2]
                
                print(f"[DEBUG] Struct {struct_mesh.metadata.get('name')} top: {struct_top_z:.3f}, Roof {roof_mesh.metadata.get('name')} bottom: {roof_bottom_z:.3f}")
                
                # Dacă elementul structural depășește acoperișul
                if struct_top_z > roof_bottom_z:
                    # Creează un plan de tăiere la Z-ul minim al acoperișului
                    cutting_plane_origin = [0, 0, roof_bottom_z]
                    cutting_plane_normal = [0, 0, 1]  # Plan orizontal
                    
                    # Taie mesh-ul structural
                    try:
                        trimmed_mesh = final_mesh.slice_plane(
                            plane_normal=cutting_plane_normal,
                            plane_origin=cutting_plane_origin,
                            cap=True  # Închide mesh-ul după tăiere
                        )
                        
                        if trimmed_mesh and hasattr(trimmed_mesh, 'vertices') and len(trimmed_mesh.vertices) > 0:
                            # Păstrează metadata originală
                            trimmed_mesh.metadata = dict(final_mesh.metadata)
                            final_mesh = trimmed_mesh
                            intersections_found = True
                            
                            print(f"[DEBUG] Trimmed {struct_mesh.metadata.get('name')} at Z={roof_bottom_z:.3f}")
                        else:
                            print(f"[DEBUG] Trimming resulted in empty mesh for {struct_mesh.metadata.get('name')}")
                    
                    except Exception as ex:
                        print(f"[DEBUG] Failed to trim {struct_mesh.metadata.get('name')}: {ex}")
            
            except Exception as ex:
                print(f"[DEBUG] Error processing roof intersection: {ex}")
        
        # Adaugă mesh-ul procesat (tăiat sau original)
        trimmed_elements.append(final_mesh)
        
        # Actualizează mapping-ul
        if struct_entry:
            updated_entry = dict(struct_entry)
            if intersections_found:
                updated_entry["trimmed_to_roof"] = True
                # Recalculează volumul după tăierea la acoperiș
                if hasattr(final_mesh, 'volume') and final_mesh.volume > 0:
                    updated_entry["volume"] = float(final_mesh.volume)
                    print(f"[DEBUG] Volume updated after roof trimming: {updated_entry['mesh_name']} = {final_mesh.volume:.3f}m³")
            updated_mapping.append(updated_entry)
    
    # Combină toate elementele: acoperișuri + structurale tăiate + altele
    final_solids = roof_meshes + trimmed_elements + other_elements
    
    # Adaugă în mapping elementele care nu sunt structurale
    for mesh in roof_meshes + other_elements:
        mesh_uuid = mesh.metadata.get("uuid")
        entry = uuid_to_entry.get(mesh_uuid)
        if entry:
            updated_mapping.append(entry)
    
    print(f"[DEBUG] Structural trimming complete: {len(final_solids)} total elements")
    
    return final_solids, updated_mapping

def apply_xyz_rotations(mesh, rotate_x, rotate_y, rotate_z=0.0):
    """
    Aplică rotații pe axele X, Y și Z la un mesh deja extrudat.
    
    Args:
        mesh: trimesh object
        rotate_x: unghiul de rotație în jurul axei X în grade
        rotate_y: unghiul de rotație în jurul axei Y în grade  
        rotate_z: unghiul de rotație în jurul axei Z în grade
    
    Returns:
        mesh rotit sau mesh original dacă nu există rotații
    """
    if abs(rotate_x) < 1e-6 and abs(rotate_y) < 1e-6 and abs(rotate_z) < 1e-6:
        return mesh  # Nu sunt rotații de aplicat
    
    try:
        mesh_copy = mesh.copy()
        
        # Aplică rotațiile în ordine: Z, Y, X (pentru a păstra consistența cu standardele 3D)
        if abs(rotate_z) > 1e-6:
            angle_z_rad = np.radians(rotate_z)
            rotation_z = trimesh.transformations.rotation_matrix(angle_z_rad, [0, 0, 1])
            mesh_copy.apply_transform(rotation_z)
            print(f"[DEBUG] Applied Z rotation: {rotate_z}°")
        
        if abs(rotate_y) > 1e-6:
            angle_y_rad = np.radians(rotate_y)
            rotation_y = trimesh.transformations.rotation_matrix(angle_y_rad, [0, 1, 0])
            mesh_copy.apply_transform(rotation_y)
            print(f"[DEBUG] Applied Y rotation: {rotate_y}°")
        
        if abs(rotate_x) > 1e-6:
            angle_x_rad = np.radians(rotate_x)
            rotation_x = trimesh.transformations.rotation_matrix(angle_x_rad, [1, 0, 0])
            mesh_copy.apply_transform(rotation_x)
            print(f"[DEBUG] Applied X rotation: {rotate_x}°")
        
        print(f"[DEBUG] Applied XYZ rotations: X={rotate_x}°, Y={rotate_y}°, Z={rotate_z}°")
        return mesh_copy
        
    except Exception as ex:
        print(f"[DEBUG] XYZ rotation failed: {ex}")
        return mesh

# -----------------------------
# Procesare blocuri Door/Window cu logica TOV/FOV
# -----------------------------
def process_door_window_block(doc, insert_entity, global_z, mesh_name_count, mapping, solids, voids, control_points=None):
    """
    Procesează un bloc Door/Window TOV folosind geometria FOV din biblioteci.
    
    Args:
        doc: Documentul DXF
        insert_entity: Entitatea INSERT care conține blocul TOV
        global_z: Z global pentru nivel
        mesh_name_count: Counter pentru nume mesh-uri
        mapping: Lista de mapping pentru IFC
        solids: Lista mesh-urilor solide
        voids: Lista mesh-urilor void
        control_points: Puncte de control opționale
    
    Returns:
        bool: True dacă blocul a fost procesat cu succes
    """
    if not DOOR_WINDOW_PROCESSOR_AVAILABLE:
        return False
        
    try:
        # Inițializează procesorul
        processor = DoorWindowProcessor()
        
        # Extrage datele TOV din INSERT entity
        block_name = getattr(insert_entity.dxf, "name", "")
        insert_point = getattr(insert_entity.dxf, "insert", None)
        rotation_angle = getattr(insert_entity.dxf, "rotation", 0.0)
        scale_x = getattr(insert_entity.dxf, "xscale", 1.0)
        scale_y = getattr(insert_entity.dxf, "yscale", 1.0)
        scale_z = getattr(insert_entity.dxf, "zscale", 1.0)
        handle = getattr(insert_entity, 'handle', 'unknown')
        xdata = getattr(insert_entity, 'xdata', {})
        
        if not insert_point or not block_name.endswith('_TOV'):
            return False
            
        print(f"[DEBUG] ===== Processing Door/Window TOV: {block_name} =====")
        print(f"[DEBUG] TOV Position: ({insert_point.x:.2f}, {insert_point.y:.2f})")
        print(f"[DEBUG] TOV Rotation: {rotation_angle:.1f}°")
        tov_layer = getattr(insert_entity.dxf, 'layer', 'unknown')
        print(f"[DEBUG] TOV Layer: {tov_layer}")
        
        # Determină tipul bibliotecii
        base_name = processor._get_base_name(block_name)
        lib_type = 'doors' if base_name.lower().startswith('door') else 'windows'
        fov_name = base_name + '_FOV'
        
        print(f"[DEBUG] Expected library type: {lib_type}")
        print(f"[DEBUG] Expected FOV name: {fov_name}")
        print(f"[DEBUG] Base name: {base_name}")
        
        # Încarcă biblioteca corespunzătoare
        if not processor.load_library(lib_type):
            print(f"[WARNING] Could not load {lib_type} library")
            return False
        else:
            print(f"[DEBUG] Successfully loaded {lib_type} library")
            
        # Debug: afișează toate blocurile din bibliotecă
        if lib_type in processor.library_blocks:
            blocks_in_lib = list(processor.library_blocks[lib_type].keys())
            print(f"[DEBUG] Available blocks in {lib_type} library: {blocks_in_lib}")
            
        # Verifică dacă există FOV în bibliotecă
        if fov_name not in processor.library_blocks[lib_type]:
            print(f"[WARNING] FOV block {fov_name} not found in {lib_type} library")
            return False
        else:
            print(f"[DEBUG] Found FOV block {fov_name} in {lib_type} library")
            
        # Extrage datele TOV
        tov_data = processor.extract_tov_data(insert_entity, doc)
        if not tov_data:
            print(f"[ERROR] Failed to extract TOV data from {block_name}")
            return False
            
        # Extrage geometria FOV din bibliotecă
        fov_block = processor.library_blocks[lib_type][fov_name]['block']
        fov_doc = processor.library_blocks[lib_type][fov_name]['doc']
        fov_geometry = processor.extract_fov_geometry(fov_block, fov_doc, lib_type)
        
        if not fov_geometry:
            print(f"[ERROR] Failed to extract FOV geometry from {fov_name}")
            return False
            
        print(f"[DEBUG] Found {len(fov_geometry)} layers in FOV: {list(fov_geometry.keys())}")
        
        # Procesează fiecare layer din FOV
        for layer_name, layer_data in fov_geometry.items():
            entities = layer_data['entities']
            thickness = layer_data['thickness']
            solid_flag = layer_data['solid']
            
            print(f"[DEBUG] Processing FOV layer '{layer_name}': {len(entities)} entities, thickness={thickness}, solid={solid_flag}")
            
            # Verifică și ajustează thickness-ul pentru vizibilitate
            if thickness < 0.05:
                thickness = 0.15  # Minimum thickness pentru vizibilitate
                print(f"[DEBUG] Adjusted thickness to {thickness} for better visibility")
            
            # Procesează entitățile din layer folosind logica existentă
            for entity in entities:
                try:
                    # Procesează entitatea ca și cum ar fi în planul principal
                    # dar cu transformările de la TOV
                    entity_type = entity.dxftype()
                    
                    if entity_type in ["LWPOLYLINE", "POLYLINE", "LINE", "ARC", "CIRCLE"]:
                        # Creează mesh-ul pentru entitate
                        mesh_name = f"{base_name}_{layer_name}_{entity_type}"
                        print(f"[DEBUG] Creating mesh from {entity_type} entity in layer {layer_name}, solid={solid_flag}")
                        mesh = create_mesh_from_entity(entity, thickness, solid_flag, mesh_name)
                        
                        if mesh and len(mesh.vertices) > 0:
                            # APLICĂ TRANSFORMĂRILE ÎN ORDINEA CORECTĂ:
                            
                            # 1. Scalare la origine (0,0,0)
                            if scale_x != 1.0 or scale_y != 1.0 or scale_z != 1.0:
                                scale_matrix = np.eye(4)
                                scale_matrix[0, 0] = scale_x
                                scale_matrix[1, 1] = scale_y  
                                scale_matrix[2, 2] = scale_z
                                mesh.apply_transform(scale_matrix)
                                print(f"[DEBUG] Applied scaling: ({scale_x:.2f}, {scale_y:.2f}, {scale_z:.2f})")
                            
                            # 2. Rotație la origine (0,0,0) - pentru DXF INSERT entities este în jurul axei Z
                            if abs(tov_data['rotation']) > 0.01:  # Doar dacă rotația este semnificativă
                                angle_rad = np.radians(tov_data['rotation'])
                                rotation_matrix = trimesh.transformations.rotation_matrix(angle_rad, [0, 0, 1], [0, 0, 0])
                                mesh.apply_transform(rotation_matrix)
                                print(f"[DEBUG] Applied Z-axis rotation: {tov_data['rotation']:.1f}° around origin")
                            
                            # 3. Translație la poziția finală în world space
                            final_position = [
                                tov_data['position'][0],
                                tov_data['position'][1],
                                tov_data['position'][2]
                            ]
                            mesh.apply_translation(final_position)
                            print(f"[DEBUG] Applied final translation to: ({final_position[0]:.2f}, {final_position[1]:.2f}, {final_position[2]:.2f})")
                            
                            # Adaugă mesh-ul la listele corespunzătoare
                            # Păstrează numele real al layer-ului ca material pentru diferențiere
                            material_name = layer_name  # Păstrează 'IfcDoor', 'wood', 'glass' separate
                            mesh_entry = {
                                "mesh": mesh,
                                "material": material_name,
                                "block_name": f"DoorWindow_{base_name}_{layer_name}",
                                "insert_position": {
                                    "x": float(tov_data['position'][0]),
                                    "y": float(tov_data['position'][1]),
                                    "z": float(tov_data['position'][2])
                                },
                                "rotation_angle": float(tov_data['rotation']),
                                "layer": layer_name,
                                "solid": solid_flag
                            }
                            print(f"[DEBUG] Assigned material '{material_name}' to layer '{layer_name}'")
                            
                            if solid_flag:
                                solids.append(mesh_entry)
                            else:
                                voids.append(mesh_entry)
                                
                            # Adaugă în mapping pentru IFC
                            mapping_entry = create_ifc_mapping_entry(
                                mesh_entry, handle, xdata, base_name, "door" if lib_type == "doors" else "window"
                            )
                            mapping.append(mapping_entry)
                            
                            # Incrementează counter pentru mesh-uri
                            if 'count' not in mesh_name_count:
                                mesh_name_count['count'] = 0
                            mesh_name_count['count'] += 1
                            print(f"[DEBUG] Added Door/Window mesh: {layer_name} ({'solid' if solid_flag else 'void'})")
                            
                except Exception as e:
                    print(f"[WARNING] Error processing FOV entity {entity_type}: {e}")
                    import traceback
                    print(f"[DEBUG] Full error: {traceback.format_exc()}")
                    continue
                    
        # După procesarea tuturor entităților, creează mesh-uri separate per material
        if solids or voids:
            print(f"[DEBUG] Creating separate meshes per material from {len(solids)} solids and {len(voids)} voids")
            
            # Grupează mesh-urile după material
            material_groups = {}
            
            # Grupează solid-urile (doar cele din TOV processing care sunt dicționare)
            tov_solids = []
            tov_voids = []
            
            # Separă TOV entries (dicționare) de mesh-urile normale (Trimesh objects)
            for solid in solids:
                if isinstance(solid, dict) and 'mesh' in solid:
                    # TOV entry - dicționar cu mesh și metadate
                    tov_solids.append(solid)
                # Ignoră mesh-urile normale (Trimesh direct) - nu sunt din TOV
            
            for void in voids:
                if isinstance(void, dict) and 'mesh' in void:
                    # TOV entry - dicționar cu mesh și metadate
                    tov_voids.append(void)
                # Ignoră mesh-urile normale - nu sunt din TOV
            
            print(f"[DEBUG] Found {len(tov_solids)} TOV solids and {len(tov_voids)} TOV voids from {len(solids)}+{len(voids)} total")
            
            # Grupează TOV solid-urile după material
            for solid in tov_solids:
                material = solid.get('material', 'default')
                if material not in material_groups:
                    material_groups[material] = {'solids': [], 'voids': []}
                material_groups[material]['solids'].append(solid)
            
            # Grupează TOV void-urile (pot afecta toate materialele)
            for void in tov_voids:
                void_material = void.get('material', 'glass')
                # Void-urile se aplică asupra tuturor materialelor solide
                for material in material_groups:
                    if material_groups[material]['solids']:  # Doar dacă există solids
                        material_groups[material]['voids'].append(void)
            
            print(f"[DEBUG] Found {len(material_groups)} material groups: {list(material_groups.keys())}")
            
            # Creează mesh-uri separate pentru fiecare material
            for material, group in material_groups.items():
                group_solids = group['solids']
                group_voids = group['voids']
                
                if not group_solids:
                    continue
                    
                print(f"[DEBUG] Processing material '{material}': {len(group_solids)} solids, {len(group_voids)} voids")
                
                # Combină mesh-urile din același material
                if len(group_solids) == 1 and not group_voids:
                    # Un singur solid, fără voids
                    final_mesh = group_solids[0]['mesh']
                    print(f"[DEBUG] Using single mesh for material '{material}'")
                else:
                    # Multiple solids sau cu voids - aplică Boolean operations
                    final_mesh = combine_tov_meshes(group_solids, group_voids, f"{base_name}_{material}")
                
                if final_mesh:
                    # Creează entry pentru mesh-ul final
                    material_entry = {
                        "mesh": final_mesh,
                        "name": f"{base_name}_{material}",
                        "material": material,
                        "layer": group_solids[0]['layer'],  # Folosește layer-ul primului solid
                        "solid": 1
                    }
                    
                    # Adaugă în solids (va fi preluat în funcția apelantă)
                    solids.append(material_entry)
                    
                    # Creează mapping entry pentru material
                    mapping_entry = {
                        "mesh_name": f"DoorWindow_{base_name}_{material}",
                        "uuid": str(__import__('uuid').uuid4()),
                        "ifc_type": f"Ifc{'Door' if lib_type == 'doors' else 'Window'}",
                        "name": f"{base_name}_{material}",
                        "material": material,
                        "position": {
                            "x": tov_data['position'][0],
                            "y": tov_data['position'][1],
                            "z": tov_data['position'][2]
                        },
                        "rotation": tov_data['rotation'],
                        "layer": material_entry['layer'],
                        "solid": 1,
                        "handle": handle,
                        "xdata": str(xdata) if xdata else None  # Convert to string for JSON
                    }
                    mapping.append(mapping_entry)
                    
                    print(f"[DEBUG] Successfully created TOV mesh for material '{material}': {len(final_mesh.vertices)} vertices")
            
            # Curăță listele originale (păstrează doar mesh-urile finale)
            original_count = len(solids) + len(voids)
            final_count = len(material_groups)
            
            # Păstrează doar ultimele mesh-uri (cele per material)
            solids[:] = solids[-final_count:] if final_count <= len(solids) else solids
            voids.clear()  # Clear all individual voids
            
            print(f"[DEBUG] Reduced {original_count} individual meshes to {final_count} material-based meshes")
        
        print(f"[DEBUG] Successfully processed Door/Window TOV: {block_name}")
        return True
        
    except Exception as e:
        print(f"[ERROR] Error processing Door/Window block {block_name}: {e}")
        return False

def arc_to_points(entity, segments=16):
    """
    Convertește un ARC în listă de puncte
    """
    try:
        center = entity.dxf.center
        radius = entity.dxf.radius
        start_angle = entity.dxf.start_angle
        end_angle = entity.dxf.end_angle
        
        # Normalizează unghiurile în radiani
        start_rad = np.radians(start_angle)
        end_rad = np.radians(end_angle)
        
        # Gestionează arcele care trec peste 0°
        if end_rad < start_rad:
            end_rad += 2 * np.pi
            
        angle_range = end_rad - start_rad
        angle_step = angle_range / segments
        
        points = []
        for i in range(segments + 1):
            angle = start_rad + i * angle_step
            x = center.x + radius * np.cos(angle)
            y = center.y + radius * np.sin(angle)
            points.append((x, y))
            
        return points
        
    except Exception as e:
        print(f"[WARNING] Error converting arc to points: {e}")
        return []

def manual_mesh_combine(mesh1, mesh2):
    """
    Combină manual două mesh-uri prin concatenarea vertices și faces
    """
    try:
        import numpy as np
        
        # Combină vertices
        vertices = np.vstack([mesh1.vertices, mesh2.vertices])
        
        # Ajustează indices pentru faces din mesh2
        faces1 = mesh1.faces
        faces2 = mesh2.faces + len(mesh1.vertices)  # Offset pentru vertices din mesh2
        
        # Combină faces
        faces = np.vstack([faces1, faces2])
        
        # Creează noul mesh
        combined = trimesh.Trimesh(vertices=vertices, faces=faces)
        return combined
        
    except Exception as e:
        print(f"[WARNING] Manual mesh combine failed: {e}")
        return mesh1  # Return original if combine fails

def combine_tov_meshes(solids, voids, base_name):
    """
    Combină mesh-urile solid și aplică operațiile de void pentru TOV complex geometry
    """
    try:
        if not solids:
            print(f"[WARNING] No solid meshes to combine for {base_name}")
            return None
            
        # Începe cu primul mesh solid
        combined = solids[0]['mesh'].copy()
        print(f"[DEBUG] Starting with solid mesh: {len(combined.vertices)} vertices, {len(combined.faces)} faces")
        
        # Combină toate mesh-urile solid prin uniune
        for i, solid_entry in enumerate(solids[1:], 1):
            try:
                solid_mesh = solid_entry['mesh']
                print(f"[DEBUG] Combining solid {i}: {len(solid_mesh.vertices)} vertices")
                
                # Verifică că mesh-ul este valid
                if len(solid_mesh.vertices) > 0 and len(solid_mesh.faces) > 0:
                    try:
                        # Încearcă cu motorul implicit trimesh (fără Blender)
                        combined = combined.union(solid_mesh)
                        print(f"[DEBUG] Union result: {len(combined.vertices)} vertices, {len(combined.faces)} faces")
                    except Exception as union_error:
                        print(f"[DEBUG] Union failed, merging geometries manually: {union_error}")
                        # Fallback: combină manual vertices și faces
                        combined = manual_mesh_combine(combined, solid_mesh)
                        print(f"[DEBUG] Manual combine result: {len(combined.vertices)} vertices, {len(combined.faces)} faces")
                    
            except Exception as e:
                print(f"[DEBUG] Could not union solid {i}, continuing: {e}")
                continue
        
        # Aplică operațiile de void (substracting)
        for i, void_entry in enumerate(voids):
            try:
                void_mesh = void_entry['mesh']
                print(f"[DEBUG] Subtracting void {i}: {len(void_mesh.vertices)} vertices")
                
                # Verifică că mesh-ul este valid
                if len(void_mesh.vertices) > 0 and len(void_mesh.faces) > 0:
                    try:
                        # Încearcă cu motorul implicit trimesh
                        combined = combined.difference(void_mesh)
                        print(f"[DEBUG] Difference result: {len(combined.vertices)} vertices, {len(combined.faces)} faces")
                    except Exception as diff_error:
                        print(f"[DEBUG] Difference failed, skipping void operation: {diff_error}")
                        # Pentru void-uri, putem ignora dacă Boolean operation-ul nu reușește
                        continue
                    
            except Exception as e:
                print(f"[DEBUG] Could not subtract void {i}, continuing: {e}")
                continue
        
        # Verifică rezultatul final
        if hasattr(combined, 'vertices') and len(combined.vertices) > 0:
            print(f"[DEBUG] Final combined mesh: {len(combined.vertices)} vertices, {len(combined.faces)} faces")
            return combined
        else:
            print(f"[WARNING] Combined mesh is empty or invalid for {base_name}")
            return solids[0]['mesh']  # Return original if combination fails
            
    except Exception as e:
        print(f"[ERROR] Error combining TOV meshes for {base_name}: {e}")
        import traceback
        print(f"[DEBUG] Full traceback: {traceback.format_exc()}")
        return solids[0]['mesh'] if solids else None

def create_mesh_from_entity(entity, thickness, solid_flag, mesh_name):
    """
    Creează mesh din entitate folosind logica existentă de procesare
    """
    try:
        entity_type = entity.dxftype()
        mesh = None
        
        if entity_type == "LWPOLYLINE":
            points = lwpolyline_to_points(entity, 16)
            closed = getattr(entity, "closed", False)
            if closed and len(points) >= 3:
                poly = Polygon(points)
                if poly.is_valid and poly.area > 0:
                    # Pentru TOV entities, distinge între doors și windows
                    if thickness < 0.5:  # Thin meshes sunt de obicei din procesarea TOV
                        if 'door' in mesh_name.lower():
                            # Pentru uși, păstrează thickness-ul subțire pentru tăiere în pereți
                            # Ușile sunt de obicei void-uri care taie pereții
                            mesh = extrude_polygon(poly, max(thickness, 0.2))  # Minimum 20cm pentru uși
                            print(f"[DEBUG] Door mesh kept thin: {thickness:.2f} -> {max(thickness, 0.2):.2f} for wall cutting")
                        else:
                            # Pentru ferestre și alte elemente, îmbunătățește înălțimea
                            height = max(thickness, 2.5)  # Minimum înălțime realistă pentru ferestre
                            mesh = extrude_polygon(poly, height)
                            print(f"[DEBUG] Enhanced window/other mesh height from {thickness:.2f} to {height:.2f}")
                    else:
                        mesh = extrude_polygon(poly, thickness)
                    
        elif entity_type == "POLYLINE":
            # Similar cu LWPOLYLINE dar pentru POLYLINE vechi
            points = []
            for vertex in entity.vertices:
                points.append((vertex.dxf.location.x, vertex.dxf.location.y))
            
            if len(points) >= 3:
                # Verifică dacă este închis
                closed = entity.is_closed or (len(points) > 2 and 
                    abs(points[0][0] - points[-1][0]) < 1e-6 and 
                    abs(points[0][1] - points[-1][1]) < 1e-6)
                    
                if closed:
                    if points[0] != points[-1]:
                        points.append(points[0])  # Închide poligonul
                    poly = Polygon(points[:-1])  # Exclude ultimul punct duplicat
                    if poly.is_valid and poly.area > 0:
                        mesh = extrude_polygon(poly, thickness)
                        
        elif entity_type == "LINE":
            # Pentru LINE, creează o geometrie subțire (rectangulară)
            start = entity.dxf.start
            end = entity.dxf.end
            
            # Calculează un vector perpendicular pentru lățime
            dx = end.x - start.x
            dy = end.y - start.y
            length = (dx**2 + dy**2)**0.5
            
            if length > 1e-6:
                # Vector perpendicular normalizat cu lățime mică
                width = min(0.1, thickness * 0.1)  # Lățime mică pentru linii
                px = -dy / length * width * 0.5
                py = dx / length * width * 0.5
                
                # Creează un rectangle subțire
                points = [
                    (start.x + px, start.y + py),
                    (end.x + px, end.y + py),
                    (end.x - px, end.y - py),
                    (start.x - px, start.y - py)
                ]
                
                poly = Polygon(points)
                if poly.is_valid and poly.area > 0:
                    mesh = extrude_polygon(poly, thickness)
                    
        elif entity_type == "ARC":
            # Pentru ARC, discretizează în segmente
            arc_segments = 16
            points = arc_to_points(entity, arc_segments)
            
            if len(points) >= 2:
                # Pentru arc, creează o cale subțire
                width = min(0.1, thickness * 0.1)
                # Creează o cale cu lățime mică de-a lungul arcului
                # Pentru simplitate, tratează ca pe o linie între primul și ultimul punct
                start_point = points[0]
                end_point = points[-1]
                
                dx = end_point[0] - start_point[0]
                dy = end_point[1] - start_point[1]
                length = (dx**2 + dy**2)**0.5
                
                if length > 1e-6:
                    px = -dy / length * width * 0.5
                    py = dx / length * width * 0.5
                    
                    rect_points = [
                        (start_point[0] + px, start_point[1] + py),
                        (end_point[0] + px, end_point[1] + py),
                        (end_point[0] - px, end_point[1] - py),
                        (start_point[0] - px, start_point[1] - py)
                    ]
                    
                    poly = Polygon(rect_points)
                    if poly.is_valid and poly.area > 0:
                        mesh = extrude_polygon(poly, thickness)
                        
        elif entity_type == "CIRCLE":
            # Pentru CIRCLE, creează un cilindru
            center = entity.dxf.center
            radius = entity.dxf.radius
            
            if radius > 1e-6:
                # Creează un cerc discretizat
                circle_segments = 32
                angle_step = 2 * np.pi / circle_segments
                points = []
                
                for i in range(circle_segments):
                    angle = i * angle_step
                    x = center.x + radius * np.cos(angle)
                    y = center.y + radius * np.sin(angle)
                    points.append((x, y))
                
                poly = Polygon(points)
                if poly.is_valid and poly.area > 0:
                    mesh = extrude_polygon(poly, thickness)
        
        if mesh is not None and len(mesh.vertices) > 0:
            print(f"[DEBUG] Created mesh for {entity_type}: {len(mesh.vertices)} vertices, {len(mesh.faces)} faces")
            return mesh
        else:
            print(f"[WARNING] Failed to create mesh for {entity_type}")
            return None
            
    except Exception as e:
        print(f"[ERROR] Error creating mesh from {entity_type}: {e}")
        return None

def get_material_for_layer(layer_name):
    """
    Returnează materialul pentru un layer bazat pe maparea existentă
    """
    layer_material_map = {
        'IfcDoor': 'wood',
        'IfcWindow': 'glass', 
        'glass': 'glass',
        'wood': 'wood',
        'window': 'glass',
        'door': 'wood',
        # Adaugă mai multe variații pentru door/window layers
        'door_frame': 'wood',
        'door_panel': 'wood', 
        'window_frame': 'wood',
        'window_glass': 'glass',
        'window_sash': 'wood',
        # Pentru layere din library care încep cu diferite prefixe
        'Door': 'wood',
        'Window': 'glass'
    }
    
    # Verifică și după prefixe dacă nu găsește exact
    layer_lower = layer_name.lower()
    if 'door' in layer_lower:
        return 'wood'
    elif 'window' in layer_lower:
        return 'glass' if 'glass' in layer_lower else 'wood'
    elif 'glass' in layer_lower:
        return 'glass'
    elif 'wood' in layer_lower:
        return 'wood'
    
    return layer_material_map.get(layer_name, 'default')

def create_ifc_mapping_entry(mesh_entry, handle, xdata, element_name, element_type):
    """
    Creează intrarea de mapping pentru IFC conform formatului existent
    """
    import uuid
    return {
        "mesh_name": mesh_entry.get("name", element_name),
        "uuid": str(uuid.uuid4()),  # Adaugă uuid pentru compatibilitate cu restul mapping-ului
        "ifc_type": f"Ifc{element_type.capitalize()}",
        "name": element_name,
        "material": mesh_entry.get("material", "default"),
        "position": {
            "x": tov_data['position'][0] if 'tov_data' in locals() else 0.0,
            "y": tov_data['position'][1] if 'tov_data' in locals() else 0.0, 
            "z": tov_data['position'][2] if 'tov_data' in locals() else 0.0
        },
        "rotation": tov_data['rotation'] if 'tov_data' in locals() else 0.0,
        "layer": mesh_entry.get("layer", "unknown"),
        "solid": mesh_entry.get("solid", 1),
        "handle": handle,
        "xdata": str(xdata) if xdata else None
    }

# -----------------------------
# Procesare geometrie din blocuri
# -----------------------------
def process_block_geometry(doc, block_layout, insert_point, rotation_angle, 
                          scale_x, scale_y, scale_z, layer, insert_handle,
                          insert_xdata, mesh_name_count, mapping, solids, voids, control_points=None, global_z=0.0):
    """
    Procesează geometria dintr-un bloc DXF cu rotația în jurul punctului de inserție.
    
    Args:
        doc: documentul DXF
        block_layout: layout-ul blocului
        insert_point: punctul de inserție al blocului
        rotation_angle: rotația blocului în grade
        scale_x, scale_y, scale_z: scalarea blocului
        layer: layer-ul entității INSERT
        insert_handle: handle-ul entității INSERT
        insert_xdata: XDATA de pe entitatea INSERT
        mesh_name_count: counter pentru nume mesh-uri
        mapping: lista de mapping
        solids: lista de mesh-uri solide
        voids: lista de mesh-uri void
    """
    
    # Parsează XDATA de pe entitatea INSERT pentru parametri globali de bloc
    def parse_insert_xdata(xdata_dict, global_z):
        rotate_x_global = 0.0
        rotate_y_global = 0.0
        z_relative = 0.0  # Z relativ la global_z
        block_solid_flag = 1  # Implicit solid, doar dacă e explicit 0 devine void
        
        for appid_data in xdata_dict.values():
            for code, value in appid_data:
                if code == 1000:
                    sval = str(value)
                    if sval.startswith("rotate_x:") or sval.startswith("rotation_x:"):
                        try:
                            rotate_x_global = float(sval.split(":")[1])
                        except Exception:
                            pass
                    elif sval.startswith("rotate_y:") or sval.startswith("rotation_y:"):
                        try:
                            rotate_y_global = float(sval.split(":")[1])
                        except Exception:
                            pass
                    elif sval.startswith("z:"):
                        try:
                            z_relative = float(sval.split(":")[1])
                        except Exception:
                            pass
                    elif sval.startswith("solid:"):
                        try:
                            block_solid_flag = int(sval.split(":")[1])
                        except Exception:
                            pass
        
        # Calculează Z final: global_z + z_relative
        z_final = global_z + z_relative
        return rotate_x_global, rotate_y_global, z_final, z_relative, block_solid_flag
    
    rotate_x_global, rotate_y_global, z_final, z_relative, block_solid_flag = parse_insert_xdata(insert_xdata, global_z)
    
    if abs(rotate_x_global) > 1e-6 or abs(rotate_y_global) > 1e-6:
        print(f"[DEBUG] Block global rotations: X={rotate_x_global:.1f}°, Y={rotate_y_global:.1f}°")
    
    # Determină dacă blocul în ansamblu este solid sau void
    block_is_void = (block_solid_flag == 0)
    if block_is_void:
        print(f"[DEBUG] Block configured as VOID (solid:0) - will cut IfcWall and IfcCovering")
    
    # Punctul de origine pentru rotații (punctul de inserție cu Z final)
    rotation_origin = np.array([insert_point.x, insert_point.y, z_final])
    
    # Procesează fiecare entitate din bloc
    for entity in block_layout:
        ent_type = entity.dxftype()
        
        # Extrage XDATA din entitatea din bloc
        entity_xdata = {}
        if entity.has_xdata:
            try:
                appids = []
                if hasattr(entity, "get_xdata_appids"):
                    appids = entity.get_xdata_appids()
                if "QCAD" not in appids:
                    appids.append("QCAD")
                
                for appid in appids:
                    try:
                        data = entity.get_xdata(appid)
                        if data:
                            entity_xdata[appid] = list(data)
                    except Exception:
                        pass
            except Exception:
                pass
        
        # Parsează parametrii entității din bloc (doar proprietăți geometrice)
        def parse_entity_xdata(xdata_list, global_z, block_z_offset=0.0):
            height = 1.0  # Înălțimea extrudării
            name_str = ""  # Numele elementului
            solid_flag = 1  # Solid/void flag
            angle = 0.0  # Unghiul planului înclinat
            rotate90 = False  # Rotația cu 90° în jurul primului segment
            opening_area_formula = ""  # Formula pentru Opening_area (pentru IfcSpace)
            z_relative = 0.0  # Z relativ din XDATA
            
            for code, value in xdata_list:
                if code == 1000:
                    sval = str(value)
                    if sval.startswith("height:"):
                        try:
                            height = float(sval.split(":")[1])
                        except Exception:
                            pass
                    elif sval.startswith("z:"):
                        try:
                            z_relative = float(sval.split(":")[1])
                        except Exception:
                            pass
                    elif sval.startswith("Name:"):
                        name_str = sval.split(":", 1)[1].strip()
                    elif sval.startswith("solid:"):
                        try:
                            solid_flag = int(sval.split(":")[1])
                        except Exception:
                            pass
                    elif sval.startswith("angle:"):
                        try:
                            angle = float(sval.split(":")[1])
                        except Exception:
                            pass
                    elif sval.startswith("rotate90:"):
                        try:
                            rotate90 = bool(int(sval.split(":")[1]))
                        except Exception:
                            pass
                    elif sval.startswith("Opening_area:"):
                        opening_area_formula = sval.split(":", 1)[1].strip()
            
            # Calculează Z final pentru entitatea din bloc: global_z + block_z_offset + z_relative_entity
            z_final = global_z + block_z_offset + z_relative
            if abs(block_z_offset) > 1e-6 or abs(z_relative) > 1e-6:
                print(f"[DEBUG] Entity Z calculation: global_z={global_z:.3f} + block_z_offset={block_z_offset:.3f} + z_relative_entity={z_relative:.3f} = z_final={z_final:.3f}")
            return height, z_final, z_relative, name_str, solid_flag, angle, rotate90, opening_area_formula
        
        height, z_final_entity, z_relative_entity, name_str, solid_flag, angle, rotate90, opening_area_formula = parse_entity_xdata(
            entity_xdata.get("QCAD", []), global_z, z_relative
        )
        
        # Rotațiile finale sunt doar cele globale de pe bloc (nu mai adunăm cu elementele)
        final_rotate_x = rotate_x_global
        final_rotate_y = rotate_y_global
        
        # Generează numele mesh-ului: IfcType_ComponentLayer_Name
        entity_handle = getattr(entity, 'handle', f"block_{insert_handle}")
        entity_layer = getattr(entity, 'dxf', None)
        component_layer = getattr(entity_layer, 'layer', 'DefaultMaterial') if entity_layer else 'DefaultMaterial'
        
        # Materialul se bazează pe layer-ul componentei din bloc, nu pe layer-ul INSERT-ului
        rgba = get_material(component_layer)
        mesh_uuid = str(uuid.uuid4())
        
        # IfcType din layer-ul blocului (cu fallback pentru layer "0")
        ifc_type = layer if layer != "0" else "IfcWindow"  # Presupunem că blocurile pe layer 0 sunt ferestre
        
        # IfcType din layer-ul blocului, ComponentLayer din layer-ul entității, Name din XDATA
        key = (ifc_type, component_layer, name_str)
        mesh_name_count[key] = mesh_name_count.get(key, 0) + 1
        if name_str:
            mesh_name = f"{ifc_type}_{component_layer}_{name_str}_{mesh_name_count[key]}"
        else:
            mesh_name = f"{ifc_type}_{component_layer}_{mesh_name_count[key]}"
        
        # Procesează geometria entității
        mesh = None
        points = []
        
        if ent_type == "LWPOLYLINE":
            points = lwpolyline_to_points(entity, 16)
            closed = getattr(entity, "closed", False)
            
            if closed and len(points) >= 3:
                poly = Polygon(points)
                if poly.is_valid and poly.area > 0:
                    # Folosește formele spațiale dacă avem cercuri de control
                    if control_points and len(control_points) > 0:
                        print(f"[DEBUG] Creeaza mesh spatial in bloc cu {len(control_points)} cercuri de control")
                        mesh = create_spatial_mesh_from_contour(points, control_points, height)
                    elif rotate90:
                        print(f"[DEBUG] Creeaza mesh 90° rotit in bloc")
                        mesh = create_rotated_90_mesh(points, height)
                    elif abs(angle) > 1e-6:
                        mesh = create_angle_based_mesh(points, height, angle)
                    else:
                        mesh = extrude_polygon(poly, height)
                    
                    if mesh is not None:
                        # NOUA ORDINEA TRANSFORMĂRILOR:
                        # 1. Scalare la origine (0,0,0)
                        if abs(scale_x - 1.0) > 1e-6 or abs(scale_y - 1.0) > 1e-6 or abs(scale_z - 1.0) > 1e-6:
                            scale_matrix = np.diag([scale_x, scale_y, scale_z, 1.0])
                            mesh.apply_transform(scale_matrix)
                            print(f"[DEBUG] Applied scaling: X={scale_x:.3f}, Y={scale_y:.3f}, Z={scale_z:.3f}")

                        # 2. Rotația blocului în jurul axei Z la origine (0,0,0)
                        if abs(rotation_angle) > 1e-6:
                            z_rotation_matrix = trimesh.transformations.rotation_matrix(
                                np.radians(rotation_angle), [0, 0, 1], [0, 0, 0]
                            )
                            mesh.apply_transform(z_rotation_matrix)
                            print(f"[DEBUG] Applied Z rotation: {rotation_angle:.1f}° around origin")

                        # 3. Rotațiile XYZ la origine (0,0,0)
                        if abs(final_rotate_x) > 1e-6 or abs(final_rotate_y) > 1e-6:
                            mesh = apply_xyz_rotations_around_point(
                                mesh, final_rotate_x, final_rotate_y, 0.0, [0, 0, 0]
                            )

                        # 4. Translația la poziția finală în world space
                        z_position = z_final_entity
                        if "IfcColumn" in ifc_type:
                            z_position = global_z  # Coloanele încep de la nivelul global
                            print(f"[DEBUG] Coloana LWPOLYLINE {mesh_name}: z_final_entity={z_final_entity:.3f} -> z_position={global_z:.3f} (baza la nivel global)")

                        final_position = [insert_point.x, insert_point.y, z_position]
                        mesh.apply_translation(final_position)
                        print(f"[DEBUG] Applied final translation to: {final_position}")
                        
        elif ent_type == "POLYLINE":
            points = polyline_to_points(entity, 16)
            closed = getattr(entity, "is_closed", False)
            
            if closed and len(points) >= 3:
                poly = Polygon(points)
                if poly.is_valid and poly.area > 0:
                    # Extrudare
                    if rotate90:
                        print(f"[DEBUG] Creeaza mesh 90° rotit POLYLINE in bloc")
                        mesh = create_rotated_90_mesh(points, height)
                    elif abs(angle) > 1e-6:
                        mesh = create_angle_based_mesh(points, height, angle)
                    else:
                        mesh = extrude_polygon(poly, height)
                    
                    if mesh is not None:
                        # NOUA ORDINEA TRANSFORMĂRILOR:
                        # 1. Scalare la origine (0,0,0)
                        if abs(scale_x - 1.0) > 1e-6 or abs(scale_y - 1.0) > 1e-6 or abs(scale_z - 1.0) > 1e-6:
                            scale_matrix = np.diag([scale_x, scale_y, scale_z, 1.0])
                            mesh.apply_transform(scale_matrix)
                            print(f"[DEBUG] Applied scaling: X={scale_x:.3f}, Y={scale_y:.3f}, Z={scale_z:.3f}")

                        # 2. Rotația blocului în jurul axei Z la origine (0,0,0)
                        if abs(rotation_angle) > 1e-6:
                            z_rotation_matrix = trimesh.transformations.rotation_matrix(
                                np.radians(rotation_angle), [0, 0, 1], [0, 0, 0]
                            )
                            mesh.apply_transform(z_rotation_matrix)
                            print(f"[DEBUG] Applied Z rotation: {rotation_angle:.1f}° around origin")

                        # 3. Rotațiile XYZ la origine (0,0,0)
                        if abs(final_rotate_x) > 1e-6 or abs(final_rotate_y) > 1e-6:
                            mesh = apply_xyz_rotations_around_point(
                                mesh, final_rotate_x, final_rotate_y, 0.0, [0, 0, 0]
                            )

                        # 4. Translația la poziția finală în world space
                        z_position = z_final_entity
                        if "IfcColumn" in ifc_type:
                            z_position = global_z  # Coloanele încep de la nivelul global
                            print(f"[DEBUG] Coloana POLYLINE {mesh_name}: z_final_entity={z_final_entity:.3f} -> z_position={global_z:.3f} (baza la nivel global)")

                        final_position = [insert_point.x, insert_point.y, z_position]
                        mesh.apply_translation(final_position)
                        print(f"[DEBUG] Applied final translation to: {final_position}")
        
        elif ent_type == "CIRCLE" and hasattr(entity, "dxf"):
            center = (entity.dxf.center.x, entity.dxf.center.y)
            radius = entity.dxf.radius
            segments = 32
            points = [
                (
                    center[0] + np.cos(2 * np.pi * i / segments) * radius,
                    center[1] + np.sin(2 * np.pi * i / segments) * radius,
                )
                for i in range(segments)
            ]
            
            poly = Polygon(points)
            if poly.is_valid and poly.area > 0:
                # Extrudare
                if abs(angle) > 1e-6:
                    mesh = create_inclined_mesh(points, height, angle)
                else:
                    mesh = extrude_polygon(poly, height)
                
                if mesh is not None:
                    # NOUA ORDINEA TRANSFORMĂRILOR:
                    # 1. Scalare la origine (0,0,0)
                    if abs(scale_x - 1.0) > 1e-6 or abs(scale_y - 1.0) > 1e-6 or abs(scale_z - 1.0) > 1e-6:
                        scale_matrix = np.diag([scale_x, scale_y, scale_z, 1.0])
                        mesh.apply_transform(scale_matrix)
                        print(f"[DEBUG] Applied scaling: X={scale_x:.3f}, Y={scale_y:.3f}, Z={scale_z:.3f}")

                    # 2. Rotația blocului în jurul axei Z la origine (0,0,0)
                    if abs(rotation_angle) > 1e-6:
                        z_rotation_matrix = trimesh.transformations.rotation_matrix(
                            np.radians(rotation_angle), [0, 0, 1], [0, 0, 0]
                        )
                        mesh.apply_transform(z_rotation_matrix)
                        print(f"[DEBUG] Applied Z rotation: {rotation_angle:.1f}° around origin")

                    # 3. Rotațiile XYZ la origine (0,0,0)
                    if abs(final_rotate_x) > 1e-6 or abs(final_rotate_y) > 1e-6:
                        mesh = apply_xyz_rotations_around_point(
                            mesh, final_rotate_x, final_rotate_y, 0.0, [0, 0, 0]
                        )

                    # 4. Translația la poziția finală în world space
                    z_position = z_final_entity
                    if "IfcColumn" in ifc_type:
                        z_position = global_z  # Coloanele încep de la nivelul global
                        print(f"[DEBUG] Coloana CIRCLE {mesh_name}: z_final_entity={z_final_entity:.3f} -> z_position={global_z:.3f} (baza la nivel global)")

                    final_position = [insert_point.x, insert_point.y, z_position]
                    mesh.apply_translation(final_position)
                    print(f"[DEBUG] Applied final translation to: {final_position} (from z_final_entity={z_final_entity:.3f})")
        
        # Adaugă mesh-ul la lista corespunzătoare și mapping
        if mesh is not None:
            # Setează metadata
            mesh.metadata = {
                "uuid": mesh_uuid,
                "name": mesh_name,
                "dxf_handle": entity_handle,
                "layer": component_layer,  # Layer-ul componentei pentru material
                "role": 0 if solid_flag == 0 else 1  # 0 = void, 1 = solid
            }
            
            # Setează culorile pe baza materialului componentei (NU pe layer-ul blocului)
            color = rgba[:3]
            alpha = rgba[3]
            rgba_float = np.array(color + [alpha], dtype=np.float32)
            mesh.visual.vertex_colors = np.tile(rgba_float, (len(mesh.vertices), 1))
            
            # Creează material cu nume descriptiv pentru identificare în Godot
            material_name = f"Material_{component_layer}_{mesh_name}"
            
            mesh.visual.material = trimesh.visual.material.PBRMaterial(
                name=material_name,  # Nume descriptiv cu layer și mesh name
                baseColorFactor=[color[0], color[1], color[2], alpha],  # Culoare directă în material
                vertex_color=True,
                alphaMode="BLEND" if alpha < 1.0 else "OPAQUE"
            )
            
            # Stochează informații despre material în metadata pentru persistență
            mesh.metadata["material_color"] = color
            mesh.metadata["material_alpha"] = alpha
            mesh.metadata["material_rgba"] = rgba_float
            
            print(f"[DEBUG] Block mesh colors: {mesh_name} | component_layer={component_layer} | block_layer={layer} | color={color} alpha={alpha}")
            print(f"[DEBUG] Material source: component ({component_layer}) NOT block ({layer})")
            
            # Calculează proprietățile geometrice
            if len(points) >= 3:
                segment_lengths = [
                    np.linalg.norm(np.array(points[i]) - np.array(points[(i+1)%len(points)])) 
                    for i in range(len(points))
                ]
                perimeter = float(np.sum(segment_lengths))
                area = float(Polygon(points).area) if len(points) >= 3 else 0.0
                lateral_area = perimeter * height
                volume = area * height
                
                # Pentru IfcSpace, scade Opening_area din lateral_area dacă este specificată
                if ifc_type == "IfcSpace" and opening_area_formula:
                    opening_area_value = evaluate_math_formula(opening_area_formula)
                    if opening_area_value > 0:
                        lateral_area = max(0.0, lateral_area - opening_area_value)
                        print(f"[DEBUG] IfcSpace {mesh_name}: lateral_area adjusted with Opening_area={opening_area_value:.2f}, final lateral_area={lateral_area:.2f}")
            else:
                segment_lengths = []
                perimeter = 0.0
                area = 0.0
                lateral_area = 0.0
                volume = 0.0
            
            # Adaugă la mapping
            mapping_entry = {
                "dxf_handle": entity_handle,
                "mesh_name": mesh_name,
                "uuid": mesh_uuid,
                "role": 0 if solid_flag == 0 else 1,
                "solid_flag": solid_flag,
                "layer": component_layer,  # Layer-ul componentei pentru material (IMPORTANT!)
                "ifc_type": ifc_type,  # IfcType din layer-ul blocului (IfcWindow, IfcDoor, etc.)
                "component_layer": component_layer,  # Layer-ul componentei pentru material
                "material_layer": component_layer,  # Layer-ul pentru maparea materialului
                "block_name": f"From_{insert_handle}",  # Referință la blocul părinte
                "insert_position": {  # Poziția world a blocului
                    "x": float(insert_point.x),
                    "y": float(insert_point.y),
                    "z": z_final  # Z final calculat (global_z + z_relative)
                },
                "z_relative": z_relative,  # Z relativ din XDATA
                "global_z": global_z,      # Z global din numele fișierului
                "z_list": [global_z, z_final_entity],  # Lista cu Z global și Z final pentru componentă
                "component_name": name_str,  # Numele componentei din XDATA
                "angle": angle,  # Parametri de pe elementul din bloc
                "height": height,  # Parametri de pe elementul din bloc (grosimea)
                "rotate_x": final_rotate_x,  # Rotații globale de pe bloc
                "rotate_y": final_rotate_y,  # Rotații globale de pe bloc
                "segment_lengths": segment_lengths,
                "perimeter": perimeter,
                "area": area,
                "lateral_area": lateral_area,
                "volume": volume,
                "vertices": [[float(p[0]), float(p[1])] for p in points],
                "is_cut_by": []
            }
            
            # Nu adăugăm mapping-ul aici - se va adăuga după procesarea boolean
            
            # Colectează mesh-urile pentru procesare boolean în cadrul blocului
            mesh.metadata["solid_flag"] = solid_flag
            mesh.metadata["component_layer"] = component_layer
            mesh.metadata["mapping_entry"] = mapping_entry
            
            if solid_flag == 0:
                print(f"[DEBUG] Block void: {mesh_name} | IfcType={ifc_type} | Material={component_layer} | rotate_x={final_rotate_x:.1f}°, rotate_y={final_rotate_y:.1f}°")
            else:
                print(f"[DEBUG] Block solid: {mesh_name} | IfcType={ifc_type} | Material={component_layer} | rotate_x={final_rotate_x:.1f}°, rotate_y={final_rotate_y:.1f}°")
            
            # Adaugă la lista temporară pentru procesare în bloc
            if not hasattr(process_block_geometry, '_block_meshes'):
                process_block_geometry._block_meshes = []
            process_block_geometry._block_meshes.append(mesh)
    
    # Procesează operațiile boolean în cadrul blocului
    if hasattr(process_block_geometry, '_block_meshes'):
        block_meshes = process_block_geometry._block_meshes
        process_block_geometry._block_meshes = []  # Reset pentru următorul bloc
        
        # Separă solid și void mesh-urile
        block_solids = []
        block_voids = []
        
        for mesh in block_meshes:
            mesh_name = mesh.metadata.get("name", "unknown")
            component_layer = mesh.metadata.get("component_layer", "unknown")
            solid_flag = mesh.metadata.get("solid_flag", 1)
            
            if solid_flag == 0:
                block_voids.append(mesh)
                print(f"[DEBUG] Block void: {mesh_name} on layer {component_layer}")
            else:
                block_solids.append(mesh)
                print(f"[DEBUG] Block solid: {mesh_name} on layer {component_layer}")
        
        print(f"[DEBUG] Block boolean processing: {len(block_solids)} solids, {len(block_voids)} voids")
        
        # Aplică operațiile boolean între componentele blocului
        final_block_meshes = []
        
        for solid_mesh in block_solids:
            current_mesh = solid_mesh
            solid_uuid = solid_mesh.metadata.get("uuid")
            solid_layer = solid_mesh.metadata.get("component_layer", "")
            cutting_voids = []
            
            # Aplică doar void-urile compatibile la acest solid
            for void_mesh in block_voids:
                void_uuid = void_mesh.metadata.get("uuid")
                void_layer = void_mesh.metadata.get("component_layer", "")
                
                # Logica de compatibilitate: void-urile de lemn taie doar solidurile de lemn
                # Panourile de sticlă (glass) nu sunt tăiate de void-urile de lemn (wood)
                compatible = False
                if void_layer == "wood" and solid_layer == "wood":
                    compatible = True  # Void-urile de lemn taie rama de lemn
                elif void_layer == solid_layer:
                    compatible = True  # Void-urile taie același material
                # Panourile de sticlă rămân intacte față de void-urile de lemn
                
                if not compatible:
                    print(f"[DEBUG] Skipping incompatible void: {void_layer} void won't cut {solid_layer} solid")
                    continue
                
                try:
                    # Verifică intersecția bounding box
                    bb_intersect = not (
                        current_mesh.bounds[1][0] < void_mesh.bounds[0][0] or
                        current_mesh.bounds[0][0] > void_mesh.bounds[1][0] or
                        current_mesh.bounds[1][1] < void_mesh.bounds[0][1] or
                        current_mesh.bounds[0][1] > void_mesh.bounds[1][1] or
                        current_mesh.bounds[1][2] < void_mesh.bounds[0][2] or
                        current_mesh.bounds[0][2] > void_mesh.bounds[1][2]
                    )
                    
                    if bb_intersect:
                        try:
                            # Testează dacă se intersectează efectiv
                            intersection = current_mesh.intersection(void_mesh)
                            if intersection and hasattr(intersection, 'volume') and intersection.volume > 1e-6:
                                # Aplică operația boolean difference
                                diff_result = current_mesh.difference(void_mesh)
                                if diff_result and hasattr(diff_result, 'vertices') and len(diff_result.vertices) > 0:
                                    # Păstrează metadata originală
                                    diff_result.metadata = dict(current_mesh.metadata)
                                    
                                    # Păstrează proprietățile vizuale (material și culori) din metadata
                                    if "material_rgba" in current_mesh.metadata:
                                        # Recuperează culorile originale din metadata
                                        original_rgba = current_mesh.metadata["material_rgba"]
                                        original_color = current_mesh.metadata["material_color"]
                                        original_alpha = current_mesh.metadata["material_alpha"]
                                        
                                        # Re-aplică materialul la mesh-ul rezultat
                                        if len(diff_result.vertices) > 0:
                                            diff_result.visual.vertex_colors = np.tile(original_rgba, (len(diff_result.vertices), 1))
                                            diff_result.visual.material = trimesh.visual.material.PBRMaterial(
                                                baseColorFactor=[1.0, 1.0, 1.0, original_alpha],
                                                vertex_color=True,
                                                alphaMode="BLEND" if original_alpha < 1.0 else "OPAQUE"
                                            )
                                            
                                            # Păstrează informațiile despre material în noul mesh
                                            diff_result.metadata["material_color"] = original_color
                                            diff_result.metadata["material_alpha"] = original_alpha
                                            diff_result.metadata["material_rgba"] = original_rgba
                                            
                                            print(f"[DEBUG] Material restored after boolean: {diff_result.metadata.get('layer', 'unknown')} - color={original_color}")
                                    else:
                                        print(f"[DEBUG] Warning: No material metadata found for {current_mesh.metadata.get('name', 'unknown')}")
                                    
                                    current_mesh = diff_result
                                    cutting_voids.append(void_uuid)
                                    print(f"[DEBUG] Block void {void_uuid} cut solid {solid_uuid} - preserved material: {current_mesh.metadata.get('layer', 'unknown')}")
                                else:
                                    print(f"[DEBUG] Block void {void_uuid} completely removed solid {solid_uuid}")
                                    current_mesh = None
                                    break
                        except Exception as ex:
                            print(f"[DEBUG] Block boolean operation failed: {ex}")
                except Exception as ex:
                    print(f"[DEBUG] Block bounds check failed: {ex}")
            
            # Adaugă mesh-ul final dacă nu a fost complet eliminat
            if current_mesh is not None:
                # Actualizează mapping-ul
                mapping_entry = current_mesh.metadata.get("mapping_entry")
                if mapping_entry:
                    mapping_entry["is_cut_by"] = cutting_voids
                    # Recalculează volumul după operațiile boolean
                    if hasattr(current_mesh, 'volume') and current_mesh.volume > 0:
                        mapping_entry["volume"] = float(current_mesh.volume)
                        print(f"[DEBUG] Block volume updated after boolean: {mapping_entry['mesh_name']} = {current_mesh.volume:.3f}m³")
                    mapping.append(mapping_entry)
                
                final_block_meshes.append(current_mesh)
                print(f"[DEBUG] Block solid processed: {current_mesh.metadata.get('name')} on layer {solid_layer} - cut by {len(cutting_voids)} voids")
            else:
                print(f"[DEBUG] Block solid completely removed: {solid_mesh.metadata.get('name')} on layer {solid_layer}")
        
        # Adaugă și mesh-urile void separate (pentru debug/vizualizare)
        for void_mesh in block_voids:
            mapping_entry = void_mesh.metadata.get("mapping_entry")
            if mapping_entry:
                mapping.append(mapping_entry)
            # Nu adăugăm void-urile la solids - ele doar taie
        
        # Verifică dacă blocul poate tăia solidele existente
        block_cutting_voids = []
        
        # Dacă blocul întreg este void (solid:0), toate mesh-urile sale devin cutting voids
        if block_is_void:
            # Toate mesh-urile finale din bloc devin cutting voids
            for mesh in final_block_meshes:
                block_cutting_voids.append(mesh)
                print(f"[DEBUG] Block as VOID: {mesh.metadata.get('name')} will cut IfcWall/IfcCovering")
        else:
            # Logica originală: doar void-urile individuale cu rotații XYZ
            for void_mesh in block_voids:
                # Verifică dacă void-ul are rotații XYZ și poate tăia IfcWall/IfcCovering
                has_xyz_rotations = (abs(final_rotate_x) > 1e-6 or abs(final_rotate_y) > 1e-6)
                if has_xyz_rotations and void_mesh.metadata.get("solid_flag", 1) == 0:
                    block_cutting_voids.append(void_mesh)
                    print(f"[DEBUG] Block cutting void identified: {void_mesh.metadata.get('name')} with XYZ rotations")
        
        # Aplică void-urile blocului la solidele existente de tip IfcWall și IfcCovering
        if block_cutting_voids:
            print(f"[DEBUG] Applying {len(block_cutting_voids)} block cutting voids to existing solids")
            
            # Creează o copie a listei de solide pentru iterare sigură
            solids_to_process = list(solids)
            
            for i, existing_solid in enumerate(solids_to_process):
                # Verifică dacă solidul este de tip IfcWall sau IfcCovering
                ifc_type = existing_solid.metadata.get("ifc_type", "")
                if ifc_type not in ["IfcWall", "IfcCovering"]:
                    continue
                
                current_mesh = existing_solid
                solid_uuid = current_mesh.metadata.get("uuid")
                cutting_voids = []
                
                # Aplică fiecare void de bloc la acest solid
                for void_mesh in block_cutting_voids:
                    void_uuid = void_mesh.metadata.get("uuid")
                    try:
                        # Verifică intersecția bounding box
                        bb_intersect = not (
                            current_mesh.bounds[1][0] < void_mesh.bounds[0][0] or
                            current_mesh.bounds[0][0] > void_mesh.bounds[1][0] or
                            current_mesh.bounds[1][1] < void_mesh.bounds[0][1] or
                            current_mesh.bounds[0][1] > void_mesh.bounds[1][1] or
                            current_mesh.bounds[1][2] < void_mesh.bounds[0][2] or
                            current_mesh.bounds[0][2] > void_mesh.bounds[1][2]
                        )
                        
                        if bb_intersect:
                            try:
                                # Testează dacă se intersectează efectiv
                                intersection = current_mesh.intersection(void_mesh)
                                if intersection and hasattr(intersection, 'volume') and intersection.volume > 1e-6:
                                    # Aplică operația boolean difference
                                    diff_result = current_mesh.difference(void_mesh)
                                    if diff_result and hasattr(diff_result, 'vertices') and len(diff_result.vertices) > 0:
                                        # Păstrează metadata originală
                                        diff_result.metadata = dict(current_mesh.metadata)
                                        current_mesh = diff_result
                                        cutting_voids.append(void_uuid)
                                        print(f"[DEBUG] Block void {void_uuid} cut existing {ifc_type} solid {solid_uuid}")
                                    else:
                                        print(f"[DEBUG] Block void {void_uuid} completely removed existing {ifc_type} solid {solid_uuid}")
                                        current_mesh = None
                                        break
                            except Exception as ex:
                                print(f"[DEBUG] Block to existing solid boolean operation failed: {ex}")
                    except Exception as ex:
                        print(f"[DEBUG] Block to existing solid bounds check failed: {ex}")
                
                # Actualizează solidul în lista principală
                if current_mesh is not None:
                    # Actualizează mapping-ul dacă a fost modificat
                    if cutting_voids:
                        mapping_entry = current_mesh.metadata.get("mapping_entry")
                        if mapping_entry:
                            existing_cuts = mapping_entry.get("is_cut_by", [])
                            mapping_entry["is_cut_by"] = existing_cuts + cutting_voids
                            # Recalculează volumul după operațiile boolean cu bloc
                            if hasattr(current_mesh, 'volume') and current_mesh.volume > 0:
                                mapping_entry["volume"] = float(current_mesh.volume)
                                print(f"[DEBUG] Existing solid volume updated after block cutting: {mapping_entry['mesh_name']} = {current_mesh.volume:.3f}m³")
                    
                    # Înlocuiește solidul în lista principală
                    solids[solids.index(existing_solid)] = current_mesh
                elif existing_solid in solids:
                    # Elimină solidul complet eliminat
                    solids.remove(existing_solid)
                    print(f"[DEBUG] Existing {ifc_type} solid completely removed by block voids")

        # Re-aplică materialele la toate mesh-urile finale pentru a fi sigur
        for mesh in final_block_meshes:
            if "material_rgba" in mesh.metadata and len(mesh.vertices) > 0:
                rgba = mesh.metadata["material_rgba"]
                color = mesh.metadata["material_color"]
                alpha = mesh.metadata["material_alpha"]
                component_layer = mesh.metadata.get("layer", "unknown")
                
                # Re-aplică culorile și materialul
                mesh.visual.vertex_colors = np.tile(rgba, (len(mesh.vertices), 1))
                mesh.visual.material = trimesh.visual.material.PBRMaterial(
                    baseColorFactor=[1.0, 1.0, 1.0, alpha],
                    vertex_color=True,
                    alphaMode="BLEND" if alpha < 1.0 else "OPAQUE"
                )
                print(f"[DEBUG] Material re-applied: {mesh.metadata.get('name')} | layer={component_layer} | color={color}")

        # Adaugă mesh-urile finale ale blocului la listele globale
        # Dacă blocul este void global, nu-l adăugăm la solids (doar taie)
        if not block_is_void:
            for mesh in final_block_meshes:
                # Pentru mesh-urile care nu au fost tăiate, volumul din mapping este calculat din geometria 2D
                # dar pentru consistență, verificăm dacă mesh-ul 3D are volum diferit
                mapping_entry = mesh.metadata.get("mapping_entry")
                if mapping_entry and hasattr(mesh, 'volume') and mesh.volume > 0:
                    original_volume = mapping_entry.get("volume", 0.0)
                    if abs(mesh.volume - original_volume) > 1e-6:
                        mapping_entry["volume"] = float(mesh.volume)
                        print(f"[DEBUG] Block mesh volume corrected: {mapping_entry['mesh_name']} = {mesh.volume:.3f}m³")
                solids.append(mesh)
                print(f"[DEBUG] Final block mesh: {mesh.metadata.get('name')} | layer={mesh.metadata.get('layer', 'unknown')} | vertices={len(mesh.vertices)}")
        else:
            print(f"[DEBUG] Block is VOID - meshes not added to solids (only used for cutting)")
            # Adaugă totuși mapping entries pentru void-uri
            for mesh in final_block_meshes:
                mapping_entry = mesh.metadata.get("mapping_entry")
                if mapping_entry:
                    mapping_entry["role"] = 0  # Marchează ca void în mapping
                    mapping.append(mapping_entry)
        
        print(f"[DEBUG] Block processing complete: {len(final_block_meshes)} final meshes, {len(block_cutting_voids)} cutting voids applied to existing solids")

def apply_xyz_rotations_around_point(mesh, rotate_x, rotate_y, rotate_z, point):
    """
    Aplică rotații XYZ în jurul unui punct specific.
    
    Args:
        mesh: mesh-ul de rotit
        rotate_x, rotate_y, rotate_z: rotațiile în grade
        point: punctul în jurul căruia se fac rotațiile [x, y, z]
    
    Returns:
        mesh: mesh-ul rotit
    """
    if abs(rotate_x) < 1e-6 and abs(rotate_y) < 1e-6 and abs(rotate_z) < 1e-6:
        return mesh
    
    try:
        # Aplică rotațiile în ordinea: Z, Y, X
        if abs(rotate_z) > 1e-6:
            rotation_matrix = trimesh.transformations.rotation_matrix(
                np.radians(rotate_z), [0, 0, 1], point
            )
            mesh.apply_transform(rotation_matrix)
            print(f"[DEBUG] Applied Z rotation: {rotate_z:.1f}° around point {point}")
        
        if abs(rotate_y) > 1e-6:
            rotation_matrix = trimesh.transformations.rotation_matrix(
                np.radians(rotate_y), [0, 1, 0], point
            )
            mesh.apply_transform(rotation_matrix)
            print(f"[DEBUG] Applied Y rotation: {rotate_y:.1f}° around point {point}")
        
        if abs(rotate_x) > 1e-6:
            rotation_matrix = trimesh.transformations.rotation_matrix(
                np.radians(rotate_x), [1, 0, 0], point
            )
            mesh.apply_transform(rotation_matrix)
            print(f"[DEBUG] Applied X rotation: {rotate_x:.1f}° around point {point}")
        
        print(f"[DEBUG] Applied XYZ rotations around point: X={rotate_x:.1f}°, Y={rotate_y:.1f}°, Z={rotate_z:.1f}°")
        
    except Exception as e:
        print(f"[DEBUG] Error applying XYZ rotations around point: {e}")
    
    return mesh

# -----------------------------
# Export doar GLB
# -----------------------------
def export_scene(scene, out_path):
    if not out_path.lower().endswith(".glb"):
        out_path = os.path.splitext(out_path)[0] + ".glb"

    # Force material export - make sure all geometries have materials
    print(f"[DEBUG] Pre-export material check:")
    for name, geom in scene.geometry.items():
        if hasattr(geom.visual, 'material') and geom.visual.material is not None:
            print(f"  {name}: Material {geom.visual.material.name} | Color {geom.visual.material.baseColorFactor}")
        else:
            print(f"  {name}: NO MATERIAL - this will be lost in export!")

    glb_bytes = gltf.export_glb(scene)
    with open(out_path, "wb") as f:
        f.write(glb_bytes)

    print(f"[DEBUG] Exported GLB: {out_path}")

# -----------------------------
# Procesare Linii de Sectiune
# -----------------------------
def process_section_lines(doc, mapping):
    """
    Procesează liniile de pe layerul 'section' pentru a crea planuri de secțiune.
    
    Args:
        doc: documentul DXF
        mapping: lista de mapping unde vor fi adăugate datele de secțiune
    
    Returns:
        list: Lista cu dicționare ce conțin informații despre secțiuni
    """
    msp = doc.modelspace()
    section_data = []
    
    print("[DEBUG] Processing section lines...")
    
    for entity in msp:
        # Caută linii pe layerul 'section'
        if (entity.dxftype() == "LINE" and 
            getattr(entity.dxf, "layer", "").lower() == "section"):
            
            start_point = entity.dxf.start
            end_point = entity.dxf.end
            handle = getattr(entity.dxf, "handle", None)
            
            # Parsează XDATA pentru parametrii de secțiune
            section_depth = 5.0  # default
            lower_z = -10.0      # default
            upper_z = 20.0       # default
            section_id = f"section_{handle}" if handle else f"section_{len(section_data)}"
            
            if entity.has_xdata:
                try:
                    qcad_data = entity.get_xdata("QCAD")
                    if qcad_data:
                        for item in qcad_data:
                            if isinstance(item, tuple) and len(item) >= 2:
                                tag, value = item[0], item[1]
                                if tag == 1000:  # String data
                                    value_str = str(value).lower()
                                    if "section_depth:" in value_str:
                                        try:
                                            section_depth = float(value_str.split("section_depth:")[1].split()[0])
                                        except:
                                            pass
                                    elif "lower_z:" in value_str:
                                        try:
                                            lower_z = float(value_str.split("lower_z:")[1].split()[0])
                                        except:
                                            pass
                                    elif "upper_z:" in value_str:
                                        try:
                                            upper_z = float(value_str.split("upper_z:")[1].split()[0])
                                        except:
                                            pass
                except Exception as e:
                    print(f"[DEBUG] Error parsing section XDATA: {e}")
            
            # Calculează vectorul direcției în planul XY
            direction_vector = np.array([
                end_point.x - start_point.x,
                end_point.y - start_point.y,
                0.0
            ])
            
            # Calculează lungimea liniei (va fi folosită ca lățimea planului)
            line_length = np.linalg.norm(direction_vector)
            if line_length > 1e-6:
                direction_vector = direction_vector / line_length
            else:
                print(f"[WARNING] Section line has zero length, skipping")
                continue
            
            # Calculează normala planului (perpendiculară pe direcția liniei în planul XY)
            plane_normal = np.array([-direction_vector[1], direction_vector[0], 0.0])
            
            # Centrul planului (punctul mijloc al liniei)
            plane_center = np.array([
                (start_point.x + end_point.x) / 2.0,
                (start_point.y + end_point.y) / 2.0,
                (lower_z + upper_z) / 2.0
            ])
            
            # Creează mesh pentru planul de secțiune (gri transparent)
            plane_width = max(section_depth, 1.0)
            plane_height = upper_z - lower_z
            
            # Creează informațiile pentru planul de secțiune
            section_info = {
                "section_id": section_id,
                "start_point": [start_point.x, start_point.y, getattr(start_point, 'z', 0.0)],
                "end_point": [end_point.x, end_point.y, getattr(end_point, 'z', 0.0)],
                "plane_center": plane_center,
                "plane_normal": plane_normal,
                "section_depth": section_depth,
                "line_length": line_length,  # Lungimea reală a liniei din DXF
                "lower_z": lower_z,
                "upper_z": upper_z
            }
            section_data.append(section_info)
            
            # Adaugă la mapping
            section_uuid = str(uuid.uuid4())
            section_entry = {
                    "dxf_handle": handle,
                    "uuid": section_uuid,
                    "type": "section_plane",
                    "layer": "section",
                    "start_point": {
                        "x": float(start_point.x),
                        "y": float(start_point.y),
                        "z": float(start_point.z) if hasattr(start_point, 'z') else 0.0
                    },
                    "end_point": {
                        "x": float(end_point.x),
                        "y": float(end_point.y),
                        "z": float(end_point.z) if hasattr(end_point, 'z') else 0.0
                    },
                    "direction_vector": {
                        "x": float(direction_vector[0]),
                        "y": float(direction_vector[1]),
                        "z": float(direction_vector[2])
                    },
                    "plane_normal": {
                        "x": float(plane_normal[0]),
                        "y": float(plane_normal[1]),
                        "z": float(plane_normal[2])
                    },
                    "plane_center": {
                        "x": float(plane_center[0]),
                        "y": float(plane_center[1]),
                        "z": float(plane_center[2])
                    },
                    "section_depth": section_depth,
                    "lower_z": lower_z,
                    "upper_z": upper_z,
                    "material": {
                        "color": [0.7, 0.7, 0.7],  # Gri deschis
                        "alpha": 0.3               # Transparent
                    }
                }
            
            mapping.append(section_entry)
            print(f"[DEBUG] Added section plane: depth={section_depth}, z_range=({lower_z}, {upper_z}), line_length={line_length:.2f}")
    
    print(f"[DEBUG] Processed {len(section_data)} section planes")
    return section_data  # Return the section data, not the meshes

def create_section_plane_mesh(center, normal, width, height):
    """
    Creează un mesh pentru un plan de secțiune rectangular.
    
    Args:
        center: punctul central al planului
        normal: normala planului
        width: lățimea planului
        height: înălțimea planului
    
    Returns:
        trimesh.Trimesh: mesh-ul planului sau None în caz de eroare
    """
    try:
        # Calculează vectorii pentru orientarea planului
        if abs(normal[2]) < 0.9:  # Planul nu este orizontal
            up_vector = np.array([0, 0, 1])
        else:  # Planul este aproape orizontal
            up_vector = np.array([1, 0, 0])
        
        # Calculează vectorul dreapta (perpendicular pe normal și up)
        right_vector = np.cross(normal, up_vector)
        right_vector = right_vector / np.linalg.norm(right_vector)
        
        # Recalculează up_vector pentru a fi perpendicular pe normal și right
        up_vector = np.cross(right_vector, normal)
        up_vector = up_vector / np.linalg.norm(up_vector)
        
        # Calculează colțurile planului
        half_width = width / 2.0
        half_height = height / 2.0
        
        corners = [
            center - half_width * right_vector - half_height * up_vector,
            center + half_width * right_vector - half_height * up_vector,
            center + half_width * right_vector + half_height * up_vector,
            center - half_width * right_vector + half_height * up_vector
        ]
        
        # Creează mesh-ul double-faced (4 triunghiuri - 2 pe fiecare față)
        vertices = np.array(corners)
        faces = np.array([
            # Fața frontală (normala pozitivă)
            [0, 1, 2],  # Primul triunghi
            [0, 2, 3],  # Al doilea triunghi
            # Fața posterioară (normala negativă - ordinea inversă)
            [0, 3, 2],  # Al treilea triunghi (inversat)
            [0, 2, 1]   # Al patrulea triunghi (inversat)
        ])
        
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
        
        # Materialul va fi setat din layer_materials.json pentru layerul 'section'
        # Folosim culoarea implicită transparentă aici
        mesh.visual.face_colors = [180, 180, 180, 77]  # RGB + Alpha (0.3 * 255)
        
        return mesh
        
    except Exception as e:
        print(f"[ERROR] Failed to create section plane mesh: {e}")
        return None

# -----------------------------
# Conversie DXF → GLB
# -----------------------------
def dxf_to_gltf(dxf_path, out_path, arc_segments=16):
    print(f"[DEBUG] Start DXF to GLB: {dxf_path} -> {out_path}")
    start_time = time.time()

    # Extrage Z global din numele fișierului
    global_z = extract_global_z_from_filename(dxf_path)
    print(f"[DEBUG] Global Z level from filename: {global_z}")

    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    # Inițializează converterul IFC în background
    ifc_converter = None
    ifc_output_path = None
    if IFC_CONVERSION_AVAILABLE:
        try:
            # Determină numele proiectului din calea fișierului
            project_name = os.path.splitext(os.path.basename(dxf_path))[0]
            ifc_converter = create_background_converter(f"Project_{project_name}")
            ifc_output_path = os.path.splitext(out_path)[0] + "_auto.ifc"
            print(f"[DEBUG] IFC Background Converter initialized: {ifc_output_path}")
        except Exception as e:
            print(f"[WARNING] Could not initialize IFC converter: {e}")
            ifc_converter = None

    # Citește cercurile de control pentru formele spațiale
    control_points = read_control_circles(doc, layer="control", global_z=global_z)
    print(f"[DEBUG] Control circles loaded: {len(control_points)} with global_z={global_z}")

    solids = []
    voids = []
    mesh_name_count = {}
    mapping = []

    for idx, e in enumerate(msp):
        ent_type = e.dxftype()
        handle = getattr(e.dxf, "handle", None)
        layer = getattr(e.dxf, "layer", "default")
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
                        xdata[appid] = list(data)
                        print(f"[DEBUG] XDATA for {ent_type} handle={handle} appid={appid}: {xdata[appid]}")
                except Exception as ex:
                    print(f"[DEBUG] XDATA error for appid {appid}: {ex}")

        # Debug pentru toate entitățile, nu doar cele cu XDATA
        print(f"[DEBUG] Processing entity: {ent_type} handle={handle} layer={layer}")

        # Pentru blocurile INSERT, obține numele blocului
        block_name = ""
        if ent_type == "INSERT":
            block_name = getattr(e.dxf, "name", "")
            print(f"[DEBUG] INSERT block name: {block_name}")

        # IMPORTANT: Procesare Door/Window TOV TREBUIE să fie ÎNAINTE de IfcWindow metadata!
        # Procesare pentru blocurile Door/Window TOV (cu logica FOV din biblioteci)
        if ent_type == "INSERT" and DOOR_WINDOW_PROCESSOR_AVAILABLE and block_name.endswith('_TOV'):
            if process_door_window_block(doc, e, global_z, mesh_name_count, mapping, solids, voids, control_points):
                print(f"[DEBUG] Successfully processed Door/Window TOV: {block_name}")
                continue  # Nu procesăm blocul ca geometrie normală sau window metadata
            else:
                print(f"[DEBUG] Failed to process Door/Window TOV: {block_name}, falling back to normal processing")

        # Procesare specială pentru blocurile de ferestre (doar pentru metadata, NU pentru TOV!)
        if ent_type == "INSERT" and layer == "IfcWindow" and not block_name.endswith('_TOV'):
            insert_point = getattr(e.dxf, "insert", None)
            rotation_angle = getattr(e.dxf, "rotation", 0.0)  # Rotația în grade
            
            if insert_point and block_name:
                # Parsează XDATA pentru Z
                z_relative = 0.0  # Z relativ la global_z
                window_height = 1.2  # Înălțime implicită pentru ferestre
                window_name = block_name
                
                if e.has_xdata:
                    try:
                        appids = []
                        if hasattr(e, "get_xdata_appids"):
                            appids = e.get_xdata_appids()
                        if "QCAD" not in appids:
                            appids.append("QCAD")
                        
                        for appid in appids:
                            try:
                                xdata_qcad = e.get_xdata(appid)
                                if xdata_qcad:
                                    for code, value in xdata_qcad:
                                        if code == 1000:
                                            sval = str(value)
                                            if sval.startswith("z:"):
                                                try:
                                                    z_relative = float(sval.split(":")[1])
                                                except Exception:
                                                    pass
                                            elif sval.startswith("height:"):
                                                try:
                                                    window_height = float(sval.split(":")[1])
                                                except Exception:
                                                    pass
                                            elif sval.startswith("Name:"):
                                                window_name = sval.split(":", 1)[1].strip()
                                    break  # După ce găsim XDATA valid, ieșim
                            except Exception as ex:
                                print(f"[DEBUG] XDATA appid {appid} error: {ex}")
                    except Exception as ex:
                        print(f"[DEBUG] XDATA parsing error for window block: {ex}")
                
                # Calculează Z final pentru fereastră
                z_final = global_z + z_relative
                
                # Creează entry pentru mapping
                window_uuid = str(uuid.uuid4())
                window_entry = {
                    "dxf_handle": handle,
                    "block_name": block_name,
                    "window_name": window_name,
                    "uuid": window_uuid,
                    "type": "window_block",
                    "layer": layer,
                    "gltf_file": f"library/gltf library/Windows/{block_name}.gltf",
                    "position": {
                        "x": float(insert_point.x),
                        "y": float(insert_point.y), 
                        "z": z_final  # Z final calculat (global_z + z_relative)
                    },
                    "z_final": z_final,       # Z final calculat
                    "z_relative": z_relative, # Z relativ din XDATA
                    "global_z": global_z,     # Z global din numele fișierului
                    "rotation": {
                        "z": rotation_angle  # Rotația în jurul axei Z în grade
                    },
                    "scale": {
                        "x": 1.0,
                        "y": 1.0,
                        "z": 1.0
                    },
                    "height": window_height
                }
                
                mapping.append(window_entry)
                print(f"[DEBUG] Added window block: {block_name} at ({insert_point.x:.2f}, {insert_point.y:.2f}, {z_final:.2f}) global_z={global_z} + z_relative={z_relative} rotation={rotation_angle:.1f}°")
                continue  # Nu procesăm blocul ca geometrie normală

        # Procesare pentru blocurile cu geometrie (INSERT cu conținut solid)
        if ent_type == "INSERT" and layer != "IfcWindow":
            block_name = getattr(e.dxf, "name", "")
            insert_point = getattr(e.dxf, "insert", None)
            rotation_angle = getattr(e.dxf, "rotation", 0.0)  # Rotația în grade
            scale_x = getattr(e.dxf, "xscale", 1.0)
            scale_y = getattr(e.dxf, "yscale", 1.0)
            scale_z = getattr(e.dxf, "zscale", 1.0)
            
            if insert_point is not None and block_name:
                # Încearcă să găsească blocul în document
                try:
                    print(f"[DEBUG] Looking for block: {block_name}")
                    block_layout = doc.blocks.get(block_name)
                    if block_layout:
                        # Procesează geometria din bloc cu punctul de inserție ca origine pentru rotații
                        print(f"[DEBUG] Processing geometry block: {block_name} at ({insert_point.x:.2f}, {insert_point.y:.2f})")
                        process_block_geometry(
                            doc, block_layout, insert_point, rotation_angle, 
                            scale_x, scale_y, scale_z, layer, handle, 
                            xdata, mesh_name_count, mapping, solids, voids, control_points, global_z
                        )
                        continue  # Blocul a fost procesat, trecem la următoarea entitate
                    else:
                        print(f"[DEBUG] Block not found: {block_name}")
                except Exception as ex:
                    print(f"[DEBUG] Error processing block {block_name}: {ex}")
                    # Continuă cu procesarea normală dacă blocul nu poate fi procesat

        def parse_xdata_from_list(xdata_list, global_z):
            height = 1.0
            z_relative = 0.0  # Z relativ la global_z
            name_str = ""
            solid_flag = 1  # Implicit solid, doar dacă e explicit setat pe 0 devine void
            angle = 0.0  # Unghiul de rotație în grade (implicit 0)
            rotate90 = False  # Rotația cu 90° în jurul primului segment
            rotate_x = 0.0  # Rotația în jurul axei X în grade
            rotate_y = 0.0  # Rotația în jurul axei Y în grade
            opening_area_formula = ""  # Formula pentru Opening_area (pentru IfcSpace)
            for code, value in xdata_list:
                if code == 1000:
                    sval = str(value)
                    if sval.startswith("height:"):
                        try:
                            height = float(sval.split(":")[1])
                        except Exception:
                            pass
                    elif sval.startswith("z:"):
                        try:
                            z_relative = float(sval.split(":")[1])
                        except Exception:
                            pass
                    elif sval.startswith("Name:"):
                        name_str = sval.split(":", 1)[1].strip()
                    elif sval.startswith("solid:"):
                        try:
                            solid_flag = int(sval.split(":")[1])
                        except Exception:
                            pass
                    elif sval.startswith("angle:"):
                        try:
                            angle = float(sval.split(":")[1])
                        except Exception:
                            pass
                    elif sval.startswith("rotate90:"):
                        try:
                            rotate90 = bool(int(sval.split(":")[1]))
                        except Exception:
                            pass
                    elif sval.startswith("rotate_x:"):
                        try:
                            rotate_x = float(sval.split(":")[1])
                        except Exception:
                            pass
                    elif sval.startswith("rotate_y:"):
                        try:
                            rotate_y = float(sval.split(":")[1])
                        except Exception:
                            pass
                    elif sval.startswith("Opening_area:"):
                        opening_area_formula = sval.split(":", 1)[1].strip()
            
            # Calculează Z final: global_z + z_relative
            z_final = global_z + z_relative
            return height, z_final, z_relative, name_str, solid_flag, angle, rotate90, rotate_x, rotate_y, opening_area_formula

        height, z_final, z_relative, name_str, solid_flag, angle, rotate90, rotate_x, rotate_y, opening_area_formula = parse_xdata_from_list(xdata.get("QCAD", []), global_z)
        rgba = get_material(layer)
        color, alpha = rgba[:3], rgba[3]
        mesh, mesh_uuid = None, str(uuid.uuid4())

        key = (layer, name_str)
        mesh_name_count[key] = mesh_name_count.get(key, 0) + 1
        mesh_name = f"{layer}_{name_str}_{mesh_name_count[key]}" if name_str else f"{layer}_{mesh_name_count[key]}"
        
        # Determină rolul elementului: void dacă solid_flag=0, altfel solid
        is_void = (solid_flag == 0)

        poly = None
        points = []
        closed = False
        
        # Procesare LWPOLYLINE cu suport pentru arce și forme spațiale
        if ent_type == "LWPOLYLINE":
            points = lwpolyline_to_points(e, arc_segments)
            closed = getattr(e, "closed", False)
            if closed and len(points) >= 3:
                poly = Polygon(points)
                if poly.is_valid and poly.area > 0:
                    # Folosește formele spațiale dacă avem cercuri de control
                    if control_points and len(control_points) > 0:
                        print(f"[DEBUG] Creeaza mesh spatial cu {len(control_points)} cercuri de control")
                        mesh = create_spatial_mesh_from_contour(points, control_points, height)
                    elif rotate90:
                        # Rotație cu 90° în jurul primului segment
                        print(f"[DEBUG] Creeaza mesh 90° rotit cu normala fetei")
                        mesh = create_rotated_90_mesh(points, height)
                        if mesh is not None:
                            # Pentru coloane, z_final devine nivelul global
                            z_position = z_final
                            if "IfcColumn" in layer:
                                z_position = global_z  # Coloanele încep de la nivelul global
                                print(f"[DEBUG] Coloana direct LWPOLYLINE rotate90 {mesh_name}: z_final={z_final:.3f} -> z_position={global_z:.3f} (baza la nivel global)")
                            
                            mesh.apply_translation([0, 0, z_position])
                    elif abs(angle) > 1e-6:
                        # Creează mesh cu rotație și proiecție pe plan
                        mesh = create_angle_based_mesh(points, height, angle)
                    else:
                        # Mesh orizontal standard cu translație Z
                        mesh = extrude_polygon(poly, height)
                        if mesh is not None:
                            # Pentru coloane, z_final devine nivelul global
                            z_position = z_final
                            if "IfcColumn" in layer:
                                z_position = global_z  # Coloanele încep de la nivelul global
                                print(f"[DEBUG] Coloana direct LWPOLYLINE standard {mesh_name}: z_final={z_final:.3f} -> z_position={global_z:.3f} (baza la nivel global)")
                            
                            mesh.apply_translation([0, 0, z_position])
                    
                    # Aplică rotațiile suplimentare pe axele X și Y doar pentru mesh-urile non-spațiale
                    if mesh is not None and not (control_points and len(control_points) > 0):
                        if abs(rotate_x) > 1e-6 or abs(rotate_y) > 1e-6:
                            mesh = apply_xyz_rotations(mesh, rotate_x, rotate_y, 0.0)

        # Procesare POLYLINE cu suport pentru arce și forme spațiale
        elif ent_type == "POLYLINE":
            points = polyline_to_points(e, arc_segments)
            closed = getattr(e, "is_closed", False)
            if closed and len(points) >= 3:
                poly = Polygon(points)
                if poly.is_valid and poly.area > 0:
                    # Folosește formele spațiale dacă avem cercuri de control
                    if control_points and len(control_points) > 0:
                        print(f"[DEBUG] Creeaza mesh spatial POLYLINE cu {len(control_points)} cercuri de control")
                        mesh = create_spatial_mesh_from_contour(points, control_points, height)
                    elif rotate90:
                        # Rotație cu 90° în jurul primului segment
                        print(f"[DEBUG] Creeaza mesh 90° rotit POLYLINE cu normala fetei")
                        mesh = create_rotated_90_mesh(points, height)
                        if mesh is not None:
                            # Pentru coloane, z_final devine nivelul global
                            z_position = z_final
                            if "IfcColumn" in layer:
                                z_position = global_z  # Coloanele încep de la nivelul global
                                print(f"[DEBUG] Coloana direct POLYLINE rotate90 {mesh_name}: z_final={z_final:.3f} -> z_position={global_z:.3f} (baza la nivel global)")
                            
                            mesh.apply_translation([0, 0, z_position])
                    elif abs(angle) > 1e-6:
                        # Creează mesh cu rotație și proiecție pe plan
                        mesh = create_angle_based_mesh(points, height, angle)
                    else:
                        # Mesh orizontal standard cu translație Z
                        mesh = extrude_polygon(poly, height)
                        if mesh is not None:
                            # Pentru coloane, z_final devine nivelul global
                            z_position = z_final
                            if "IfcColumn" in layer:
                                z_position = global_z  # Coloanele încep de la nivelul global  
                                print(f"[DEBUG] Coloana direct POLYLINE standard {mesh_name}: z_final={z_final:.3f} -> z_position={global_z:.3f} (baza la nivel global)")
                            
                            mesh.apply_translation([0, 0, z_position])
                    
                    # Aplică rotațiile suplimentare pe axele X și Y doar pentru mesh-urile non-spațiale
                    if mesh is not None and not (control_points and len(control_points) > 0):
                        if abs(rotate_x) > 1e-6 or abs(rotate_y) > 1e-6:
                            mesh = apply_xyz_rotations(mesh, rotate_x, rotate_y, 0.0)

        # Procesare CIRCLE cu suport pentru forme spațiale (EXCLUDE cercurile de control)
        elif ent_type == "CIRCLE" and hasattr(e, "dxf") and layer != "control":
            center = (e.dxf.center.x, e.dxf.center.y)
            radius = e.dxf.radius
            segments = max(32, arc_segments * 2)  # Mai multe segmente pentru cercuri
            points = [
                (
                    center[0] + np.cos(2 * np.pi * i / segments) * radius,
                    center[1] + np.sin(2 * np.pi * i / segments) * radius,
                )
                for i in range(segments)
            ]
            closed = True
            poly = Polygon(points)
            if poly.is_valid and poly.area > 0:
                # Folosește formele spațiale dacă avem cercuri de control
                if control_points and len(control_points) > 0:
                    print(f"[DEBUG] Creeaza mesh spatial CIRCLE cu {len(control_points)} cercuri de control")
                    mesh = create_spatial_mesh_from_contour(points, control_points, height)
                elif abs(angle) > 1e-6:
                    # Creează mesh cu rotație și proiecție pe plan
                    mesh = create_angle_based_mesh(points, height, angle)
                else:
                    # Mesh orizontal standard cu translație Z
                    mesh = extrude_polygon(poly, height)
                    if mesh is not None:
                        # Pentru coloane, z_final devine nivelul global
                        z_position = z_final
                        if "IfcColumn" in layer:
                            z_position = global_z  # Coloanele încep de la nivelul global  
                            print(f"[DEBUG] Coloana direct CIRCLE standard {mesh_name}: z_final={z_final:.3f} -> z_position={global_z:.3f} (baza la nivel global)")
                        
                        mesh.apply_translation([0, 0, z_position])
                
                # Aplică rotațiile suplimentare pe axele X și Y doar pentru mesh-urile non-spațiale
                if mesh is not None and not (control_points and len(control_points) > 0):
                    if abs(rotate_x) > 1e-6 or abs(rotate_y) > 1e-6:
                        mesh = apply_xyz_rotations(mesh, rotate_x, rotate_y, 0.0)

        # Calculează proprietăți geometrice pentru mapping
        if closed and len(points) >= 3:
            segment_lengths = [np.linalg.norm(np.array(points[i]) - np.array(points[(i+1)%len(points)])) for i in range(len(points))]
            perimeter = float(np.sum(segment_lengths))
            area = float(poly.area) if poly else 0.0
            lateral_area = perimeter * height
            volume = area * height
        else:
            segment_lengths = []
            perimeter = 0.0
            area = 0.0
            lateral_area = 0.0
            volume = 0.0

        if mesh is not None:
            mesh.name = mesh_name

            mesh.metadata = {
                "uuid": mesh_uuid,
                "handle": handle,
                "layer": layer,
                "name": mesh_name,
                "color": color,
                "alpha": alpha,
                "solid_flag": solid_flag,
                "is_void": is_void,
                "angle": angle,
                "rotate_x": rotate_x,
                "rotate_y": rotate_y,
            }

            rgba_float = np.array(color + [alpha], dtype=np.float32)
            mesh.visual.vertex_colors = np.tile(rgba_float, (len(mesh.vertices), 1))
            
            # Creează material cu nume descriptiv pentru identificare în Godot
            material_name = f"Material_{layer}_{mesh_name}"
            
            mesh.visual.material = trimesh.visual.material.PBRMaterial(
                name=material_name,  # Nume descriptiv cu layer și mesh name
                baseColorFactor=[color[0], color[1], color[2], alpha],  # Culoare directă în material
                vertex_color=True,
                alphaMode="BLEND" if alpha < 1.0 else "OPAQUE"
            )

            # Stochează informații despre material în metadata pentru persistență
            mesh.metadata["material_color"] = color
            mesh.metadata["material_alpha"] = alpha
            mesh.metadata["material_rgba"] = rgba_float

            print(f"[DEBUG] Export mesh: {mesh_name} | color={color} alpha={alpha} | vertex_colors.shape={mesh.visual.vertex_colors.shape if hasattr(mesh.visual, 'vertex_colors') else 'N/A'} | height={height} z_final={z_final} (global_z={global_z} + z_relative={z_relative})")

            # Pentru IfcSpace, scade Opening_area din lateral_area dacă este specificată
            if layer == "IfcSpace" and opening_area_formula:
                opening_area_value = evaluate_math_formula(opening_area_formula)
                if opening_area_value > 0:
                    lateral_area = max(0.0, lateral_area - opening_area_value)
                    print(f"[DEBUG] IfcSpace {mesh_name}: lateral_area adjusted with Opening_area={opening_area_value:.2f}, final lateral_area={lateral_area:.2f}")

            entry = {
                "dxf_handle": handle,
                "mesh_name": mesh_name,
                "uuid": mesh_uuid,
                "role": -1 if is_void else 1,
                "solid_flag": solid_flag,
                "layer": layer,
                "angle": angle,
                "rotate_x": rotate_x,
                "rotate_y": rotate_y,
                "z_final": z_final,         # Z final calculat (global_z + z_relative)
                "z_relative": z_relative,   # Z relativ din XDATA
                "global_z": global_z,       # Z global din numele fișierului
                "segment_lengths": segment_lengths,
                "perimeter": perimeter,
                "area": area,
                "lateral_area": lateral_area,
                "volume": volume,
                "vertices": [list(map(float, pt)) for pt in points] if points else [],
                "is_cut_by": []
            }
            mapping.append(entry)

            if is_void:
                voids.append(mesh)
            else:
                solids.append(mesh)

    uuid_to_entry = {entry["uuid"]: entry for entry in mapping}

    # Separează voidurile și solidele pentru aplicarea logicii globale
    global_voids = []
    layer_voids_by_layer = {}  # Pentru voidurile cu solid_flag=0 (per layer)
    all_solids = []
    
    for mesh in solids + voids:
        # Handle both direct mesh objects and mesh dictionaries (from TOV processing)
        if isinstance(mesh, dict):
            actual_mesh = mesh["mesh"]
            layer = mesh.get("layer", "default")
            is_void = not mesh.get("solid", True)  # solid=False means it's a void
        else:
            actual_mesh = mesh
            layer = mesh.metadata.get("layer", "default")
            is_void = mesh.metadata.get("is_void", False)
        
        if is_void:
            if layer == "void":
                # Layerul "void" taie toate geometriile
                global_voids.append(actual_mesh)
            else:
                # Voiduri pe alte layere (solid_flag=0) taie doar același layer
                if layer not in layer_voids_by_layer:
                    layer_voids_by_layer[layer] = []
                layer_voids_by_layer[layer].append(actual_mesh)
        else:
            all_solids.append(actual_mesh)

    print(f"[DEBUG] Global voids (layer 'void'): {len(global_voids)}")
    print(f"[DEBUG] Layer-specific voids: {sum(len(v) for v in layer_voids_by_layer.values())}")
    print(f"[DEBUG] All solids: {len(all_solids)}")

    new_solids = []
    
    # Prima etapă: Aplică voidurile globale (layerul "void") la toate solidele
    if global_voids:
        global_void_union = trimesh.util.concatenate(global_voids)
        print("[DEBUG] Applying global voids to all solids...")
        
        for mesh in all_solids:
            solid_uuid = mesh.metadata.get("uuid")
            cutting_voids = []
            
            # Verifică care voiduri globale taie acest solid
            for void_mesh in global_voids:
                void_uuid = void_mesh.metadata.get("uuid")
                try:
                    # Verificare prin intersecția bounding box-urilor
                    bb_intersect = not (
                        mesh.bounds[1][0] < void_mesh.bounds[0][0] or
                        mesh.bounds[0][0] > void_mesh.bounds[1][0] or
                        mesh.bounds[1][1] < void_mesh.bounds[0][1] or
                        mesh.bounds[0][1] > void_mesh.bounds[1][1] or
                        mesh.bounds[1][2] < void_mesh.bounds[0][2] or
                        mesh.bounds[0][2] > void_mesh.bounds[1][2]
                    )
                    
                    if bb_intersect:
                        try:
                            intersection = mesh.intersection(void_mesh)
                            if intersection and hasattr(intersection, 'volume') and intersection.volume > 1e-6:
                                cutting_voids.append(void_uuid)
                                solid_layer = mesh.metadata.get("layer", "default")
                                print(f"[DEBUG] Global void {void_uuid} cuts solid {solid_uuid} (layer {solid_layer})")
                        except Exception as ex:
                            print(f"[DEBUG] Global intersection test failed: {ex}")
                except Exception as ex:
                    print(f"[DEBUG] Global bounds check failed: {ex}")
            
            # Aplică tăierea cu voidurile globale
            try:
                diff = mesh.difference(global_void_union)
                if diff:
                    if isinstance(diff, list):
                        for dmesh in diff:
                            dmesh.metadata = dict(mesh.metadata) if hasattr(mesh, 'metadata') else {}
                            new_solids.append(dmesh)
                    else:
                        diff.metadata = dict(mesh.metadata) if hasattr(mesh, 'metadata') else {}
                        new_solids.append(diff)
                        # Recalculează volumul după tăierea cu voidurile globale
                        if hasattr(diff, 'volume') and diff.volume > 0 and solid_uuid in uuid_to_entry:
                            uuid_to_entry[solid_uuid]["volume"] = float(diff.volume)
                            print(f"[DEBUG] Volume updated after global voids: {uuid_to_entry[solid_uuid]['mesh_name']} = {diff.volume:.3f}m³")
                else:
                    new_solids.append(mesh)
            except Exception as ex:
                print(f"[DEBUG] Global boolean difference failed for mesh {solid_uuid}: {ex}")
                new_solids.append(mesh)
            
            # Actualizează mapping-ul cu voidurile globale
            if solid_uuid in uuid_to_entry:
                existing_cuts = uuid_to_entry[solid_uuid].get("is_cut_by", [])
                uuid_to_entry[solid_uuid]["is_cut_by"] = existing_cuts + cutting_voids
    else:
        # Nu există voiduri globale, copiază solidele
        new_solids = all_solids.copy()

    # A doua etapă: Aplică voidurile specifice pe layer (solid_flag=0)
    final_solids = []
    solids_by_layer = {}
    
    # Grupează solidele rezultate pe layere
    for mesh in new_solids:
        layer = mesh.metadata.get("layer", "default")
        if layer not in solids_by_layer:
            solids_by_layer[layer] = []
        solids_by_layer[layer].append(mesh)
    
    # Logică specială pentru IfcWindow voids
    window_voids = layer_voids_by_layer.get("IfcWindow", [])
    if window_voids:
        print(f"[DEBUG] Applying IfcWindow voids to IfcWall and IfcCovering: {len(window_voids)} voids")
        window_void_union = trimesh.util.concatenate(window_voids)
        
        # IfcWindow voids taie doar IfcWall și IfcCovering
        target_layers = ["IfcWall", "IfcCovering"]
        for target_layer in target_layers:
            if target_layer in solids_by_layer:
                layer_solids = solids_by_layer[target_layer]
                processed_solids = []
                
                for mesh in layer_solids:
                    solid_uuid = mesh.metadata.get("uuid")
                    cutting_voids = []
                    
                    # Verifică care window voids taie acest solid
                    for void_mesh in window_voids:
                        void_uuid = void_mesh.metadata.get("uuid")
                        try:
                            bb_intersect = not (
                                mesh.bounds[1][0] < void_mesh.bounds[0][0] or
                                mesh.bounds[0][0] > void_mesh.bounds[1][0] or
                                mesh.bounds[1][1] < void_mesh.bounds[0][1] or
                                mesh.bounds[0][1] > void_mesh.bounds[1][1] or
                                mesh.bounds[1][2] < void_mesh.bounds[0][2] or
                                mesh.bounds[0][2] > void_mesh.bounds[1][2]
                            )
                            
                            if bb_intersect:
                                try:
                                    intersection = mesh.intersection(void_mesh)
                                    if intersection and hasattr(intersection, 'volume') and intersection.volume > 1e-6:
                                        cutting_voids.append(void_uuid)
                                        print(f"[DEBUG] IfcWindow void {void_uuid} cuts {target_layer} solid {solid_uuid}")
                                except Exception as ex:
                                    print(f"[DEBUG] IfcWindow intersection test failed: {ex}")
                        except Exception as ex:
                            print(f"[DEBUG] IfcWindow bounds check failed: {ex}")
                    
                    # Aplică tăierea cu window voids
                    try:
                        diff = mesh.difference(window_void_union)
                        if diff:
                            if isinstance(diff, list):
                                for dmesh in diff:
                                    dmesh.metadata = dict(mesh.metadata) if hasattr(mesh, 'metadata') else {}
                                    processed_solids.append(dmesh)
                            else:
                                diff.metadata = dict(mesh.metadata) if hasattr(mesh, 'metadata') else {}
                                processed_solids.append(diff)
                                # Recalculează volumul după tăierea cu ferestrele
                                if hasattr(diff, 'volume') and diff.volume > 0 and solid_uuid in uuid_to_entry:
                                    uuid_to_entry[solid_uuid]["volume"] = float(diff.volume)
                                    print(f"[DEBUG] Volume updated after IfcWindow cutting: {uuid_to_entry[solid_uuid]['mesh_name']} = {diff.volume:.3f}m³")
                        else:
                            processed_solids.append(mesh)
                    except Exception as ex:
                        print(f"[DEBUG] IfcWindow boolean difference failed for mesh {solid_uuid}: {ex}")
                        processed_solids.append(mesh)
                    
                    # Actualizează mapping-ul cu window voids
                    if solid_uuid in uuid_to_entry:
                        existing_cuts = uuid_to_entry[solid_uuid].get("is_cut_by", [])
                        uuid_to_entry[solid_uuid]["is_cut_by"] = existing_cuts + cutting_voids
                
                # Înlocuiește solidele procesate
                solids_by_layer[target_layer] = processed_solids
    
    # Aplică voidurile normale pe layer (exclude IfcWindow care a fost deja procesat)
    for layer, layer_solids in solids_by_layer.items():
        if layer in layer_voids_by_layer and layer != "IfcWindow":
            layer_voids = layer_voids_by_layer[layer]
            layer_void_union = trimesh.util.concatenate(layer_voids)
            
            print(f"[DEBUG] Applying layer-specific voids for layer '{layer}': {len(layer_voids)} voids")
            
            processed_solids = []
            for mesh in layer_solids:
                solid_uuid = mesh.metadata.get("uuid")
                cutting_voids = []
                
                # Verifică care voiduri din același layer taie acest solid
                for void_mesh in layer_voids:
                    void_uuid = void_mesh.metadata.get("uuid")
                    try:
                        bb_intersect = not (
                            mesh.bounds[1][0] < void_mesh.bounds[0][0] or
                            mesh.bounds[0][0] > void_mesh.bounds[1][0] or
                            mesh.bounds[1][1] < void_mesh.bounds[0][1] or
                            mesh.bounds[0][1] > void_mesh.bounds[1][1] or
                            mesh.bounds[1][2] < void_mesh.bounds[0][2] or
                            mesh.bounds[0][2] > void_mesh.bounds[1][2]
                        )
                        
                        if bb_intersect:
                            try:
                                intersection = mesh.intersection(void_mesh)
                                if intersection and hasattr(intersection, 'volume') and intersection.volume > 1e-6:
                                    cutting_voids.append(void_uuid)
                                    print(f"[DEBUG] Layer void {void_uuid} cuts solid {solid_uuid} (both on layer {layer})")
                            except Exception as ex:
                                print(f"[DEBUG] Layer intersection test failed: {ex}")
                    except Exception as ex:
                        print(f"[DEBUG] Layer bounds check failed: {ex}")
                
                # Aplică tăierea cu voidurile de layer
                try:
                    diff = mesh.difference(layer_void_union)
                    if diff:
                        if isinstance(diff, list):
                            for dmesh in diff:
                                dmesh.metadata = dict(mesh.metadata) if hasattr(mesh, 'metadata') else {}
                                processed_solids.append(dmesh)
                        else:
                            diff.metadata = dict(mesh.metadata) if hasattr(mesh, 'metadata') else {}
                            processed_solids.append(diff)
                            # Recalculează volumul după tăierea cu voidurile de layer
                            if hasattr(diff, 'volume') and diff.volume > 0 and solid_uuid in uuid_to_entry:
                                uuid_to_entry[solid_uuid]["volume"] = float(diff.volume)
                                print(f"[DEBUG] Volume updated after layer voids: {uuid_to_entry[solid_uuid]['mesh_name']} = {diff.volume:.3f}m³")
                    else:
                        processed_solids.append(mesh)
                except Exception as ex:
                    print(f"[DEBUG] Layer boolean difference failed for mesh {solid_uuid}: {ex}")
                    processed_solids.append(mesh)
                
                # Actualizează mapping-ul cu voidurile de layer
                if solid_uuid in uuid_to_entry:
                    existing_cuts = uuid_to_entry[solid_uuid].get("is_cut_by", [])
                    uuid_to_entry[solid_uuid]["is_cut_by"] = existing_cuts + cutting_voids
            
            solids_by_layer[layer] = processed_solids
    
    # Colectează toate solidele finale
    for layer_solids in solids_by_layer.values():
        final_solids.extend(layer_solids)
    
    solids = final_solids

    # Taie elementele structurale la acoperiș
    solids, mapping = trim_elements_to_roof(solids, mapping)

    # Verificare finală și re-aplicare materiale înainte de export
    print(f"[DEBUG] Final material verification for {len(solids)} meshes:")
    for mesh in solids:
        mesh_name = mesh.metadata.get("name", "unknown")
        layer_from_metadata = mesh.metadata.get("layer", "unknown")
        
        # DEBUG SPECIAL pentru identificarea problemei layer-ului
        if "window" in mesh_name.lower() or "glass" in mesh_name.lower() or "wood" in mesh_name.lower():
            print(f"[DEBUG] BLOCK COMPONENT ANALYSIS: {mesh_name}")
            print(f"   - metadata['layer']: {layer_from_metadata}")
            print(f"   - metadata['component_layer']: {mesh.metadata.get('component_layer', 'N/A')}")
            print(f"   - metadata['material_layer']: {mesh.metadata.get('material_layer', 'N/A')}")
            print(f"   - Expected: wood/glass, Got: {layer_from_metadata}")
            
        if "material_rgba" in mesh.metadata and len(mesh.vertices) > 0:
            # Verifică și re-aplică materialul dacă este necesar
            component_layer = mesh.metadata.get("layer", "unknown")
            rgba = mesh.metadata["material_rgba"]
            
            # Re-aplică materialul pentru siguranță cu encoding layer
            mesh.visual.vertex_colors = np.tile(rgba, (len(mesh.vertices), 1))
            
            # Creează material cu nume descriptiv care include layer-ul
            component_layer = mesh.metadata.get("layer", "unknown")
            material_name = f"Material_{component_layer}_{mesh.metadata.get('name', 'unknown')}"
            
            mesh.visual.material = trimesh.visual.material.PBRMaterial(
                name=material_name,  # Nume descriptiv pentru identificare în Godot
                baseColorFactor=[mesh.metadata["material_color"][0], mesh.metadata["material_color"][1], mesh.metadata["material_color"][2], mesh.metadata["material_alpha"]],
                vertex_color=True,
                alphaMode="BLEND" if mesh.metadata["material_alpha"] < 1.0 else "OPAQUE"
            )
            print(f"[DEBUG] Final material check: {mesh_name} | layer={component_layer} | color={mesh.metadata['material_color']}")

    # Process section lines from DXF
    try:
        section_data = process_section_lines(doc, mapping)
        print(f"[DEBUG] Found {len(section_data)} section lines")
        
        # Add section planes to the existing solids list
        for i, section in enumerate(section_data):
            # Extract parameters for section plane mesh creation
            center = section['plane_center']
            normal = section['plane_normal']
            width = section['line_length']  # Folosește lungimea reală a liniei din DXF
            height = section['upper_z'] - section['lower_z']
            
            section_mesh = create_section_plane_mesh(center, normal, width, height)
            if section_mesh:
                mesh_name = f"section_plane_{i}"
                section_mesh.name = mesh_name
                section_uuid = str(uuid.uuid4())
                
                # Get material from layer_materials.json
                rgba = get_material('section')
                color, alpha = rgba[:3], rgba[3]
                
                # Add metadata similar to other meshes
                section_mesh.metadata = {
                    'name': mesh_name,
                    'layer': 'section',
                    'uuid': section_uuid,
                    'section_id': section['section_id'],
                    'material_color': color,
                    'material_alpha': alpha,
                    'material_rgba': np.array(color + [alpha], dtype=np.float32)
                }
                
                # Apply material to mesh
                rgba_float = np.array(color + [alpha], dtype=np.float32)
                section_mesh.visual.vertex_colors = np.tile(rgba_float, (len(section_mesh.vertices), 1))
                
                # Create material with descriptive name
                material_name = f"Material_section_{mesh_name}"
                section_mesh.visual.material = trimesh.visual.material.PBRMaterial(
                    name=material_name,
                    baseColorFactor=[color[0], color[1], color[2], alpha],
                    vertex_color=True,
                    alphaMode="BLEND" if alpha < 1.0 else "OPAQUE"
                )
                
                # Add to solids list for scene export
                solids.append(section_mesh)
                
                # Add to mapping for Godot integration
                mapping.append({
                    'mesh_name': mesh_name,
                    'uuid': section_uuid,
                    'dxf_type': 'SECTION_PLANE',
                    'layer': 'section',
                    'section_id': section['section_id'],
                    'start_point': [float(x) for x in section['start_point']],
                    'end_point': [float(x) for x in section['end_point']],
                    'plane_normal': [float(x) for x in section['plane_normal']],
                    'plane_center': [float(x) for x in section['plane_center']],
                    'section_depth': float(section['section_depth']),
                    'line_length': float(section['line_length']),  # Lungimea reală a liniei
                    'lower_z': float(section['lower_z']),
                    'upper_z': float(section['upper_z']),
                    'role': 1,  # Regular solid for scene
                    'solid_flag': 1,
                    'angle': 0.0,
                    'rotate_x': 0.0,
                    'rotate_y': 0.0,
                    'perimeter': 0.0,
                    'area': section['section_depth'] * 2.0,  # Approximate area
                    'lateral_area': 0.0,
                    'volume': 0.0,  # Section planes have no volume
                    'segment_lengths': [],
                    'vertices': [],
                    'is_cut_by': []
                })
                print(f"[DEBUG] Added section plane: {mesh_name}")
    except Exception as e:
        print(f"[WARNING] Error processing section lines: {e}")

    # Creează scenă și exportă
    scene = trimesh.Scene()
    for i, mesh in enumerate(solids):
        if "name" in mesh.metadata:
            base_name = mesh.metadata["name"]
            layer = mesh.metadata.get("layer", "unknown")
            
            # Encoding layer în numele node-ului pentru Godot
            # Format: MeshName_LAYER_LayerName pentru identificare în Godot
            node_name = f"{base_name}_LAYER_{layer}"
        else:
            node_name = f"solid_{i}"
            print(f"[WARNING] Mesh fara 'name' in metadata, fallback la {node_name}")
        
        print(f"[DEBUG] Add to scene: node_name={node_name} | original_layer={mesh.metadata.get('layer', 'unknown')} | vertices={len(mesh.vertices)}")
        scene.add_geometry(mesh, node_name=node_name)

    # Export mapping JSON
    json_path = os.path.splitext(out_path)[0] + "_mapping.json"
    import json
    with open(json_path, "w", encoding="utf-8") as jf:
        json.dump(mapping, jf, indent=2)
    print(f"[DEBUG] Exported mapping JSON: {json_path}")

    # Start IFC background conversion
    if ifc_converter and IFC_CONVERSION_AVAILABLE and ifc_output_path:
        try:
            print(f"[DEBUG] Adding {len(mapping)} elements to IFC queue...")
            
            # Add all mapping elements to IFC queue
            for entry in mapping:
                try:
                    # Process XDATA before conversion
                    processed_entry = process_xdata_for_element(entry)
                    ifc_converter.queue_element_for_conversion(processed_entry)
                except Exception as e:
                    print(f"[WARNING] Could not process element for IFC: {entry.get('mesh_name', 'Unknown')} - {e}")
            
            # Start background conversion
            ifc_converter.start_background_conversion(ifc_output_path)
            print(f"[DEBUG] IFC background conversion started to: {ifc_output_path}")
            
        except Exception as e:
            print(f"[WARNING] Could not start IFC background conversion: {e}")

    export_scene(scene, out_path)

    elapsed = time.time() - start_time
    print(f"[DEBUG] Finished DXF to GLB in {elapsed:.2f} sec.")
    
    # GLB-based IFC conversion (more robust - uses final geometry + metadata)
    if IFC_GLB_CONVERSION_AVAILABLE:
        try:
            base_name = os.path.splitext(out_path)[0]
            json_mapping_path = base_name + "_mapping.json"
            ifc_from_glb_path = base_name + "_from_glb.ifc"
            
            if os.path.exists(json_mapping_path):
                print(f"[DEBUG] Starting GLB-based IFC conversion...")
                if convert_glb_to_ifc(out_path, json_mapping_path, ifc_from_glb_path):
                    print(f"[SUCCESS] GLB-based IFC conversion completed: {ifc_from_glb_path}")
                else:
                    print(f"[WARNING] GLB-based IFC conversion failed")
            else:
                print(f"[WARNING] JSON mapping not found for GLB-based IFC conversion: {json_mapping_path}")
        except Exception as e:
            print(f"[WARNING] GLB-based IFC conversion error: {e}")
    
    # Information about IFC background conversion
    if ifc_converter and IFC_CONVERSION_AVAILABLE:
        print(f"[INFO] IFC conversion running in background...")
        print(f"[INFO] Final IFC file: {ifc_output_path}")
        print(f"[INFO] To wait for completion: ifc_converter.wait_for_completion()")

# -----------------------------
# Main
# -----------------------------
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python dxf_to_glb.py input.dxf output.glb [arc_segments]")
        sys.exit(1)

    dxf_path = sys.argv[1]
    out_path = sys.argv[2]
    arc_segments = int(sys.argv[3]) if len(sys.argv) > 3 else 16

    dxf_to_gltf(dxf_path, out_path, arc_segments)

    print(f"Converted {dxf_path} to {out_path}")