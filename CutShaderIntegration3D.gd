# CutShaderIntegration3D.gd
# Integrarea sistemului cut shader cu viewerul 3D existent
extends Node3D

signal section_dxf_exported(file_path: String)
signal cut_shader_preview_updated(preview_data: Dictionary)

# Referințe la componentele existente
var cad_viewer: Node3D
var camera_3d: Camera3D
var canvas_layer: CanvasLayer

# Cut shader manager
var cut_shader_active: bool = false
var section_planes: Array = []
var current_preview_data: Dictionary = {}

# UI pentru cut shader
var cut_shader_panel: Panel
var cut_shader_enabled_checkbox: CheckBox
var depth_layers_container: VBoxContainer
var export_dxf_button: Button
var preview_button: Button

# Python integration
var temp_dir: String = "user://cut_shader_temp/"
var python_process_id: int = -1

func _ready():
	print("[CutShader3D] Initializing cut shader integration...")
	_setup_temp_directory()
	_connect_to_cad_viewer()
	# _setup_cut_shader_ui()  # DISABLED - UI removal while keeping backend functionality
	print("[CutShader3D] Cut shader integration ready!")

func _setup_temp_directory():
	var dir = DirAccess.open("user://")
	if not dir.dir_exists("cut_shader_temp"):
		dir.make_dir_recursive("cut_shader_temp")
	temp_dir = ProjectSettings.globalize_path("user://cut_shader_temp/")

func _connect_to_cad_viewer():
	# Caută viewerul CAD în părinte
	cad_viewer = get_parent()
	if cad_viewer:
		camera_3d = cad_viewer.get_node_or_null("Camera3D")
		canvas_layer = cad_viewer.get_node_or_null("CanvasLayer")
		print("[CutShader3D] Connected to CAD viewer:", cad_viewer.name)
	else:
		print("[CutShader3D] Warning: Could not find CAD viewer parent")

func _setup_cut_shader_ui():
	if not canvas_layer:
		print("[CutShader3D] Warning: No canvas layer found for UI")
		return
	
	# Creează panelul pentru cut shader controls
	cut_shader_panel = Panel.new()
	cut_shader_panel.name = "CutShaderPanel"
	cut_shader_panel.position = Vector2(440, 2)  # După butoanele existente
	cut_shader_panel.size = Vector2(300, 200)
	cut_shader_panel.add_theme_color_override("bg_color", Color(0.2, 0.3, 0.4, 0.9))
	canvas_layer.add_child(cut_shader_panel)
	
	var y_offset = 10
	
	# Title
	var title_label = Label.new()
	title_label.text = "Cut Shader Sections"
	title_label.position = Vector2(10, y_offset)
	title_label.add_theme_color_override("font_color", Color.WHITE)
	title_label.add_theme_font_size_override("font_size", 14)
	cut_shader_panel.add_child(title_label)
	y_offset += 25
	
	# Enable/Disable checkbox
	cut_shader_enabled_checkbox = CheckBox.new()
	cut_shader_enabled_checkbox.text = "Enable Cut Shader"
	cut_shader_enabled_checkbox.position = Vector2(10, y_offset)
	cut_shader_enabled_checkbox.button_pressed = cut_shader_active
	cut_shader_enabled_checkbox.toggled.connect(_on_cut_shader_toggled)
	cut_shader_panel.add_child(cut_shader_enabled_checkbox)
	y_offset += 25
	
	# Sync with existing sections button
	var sync_button = Button.new()
	sync_button.text = "Sync with Current Sections"
	sync_button.position = Vector2(10, y_offset)
	sync_button.size = Vector2(180, 25)
	sync_button.pressed.connect(_sync_with_existing_sections)
	cut_shader_panel.add_child(sync_button)
	y_offset += 30
	
	# Depth layers label
	var depth_label = Label.new()
	depth_label.text = "Depth Analysis Layers:"
	depth_label.position = Vector2(10, y_offset)
	depth_label.add_theme_color_override("font_color", Color.WHITE)
	cut_shader_panel.add_child(depth_label)
	y_offset += 20
	
	# Depth layers container
	depth_layers_container = VBoxContainer.new()
	depth_layers_container.position = Vector2(10, y_offset)
	depth_layers_container.size = Vector2(280, 60)
	cut_shader_panel.add_child(depth_layers_container)
	y_offset += 70
	
	# Add default depth layers
	_add_depth_layer_control(0.5)
	_add_depth_layer_control(1.0)
	_add_depth_layer_control(2.0)
	
	# Preview button
	preview_button = Button.new()
	preview_button.text = "Generate Preview"
	preview_button.position = Vector2(10, y_offset)
	preview_button.size = Vector2(130, 25)
	preview_button.pressed.connect(_generate_cut_shader_preview)
	cut_shader_panel.add_child(preview_button)
	
	# Export DXF button
	export_dxf_button = Button.new()
	export_dxf_button.text = "Export DXF"
	export_dxf_button.position = Vector2(150, y_offset)
	export_dxf_button.size = Vector2(130, 25)
	export_dxf_button.pressed.connect(_export_dxf_section)
	cut_shader_panel.add_child(export_dxf_button)
	
	print("[CutShader3D] Cut shader UI created successfully")

