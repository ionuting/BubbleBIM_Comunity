import json
import trimesh
import numpy as np
from trimesh.creation import extrude_polygon
from shapely.geometry import Polygon

# Config materiale simple (culoare RGBA)
LAYER_COLORS = {
    "Rooms": [0.8, 0.8, 0.8, 1.0],
    "void": [1.0, 1.0, 1.0, 0.0],
    "column": [0.7, 0.7, 0.2, 1.0],
    "beam": [0.5, 0.5, 0.5, 1.0],
    "proxy": [0.2, 0.7, 0.9, 1.0],
    "default": [0.5, 1.0, 0.0, 1.0]
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

def get_color(layer):
    return LAYER_COLORS.get(layer, LAYER_COLORS["default"])

def main(json_path, out_path):
    with open(json_path, "r") as f:
        data = json.load(f)

    solids = []
    voids = []
    materials = []

    for entity in data:
        if entity["type"] != "LWPOLYLINE" or not entity.get("closed", False):
            continue
        points = [(float(p[0]), float(p[1])) for p in entity["points"]]
        poly = Polygon(points)
        if not poly.is_valid or not poly.is_simple or poly.area == 0:
            continue
        height, z = parse_height_z(entity.get("xdata", {}))
        layer = entity.get("layer", "default")
        color = get_color(layer)
        mesh = extrude_polygon(poly, height)
        mesh.apply_translation([0, 0, z])
        if layer == "void":
            voids.append(mesh)
        else:
            solids.append((mesh, color))

    # Aplica void-urile (diferenta booleana)
    if voids:
        void_union = trimesh.util.concatenate(voids)
        new_solids = []
        for mesh, color in solids:
            diff = mesh.difference(void_union)
            if diff is not None:
                if isinstance(diff, list):
                    for d in diff:
                        new_solids.append((d, color))
                else:
                    new_solids.append((diff, color))
        solids = new_solids

    # Creeaza scena si exporta
    scene = trimesh.Scene()
    for i, (mesh, color) in enumerate(solids):
        mesh.visual.vertex_colors = np.tile((np.array(color)*255).astype(np.uint8), (len(mesh.vertices), 1))
        scene.add_geometry(mesh, node_name=f"solid_{i}")
    scene.export(out_path)

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: python json_to_glb_trimesh.py input.json output.glb")
        exit(1)
    main(sys.argv[1], sys.argv[2])
