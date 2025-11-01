import ezdxf
import json
import sys
import time

class DXFtoJSONConverter:
    def __init__(self, dxf_path, json_path):
        self.dxf_path = dxf_path
        self.json_path = json_path

    def convert(self):
        print(f"[DEBUG] Start DXF to JSON: {self.dxf_path} -> {self.json_path}")
        start_time = time.time()
        doc = ezdxf.readfile(self.dxf_path)
        msp = doc.modelspace()
        entities = []
        for idx, e in enumerate(msp):
            ent_type = e.dxftype()
            print(f"[DEBUG] Entity {idx}: type={ent_type}, handle={getattr(e.dxf, 'handle', None)}, layer={getattr(e.dxf, 'layer', None)}")
            ent = {
                "type": ent_type,
                "handle": e.dxf.handle,
                "layer": e.dxf.layer,
            }

            # XDATA (proprietăți custom, inclusiv QCAD)
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
            if xdata:
                ent["xdata"] = xdata

            # TEXT
            if ent_type == "TEXT":
                ent["text"] = e.dxf.text
                ent["position"] = [e.dxf.insert.x, e.dxf.insert.y]
                ent["layer"] = e.dxf.layer
            # MTEXT
            elif ent_type == "MTEXT":
                ent["text"] = e.text
                ent["position"] = [e.dxf.insert.x, e.dxf.insert.y]
                ent["layer"] = e.dxf.layer
            # CIRCLE
            elif ent_type == "CIRCLE":
                ent["center"] = [e.dxf.center.x, e.dxf.center.y]
                ent["radius"] = e.dxf.radius
                ent["layer"] = e.dxf.layer
            # ARC
            elif ent_type == "ARC":
                ent["center"] = [e.dxf.center.x, e.dxf.center.y]
                ent["radius"] = e.dxf.radius
                ent["start_angle"] = e.dxf.start_angle
                ent["end_angle"] = e.dxf.end_angle
                ent["layer"] = e.dxf.layer
            # LWPOLYLINE (poligon inchis)
            elif ent_type == "LWPOLYLINE":
                points = [[p[0], p[1]] for p in e.get_points()]
                ent["points"] = points
                ent["closed"] = e.closed
                ent["layer"] = e.dxf.layer
            # POLYLINE (poligon inchis)
            elif ent_type == "POLYLINE":
                points = [[v.dxf.location.x, v.dxf.location.y] for v in e.vertices()]
                ent["points"] = points
                ent["closed"] = e.is_closed
                ent["layer"] = e.dxf.layer
            # BLOCKINSERT
            elif ent_type == "INSERT":
                ent["block_name"] = e.dxf.name
                ent["insert"] = [e.dxf.insert.x, e.dxf.insert.y]
                ent["rotation"] = e.dxf.rotation if hasattr(e.dxf, "rotation") else 0
                ent["scale"] = [e.dxf.xscale, e.dxf.yscale] if hasattr(e.dxf, "xscale") else [1, 1]
                ent["layer"] = e.dxf.layer
            entities.append(ent)
            if idx % 10 == 0:
                print(f"[DEBUG] Processed {idx+1} entities...")
        print(f"[DEBUG] Total entities: {len(entities)}")
        with open(self.json_path, "w", encoding="utf-8") as f:
            json.dump(entities, f, indent=2, default=str)
        elapsed = time.time() - start_time
        print(f"[DEBUG] Finished DXF to JSON in {elapsed:.2f} seconds.")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python dxf_to_json.py input.dxf output.json")
        sys.exit(1)
    dxf_path = sys.argv[1]
    json_path = sys.argv[2]
    converter = DXFtoJSONConverter(dxf_path, json_path)
    converter.convert()
    print(f"Converted {dxf_path} to {json_path}")