func _add_depth_layer_control(default_value: float):
	var hbox = HBoxContainer.new()
	
	var label = Label.new()
	label.text = "Layer:"
	label.add_theme_color_override("font_color", Color.WHITE)
	label.custom_minimum_size = Vector2(50, 20)
	hbox.add_child(label)
	
	var spinbox = SpinBox.new()
	spinbox.min_value = 0.1
	spinbox.max_value = 10.0
	spinbox.step = 0.1
	spinbox.value = default_value
	spinbox.custom_minimum_size = Vector2(80, 20)
	hbox.add_child(spinbox)
	
	var remove_btn = Button.new()
	remove_btn.text = "X"
	remove_btn.custom_minimum_size = Vector2(25, 20)
	remove_btn.pressed.connect(_remove_depth_layer.bind(hbox))
	hbox.add_child(remove_btn)
	
	depth_layers_container.add_child(hbox)

func _remove_depth_layer(hbox: HBoxContainer):
	depth_layers_container.remove_child(hbox)
	hbox.queue_free()

func _on_cut_shader_toggled(enabled: bool):
	cut_shader_active = enabled
	print("[CutShader3D] Cut shader ", "enabled" if enabled else "disabled")
	
	if enabled:
		_sync_with_existing_sections()

func _sync_with_existing_sections():
	"""Sincronizează planurile cut shader cu secțiunile existente din viewer"""
	if not cad_viewer:
		print("[CutShader3D] No CAD viewer reference")
		return
	
	section_planes.clear()
	
	# Verifică dacă există sisteme de secțiuni în viewerul existent
	if cad_viewer.has_method("_get_current_section_data"):
		var section_data = cad_viewer._get_current_section_data()
		_convert_viewer_sections_to_cut_planes(section_data)
	else:
		# Creează planuri de secțiune bazate pe camera curentă
		_create_cut_planes_from_camera()
	
	print("[CutShader3D] Synchronized ", len(section_planes), " section planes")

func _convert_viewer_sections_to_cut_planes(section_data: Dictionary):
	"""Convertește datele de secțiune din viewer în planuri cut shader"""
	for section_name in section_data.keys():
		var section = section_data[section_name]
		var cut_plane = {
			"name": section_name,
			"origin": section.get("origin", Vector3.ZERO),
			"normal": section.get("normal", Vector3.UP),
			"active": section.get("enabled", true),
			"depth_range": section.get("depth_range", [0.0, 3.0])
		}
		section_planes.append(cut_plane)

