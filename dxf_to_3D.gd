extends Node3D

# Referințe la noduri pentru organizare
var models_container: Node3D
var current_loaded_models: Array = []

func _ready():
	# Creează container pentru modele
	models_container = Node3D.new()
	models_container.name = "ModelsContainer"
	add_child(models_container)
	
	# Încarcă GLB-ul cu TOV processing
	load_glb_with_tov()
	
	# Scanează și încarcă modele din Diagram.xml (opțional)
	# load_diagram_models_from_manifest("res://project_manifest.json")

func load_diagram_models_from_manifest(manifest_path: String):
	"""
	Încarcă toate modelele GLB din manifest generat de graph_to_glb.py
	"""
	if not FileAccess.file_exists(manifest_path):
		push_warning("Manifest not found: %s" % manifest_path)
		return
	
	var file = FileAccess.open(manifest_path, FileAccess.READ)
	if not file:
		push_error("Failed to open manifest: %s" % manifest_path)
		return
	
	var json_text = file.get_as_text()
	file.close()
	
	var json = JSON.new()
	var parse_result = json.parse(json_text)
	
	if parse_result != OK:
		push_error("Failed to parse manifest JSON: %s" % manifest_path)
		return
	
	var manifest = json.get_data()
	var models = manifest.get("models", [])
	
	print("[LOAD] Loading %d diagram models from manifest" % models.size())
	
	for model_info in models:
		var glb_path = model_info.get("glb_output", "")
		var model_name = model_info.get("name", "Unknown")
		
		# Convertește calea la format Godot (res://)
		var godot_path = _convert_to_godot_path(glb_path)
		
		if godot_path and FileAccess.file_exists(godot_path):
			print("[LOAD] Loading diagram model: %s from %s" % [model_name, godot_path])
			var model_node = load_glb_file(godot_path, model_name)
			
			if model_node:
				models_container.add_child(model_node)
				current_loaded_models.append({
					"name": model_name,
					"node": model_node,
					"source": glb_path
				})
		else:
			push_warning("GLB file not found or invalid path: %s" % glb_path)
	
	print("[LOAD] Successfully loaded %d diagram models" % current_loaded_models.size())


func _convert_to_godot_path(file_path: String) -> String:
	"""
	Convertește o cale de sistem la format Godot (res://)
	"""
	# Dacă e deja res://, returnează direct
	if file_path.begins_with("res://"):
		return file_path
	
	# Încearcă să găsească calea relativă la proiect
	var project_path = ProjectSettings.globalize_path("res://")
	var abs_path = ProjectSettings.globalize_path(file_path)
	
	# Verifică dacă fișierul e în proiect
	if abs_path.begins_with(project_path):
		var rel_path = abs_path.substr(project_path.length())
		return "res://" + rel_path.replace("\\", "/")
	
	# Dacă nu e în proiect, încearcă cu calea globală (user://)
	if FileAccess.file_exists(file_path):
		# Pentru fișiere externe, Godot nu poate încărca direct
		# Trebuie copiate în proiect sau folosit user://
		push_warning("File outside project: %s" % file_path)
		return ""
	
	return ""


func load_glb_file(glb_path: String, model_name: String = "") -> Node3D:
	"""
	Încarcă un fișier GLB și returnează root node-ul
	"""
	if not FileAccess.file_exists(glb_path):
		push_error("GLB file not found: %s" % glb_path)
		return null
	
	var gltf = GLTFDocument.new()
	var state = GLTFState.new()
	var error = gltf.append_from_file(glb_path, state)
	
	if error != OK:
		push_error("Failed to load GLB: %s (error: %d)" % [glb_path, error])
		return null
	
	var scene_root = gltf.generate_scene(state)
	
	if scene_root:
		if model_name:
			scene_root.name = model_name
		
		print("[GLB] Successfully loaded: %s" % glb_path)
		print("[GLB] Children count: %d" % scene_root.get_children().size())
		
		# Debug mesh info
		_debug_meshes(scene_root)
		
		return scene_root
	else:
		push_error("Failed to generate scene from GLB: %s" % glb_path)
		return null


func clear_loaded_models():
	"""
	Elimină toate modelele încărcate din container
	"""
	for child in models_container.get_children():
		child.queue_free()
	
	current_loaded_models.clear()
	print("[CLEAR] Cleared all loaded models")


func get_loaded_models_info() -> Array:
	"""
	Returnează informații despre modelele încărcate
	"""
	return current_loaded_models


func load_glb_with_tov():
	var glb_path = "res://test_tov_demo.glb"
	if not FileAccess.file_exists(glb_path):
		push_error("GLB file not found: %s" % glb_path)
		return
	
	# Încarcă GLB-ul
	var gltf = GLTFDocument.new()
	var state = GLTFState.new()
	var error = gltf.append_from_file(glb_path, state)
	
	if error != OK:
		push_error("Failed to load GLB: %s" % glb_path)
		return
	
	# Generează scena din GLB
	var scene_root = gltf.generate_scene(state)
	if scene_root:
		add_child(scene_root)
		print("Successfully loaded GLB with TOV processing!")
		print("Children count: ", scene_root.get_children().size())
		
		# Debug info pentru mesh-uri
		_debug_meshes(scene_root)
	else:
		push_error("Failed to generate scene from GLB")

func _debug_meshes(node: Node, depth: int = 0):
	var indent = "  ".repeat(depth)
	print(indent, "Node: ", node.name, " (", node.get_class(), ")")
	
	if node is MeshInstance3D:
		var mesh_instance = node as MeshInstance3D
		if mesh_instance.mesh:
			print(indent, "  Mesh surfaces: ", mesh_instance.mesh.get_surface_count())
			for i in range(mesh_instance.mesh.get_surface_count()):
				var material = mesh_instance.mesh.surface_get_material(i)
				if material:
					print(indent, "    Surface ", i, " material: ", material.resource_path)
				else:
					print(indent, "    Surface ", i, " no material")
	
	for child in node.get_children():
		_debug_meshes(child, depth + 1)


# Creează un CSGPolygon3D din puncte
func create_polygon(points: Array, closed: bool) -> CSGPolygon3D:
	var arr: PackedVector2Array = []
	for p in points:
		arr.append(Vector2(p[0], p[1]))
	if closed:
		arr.append(Vector2(points[0][0], points[0][1]))

	var csg = CSGPolygon3D.new()
	csg.polygon = arr       # aici merge array direct, nu Curve2D
	csg.mode = CSGPolygon3D.MODE_DEPTH
	csg.depth = 1.0
	return csg


# Creează un cerc aproximat cu poligon regulat
func create_circle(center: Array, radius: float, segments: int = 32) -> CSGPolygon3D:
	var arr: PackedVector2Array = []
	for i in range(segments):
		var angle = (TAU / segments) * i
		var x = center[0] + cos(angle) * radius
		var y = center[1] + sin(angle) * radius
		arr.append(Vector2(x, y))
	arr.append(arr[0]) # închide cercul

	var csg = CSGPolygon3D.new()
	csg.polygon = arr
	csg.mode = CSGPolygon3D.MODE_DEPTH
	csg.depth = 1.0
	return csg
