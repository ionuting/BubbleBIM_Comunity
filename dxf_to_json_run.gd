extends Node3D

func _ready():
	var dxf_path = "python/dxf/exemplu_nou.dxf" # sau calea completă dacă nu e în directorul de lucru
	var json_path = "python/dxf/out1.json" # sau calea dorită pentru output
	var script_path = "python/dxf_to_json.py"
	var args = [script_path, dxf_path, json_path]
	var output = []
	var exit_code = OS.execute("python", args, output, true)
	print("Rezultat script Python:", output)
	print("Exit code:", exit_code)
