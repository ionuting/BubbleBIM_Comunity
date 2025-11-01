# Auto-generated script for loading Diagram.xml models
extends Node

var models_loaded: bool = false
var models_info: Array = []

func _ready():
	print("[DiagramLoader] Ready to load diagram models")

func load_all_diagrams() -> Array:
	"""Load all diagram models from manifest"""
	var manifest_path = "res://diagrams_output/diagrams_manifest.json"
	
	if not FileAccess.file_exists(manifest_path):
		push_warning("Diagram manifest not found: %s" % manifest_path)
		return []
	
	var file = FileAccess.open(manifest_path, FileAccess.READ)
	if not file:
		push_error("Failed to open manifest: %s" % manifest_path)
		return []
	
	var json_text = file.get_as_text()
	file.close()
	
	var json = JSON.new()
	var parse_result = json.parse(json_text)
	
	if parse_result != OK:
		push_error("Failed to parse manifest JSON")
		return []
	
	var manifest = json.get_data()
	models_info = manifest.get("models", [])
	
	print("[DiagramLoader] Found %d diagram models" % models_info.size())
	models_loaded = true
	
	return models_info

func get_model_glb_path(model_name: String) -> String:
	"""Get GLB path for a specific model by name"""
	if not models_loaded:
		load_all_diagrams()
	
	for model in models_info:
		if model.get("name", "") == model_name:
			var glb_path = model.get("relative_path", "")
			if glb_path:
				return "res://" + glb_path.replace("\\", "/")
	
	return ""

func get_all_model_names() -> Array:
	"""Get list of all model names"""
	if not models_loaded:
		load_all_diagrams()
	
	var names = []
	for model in models_info:
		names.append(model.get("name", "Unknown"))
	
	return names