func _create_cut_planes_from_camera():
	"""Creează planuri de secțiune bazate pe poziția și orientarea camerei"""
	if not camera_3d:
		return
	
	var camera_pos = camera_3d.global_transform.origin
	var camera_forward = -camera_3d.global_transform.basis.z
	
	# Plan de secțiune principal bazat pe camera
	var main_plane = {
		"name": "Camera_Section",
		"origin": camera_pos,
		"normal": camera_forward,
		"active": true,
		"depth_range": [0.0, 3.0]
	}
	section_planes.append(main_plane)
	
	# Plan suplimentar pentru analiza pe adâncime
	var depth_plane = {
		"name": "Depth_Analysis",
		"origin": camera_pos + camera_forward * 2.0,
		"normal": camera_forward,
		"active": true,
		"depth_range": [1.0, 4.0]
	}
	section_planes.append(depth_plane)

func _get_depth_layers() -> Array:
	"""Extrage valorile straturilor de adâncime din UI"""
	var layers = []
	for child in depth_layers_container.get_children():
		if child is HBoxContainer:
			var spinbox = child.get_child(1) as SpinBox
			if spinbox:
				layers.append(spinbox.value)
	return layers

func _generate_cut_shader_preview():
	"""Generează preview-ul cut shader"""
	if not cut_shader_active:
		print("[CutShader3D] Cut shader not active")
		return
	
	if len(section_planes) == 0:
		_sync_with_existing_sections()
	
	var preview_data = _prepare_cut_shader_data()
	_call_python_cut_shader(preview_data, true)

func _export_dxf_section():
	"""Exportă secțiunea curentă ca DXF"""
	if not cut_shader_active:
		print("[CutShader3D] Cut shader not active")
		return
	
	if len(section_planes) == 0:
		_sync_with_existing_sections()
	
	var export_data = _prepare_cut_shader_data()
	_call_python_cut_shader(export_data, false)

func _prepare_cut_shader_data() -> Dictionary:
	"""Pregătește datele pentru sistemul cut shader Python"""
	var data = {
		"planes": [],
		"depth_layers": _get_depth_layers(),
		"material_filter": "",
		"output_dir": temp_dir,
		"export_mode": true,
		"format": "dxf"
	}
	
	# Convertește planurile de secțiune
	for plane in section_planes:
		var plane_data = {
			"name": plane.name,
			"origin": {
				"x": plane.origin.x,
				"y": plane.origin.y, 
				"z": plane.origin.z
			},
			"normal": {
				"x": plane.normal.x,
				"y": plane.normal.y,
				"z": plane.normal.z
			},
			"active": plane.active,
			"depth_range": plane.depth_range
		}
		data.planes.append(plane_data)
	
	return data

func _call_python_cut_shader(data: Dictionary, is_preview: bool):
	"""Apelează scriptul Python pentru procesarea cut shader"""
	# Salvează datele într-un fișier JSON temporar
	var json_file = temp_dir + "cut_shader_params.json"
	var file = FileAccess.open(json_file, FileAccess.WRITE)
	if file:
		file.store_string(JSON.stringify(data))
		file.close()
	else:
		print("[CutShader3D] Failed to save parameters file")
		return
	
	# Apelează scriptul Python
	var python_script = ProjectSettings.globalize_path("res://realtime_cut_shader_3d.py")
	var args = [python_script, json_file]
	
	if is_preview:
		args.append("--preview")
	
	print("[CutShader3D] Calling Python script: python ", args)
	
	var output = []
	var exit_code = OS.execute("python", args, output, false, true)
	
	if exit_code == 0:
		_on_cut_shader_completed(output, is_preview)
	else:
		print("[CutShader3D] Python script failed with exit code: ", exit_code)
		for line in output:
			print("[Python Error] ", line)

