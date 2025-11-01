import os
import sys
from dxf_to_glb_trimesh import dxf_to_gltf

def main():
    if len(sys.argv) > 1:
        # Use command line argument
        dxf_path = sys.argv[1]
        glb_path = os.path.splitext(dxf_path)[0] + "_out.glb"
    else:
        # Default paths
        dxf_path = r"C:/Users/ionut.ciuntuc/Documents/viewer2d/python/dxf/etaj_01.dxf"
        glb_path = r"C:/Users/ionut.ciuntuc/Documents/viewer2d/python/dxf/etaj_01_out.glb"

    print(f"[INFO] DXF to GLB conversion: {dxf_path} -> {glb_path}")
    dxf_to_gltf(dxf_path, glb_path)
    print(f"[INFO] Conversion completed: {glb_path}")

if __name__ == "__main__":
    main()