func _on_cut_shader_completed(output: Array, was_preview: bool):
	"""Procesează rezultatul scriptului Python"""
	var result_file = ""
	var success_message = ""
	
	for line in output:
		if line.begins_with("RESULT_FILE:"):
			result_file = line.substr(12).strip_edges()
		elif line.begins_with("SUCCESS:"):
			success_message = line.substr(8).strip_edges()
		
		print("[Python Output] ", line)
	
	if result_file != "":
		if was_preview:
			current_preview_data = {"file": result_file, "message": success_message}
			emit_signal("cut_shader_preview_updated", current_preview_data)
			print("[CutShader3D] Preview generated: ", result_file)
		else:
			emit_signal("section_dxf_exported", result_file)
			print("[CutShader3D] DXF exported: ", result_file)
			
			# Afișează mesaj de succes în UI
			_show_export_message("DXF export successful!\nFile: " + result_file.get_file())

func _show_export_message(message: String):
	"""Afișează un mesaj de succes pentru export"""
	if not canvas_layer:
		return
	
	var message_label = Label.new()
	message_label.text = message
	message_label.position = Vector2(50, 50)
	message_label.size = Vector2(400, 60)
	message_label.add_theme_color_override("font_color", Color.GREEN)
	message_label.add_theme_color_override("font_shadow_color", Color.BLACK)
	message_label.add_theme_font_size_override("font_size", 12)
	canvas_layer.add_child(message_label)
	
	# Elimină mesajul după 3 secunde
	var timer = Timer.new()
	timer.wait_time = 3.0
	timer.one_shot = true
	timer.timeout.connect(func(): 
		message_label.queue_free()
		timer.queue_free()
	)
	canvas_layer.add_child(timer)
	timer.start()

# === INTEGRATION WITH EXISTING SECTION SYSTEM ===

func integrate_with_existing_sections():
	"""Integrează cu sistemul de secțiuni existent din CAD viewer"""
	if not cad_viewer:
		return
	
	# Conectează la semnalele existente de secțiuni dacă există
	if cad_viewer.has_signal("section_changed"):
		cad_viewer.section_changed.connect(_on_existing_section_changed)
	
	# Hook-uri în metodele existente de secțiuni
	if cad_viewer.has_method("_on_horizontal_section_z_changed"):
		# Monitorizează schimbările în secțiunile orizontale
		pass

func _on_existing_section_changed(section_data: Dictionary):
	"""Reacționează la schimbările în sistemul de secțiuni existent"""
	if cut_shader_active:
		_sync_with_existing_sections()
		if cut_shader_enabled_checkbox and cut_shader_enabled_checkbox.button_pressed:
			# Auto-actualizează preview-ul
			call_deferred("_generate_cut_shader_preview")

# === KEYBOARD SHORTCUTS ===

func _unhandled_input(event):
	if event is InputEventKey and event.pressed:
		match event.keycode:
			KEY_C:
				if Input.is_key_pressed(KEY_CTRL) and Input.is_key_pressed(KEY_SHIFT):
					# Ctrl+Shift+C: Toggle cut shader
					if cut_shader_enabled_checkbox:
						cut_shader_enabled_checkbox.button_pressed = not cut_shader_enabled_checkbox.button_pressed
						_on_cut_shader_toggled(cut_shader_enabled_checkbox.button_pressed)
					return true
			KEY_E:
				if Input.is_key_pressed(KEY_CTRL) and cut_shader_active:
					# Ctrl+E: Export DXF
					_export_dxf_section()
					return true
			KEY_P:
				if Input.is_key_pressed(KEY_CTRL) and cut_shader_active:
					# Ctrl+P: Generate preview
					_generate_cut_shader_preview()
					return true
	
	return false

# === CLEANUP ===

func _exit_tree():
	# Curăță fișierele temporare
	var dir = DirAccess.open(temp_dir)
	if dir:
		dir.list_dir_begin()
		var file_name = dir.get_next()
		while file_name != "":
			if not dir.current_is_dir():
				dir.remove(file_name)
			file_name = dir.get_next()
