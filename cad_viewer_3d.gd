# CADViewer.gd (versiunea îmbunătățită cu snap)
extends Node3D

# IMMEDIATE DEBUG - This should print as soon as script loads
func _init():
	print("🚨 CAD_VIEWER_3D.GD SCRIPT LOADED! _init() called")

@onready var camera: Camera3D = $Camera3D
@onready var canvas: CanvasLayer = $CanvasLayer

# Grid & background
@export var grid_spacing: float = 1.0
@export var grid_color: Color = Color(0.8,0.8,0.8,0.3)
@export var background_color: Color = Color(0.95,0.95,0.95)

# Infinite Grid settings
var grid_visible: bool = true
var grid_z_position: float = 0.0
var infinite_grid: MeshInstance3D
var grid_material: StandardMaterial3D



# Snap settings
var snap_enabled: bool = false
var snap_distance: float = 0.5
var snap_preview_marker: MeshInstance3D

# Zoom, Pan, Orbit
@export var zoom_speed: float = 1.05  # Zoom mai puțin sensibil (5% în loc de 10%)
@export var max_orthogonal_size: float = 10000.0  # Limite pentru zoom out extrem
@export var min_orthogonal_size: float = 0.1      # Limite pentru zoom in extrem
var pan_last_pos: Vector2
var is_panning := false
var rotate_last_pos: Vector2
var is_rotating := false
var orbit_pivot: Vector3 = Vector3.ZERO

# UI elements
var coord_label: Label

# Grid UI controls
var grid_controls_panel: Panel
var grid_visible_checkbox: CheckBox
var grid_z_slider: HSlider
var grid_z_label: Label

var selected_geometry: Node3D = null
var default_material: StandardMaterial3D = null
var layer_materials := {}

# Dictionary to track all imported projects (filename -> layer_groups)
var imported_projects := {}

# Current project folder pentru ReloadBtn
var current_project_folder: String = ""

# === CUT SHADER SECTION SYSTEM ===
var cut_shader_integration: Node3D = null
var section_planes_data: Array = []
var current_section_state: Dictionary = {}

# Section visibility and control variables
var horizontal_section_enabled: bool = false
var vertical_section_enabled: bool = false
var horizontal_section_z: float = 1.0
var horizontal_section_depth: float = 0.5
var vertical_section_x: float = 0.0
var vertical_section_y: float = 0.0
var vertical_section_depth: float = 0.5

# Section UI controls
var section_controls_panel: Panel
var h_section_checkbox: CheckBox
var v_section_checkbox: CheckBox
var h_section_slider: HSlider
var h_depth_slider: HSlider
var v_section_x_slider: HSlider
var v_section_y_slider: HSlider
var v_depth_slider: HSlider

# Section effects
var section_material: StandardMaterial3D
var section_shader: Shader

# Section planes for visualization
var section_plane_horizontal: MeshInstance3D
var section_plane_vertical_x: MeshInstance3D
var section_plane_vertical_y: MeshInstance3D

# Additional UI controls for sections
var vertical_section_toggle: CheckBox

# Drawing plane and depth control variables
var drawing_plane_z: float = 0.0
var z_min: float = -2.0
var z_max: float = 5.0

func _ready():
	print("🚨🚨🚨 CAD_VIEWER_3D.GD _ready() FUNCTION STARTED! 🚨🚨🚨")
	print("=== CAD VIEWER 3D - SCENE STARTUP DEBUG ===")
	print("[DEBUG] _ready() called - initializing scene...")
	print("[DEBUG] Grid settings - visible:", grid_visible, "z_position:", grid_z_position, "spacing:", grid_spacing)
	
	# Adaugă o lumină direcțională pentru evidențierea voidurilor
	var dir_light = DirectionalLight3D.new()
	dir_light.light_color = Color(1, 1, 0.95)
	dir_light.shadow_enabled = true
	dir_light.shadow_bias = 0.05
	
	# Poziționează lumina sus (Z mare) și orientează-o în jos spre scena
	# În sistemul nostru: X = est-vest, Y = nord-sud, Z = verticală
	dir_light.transform.origin = Vector3(50, 50, 100)  # Lumina sus și diagonal
	dir_light.rotation_degrees = Vector3(-45, -45, 0)  # Orientare diagonală în jos
	add_child(dir_light)
	print("[DEBUG] DirectionalLight3D added at position:", dir_light.transform.origin)
	if canvas == null:
		var cl = CanvasLayer.new()
		add_child(cl)
		canvas = cl

	default_material = StandardMaterial3D.new()
	default_material.albedo_color = Color(0.5, 1.0, 0.0) # lime green

	# Încarcă config materiale layere
	var config_path = "res://layer_materials.json"

	if FileAccess.file_exists(config_path):
		var config_str = FileAccess.get_file_as_string(config_path)
		var config_data = JSON.parse_string(config_str)
		if typeof(config_data) == TYPE_DICTIONARY:
			layer_materials = config_data

	# Normalizează structura layer_materials (acceptă și array direct din CSV/JSON)
	for k in layer_materials.keys():
		var v = layer_materials[k]
		if v is Array and v.size() == 4:
			layer_materials[k] = {"color": [v[0], v[1], v[2]], "alpha": v[3]}

	_set_top_view()
	print("[DEBUG] Camera set to top view")

	var env = Environment.new()
	env.background_color = background_color
	env.background_mode = Environment.BG_COLOR
	camera.environment = env
	print("[DEBUG] Environment configured with background color:", background_color)

	print("[DEBUG] Creating infinite grid...")
	_create_infinite_grid()
	print("[DEBUG] Creating center lines...")
	_create_center_lines(50)
	print("[DEBUG] Setting up UI buttons...")
	_setup_ui_buttons()
	print("[DEBUG] Setting up coordinate label...")
	_setup_coordinate_label()
	print("[DEBUG] Setting up grid controls...")
	_setup_grid_controls()
	print("[DEBUG] Updating camera clipping...")
	_update_camera_clipping()
	print("[DEBUG] Creating snap preview marker...")
	_create_snap_preview_marker()
	print("=== CAD VIEWER 3D - SCENE STARTUP COMPLETE ===")
	print("[DEBUG] Final grid state - infinite_grid node:", infinite_grid != null, "visible:", infinite_grid.visible if infinite_grid else "N/A")
	
	# Integrare Export IFC Button
	var export_ifc_btn = $CanvasLayer/ExportIfcBtn if has_node("CanvasLayer/ExportIfcBtn") else null
	if export_ifc_btn:
		export_ifc_btn.pressed.connect(_on_export_ifc_btn_pressed)
	
	# Integrare Export Multi-Level IFC Button
	var export_multi_ifc_btn = $CanvasLayer/ExportMultiIfcBtn if has_node("CanvasLayer/ExportMultiIfcBtn") else null
	if export_multi_ifc_btn:
		export_multi_ifc_btn.pressed.connect(_on_export_multi_ifc_btn_pressed)

	print("[DEBUG] 🔥🔥🔥 READY TO MOVE TO UI INTEGRATION SECTION 🔥🔥🔥")
	print("[DEBUG] *** STEP 9: Moving to UI integration section ***")
	
	# DEBUGGING CRITICAL: Salvează în fișier pentru a vedea dacă se ajunge aici
	var debug_file = FileAccess.open("user://debug_ready_log.txt", FileAccess.WRITE)
	if debug_file:
		debug_file.store_line("STEP 9: UI integration section reached at " + str(Time.get_unix_time_from_system()))
		debug_file.close()
	
	# Conectează semnale pentru Tree (Objects)
	print("[DEBUG] *** STEP 10: Connecting Tree signals ***")
	var tree_node = get_node_or_null("Objects")
	if tree_node:
		tree_node.connect("item_selected", Callable(self, "_on_tree_item_selected"))
		tree_node.connect("item_edited", Callable(self, "_on_tree_item_edited"))
		print("[DEBUG] ✓ Tree signals connected")
	else:
		print("[DEBUG] ✗ Tree node not found")

	print("[DEBUG] *** STEP 11: Starting UI integration ***")
	# Integrare LoadDxfBtn
	print("[DEBUG] *** SEARCHING FOR LoadDxfBtn ***")
	
	# DEBUGGING CRITICAL: Salvează în fișier progresul
	var debug_file2 = FileAccess.open("user://debug_ready_log.txt", FileAccess.WRITE_READ)
	if debug_file2:
		debug_file2.seek_end()
		debug_file2.store_line("STEP 11: Searching for LoadDxfBtn at " + str(Time.get_unix_time_from_system()))
		debug_file2.close()
	
	var load_btn = $CanvasLayer/LoadDxfBtn if has_node("CanvasLayer/LoadDxfBtn") else null
	if load_btn:
		print("[DEBUG] ✓ LoadDxfBtn found, connecting...")
		load_btn.pressed.connect(_on_load_dxf_btn_pressed)
		print("[DEBUG] ✓ LoadDxfBtn connected successfully")
	else:
		print("[ERROR] ✗ LoadDxfBtn NOT FOUND!")
	
	# Conectează FileDialog-ul existent din scenă
	print("[DEBUG] *** SEARCHING FOR DxfFolderDialog ***")
	print("[DEBUG] Checking path: CanvasLayer/DxfFolderDialog")
	print("[DEBUG] has_node result:", has_node("CanvasLayer/DxfFolderDialog"))
	
	# DEBUGGING CRITICAL: Salvează în fișier progresul
	var debug_file3 = FileAccess.open("user://debug_ready_log.txt", FileAccess.WRITE_READ)
	if debug_file3:
		debug_file3.seek_end()
		debug_file3.store_line("STEP 12: Searching for DxfFolderDialog - has_node result: " + str(has_node("CanvasLayer/DxfFolderDialog")) + " at " + str(Time.get_unix_time_from_system()))
		debug_file3.close()
	var file_dialog = $CanvasLayer/DxfFolderDialog if has_node("CanvasLayer/DxfFolderDialog") else null
	if file_dialog:
		print("[DEBUG] FileDialog found during initialization!")
		print("[DEBUG] FileDialog class:", file_dialog.get_class())
		print("[DEBUG] FileDialog file_mode:", file_dialog.file_mode)
		print("[DEBUG] FileDialog access:", file_dialog.access)
		
		# Listează toate semnalele disponibile
		print("[DEBUG] Available signals:")
		var signal_list = file_dialog.get_signal_list()
		for signal_info in signal_list:
			print("[DEBUG] - Signal:", signal_info.name)
		
		# În Godot 4, pentru FILE_MODE_OPEN_DIR, semnalul poate fi diferit
		if file_dialog.has_signal("dir_selected"):
			file_dialog.dir_selected.connect(Callable(self, "_on_dxf_folder_selected"))
			print("[DEBUG] FileDialog dir_selected connected successfully")
		elif file_dialog.has_signal("files_selected"):
			file_dialog.files_selected.connect(Callable(self, "_on_dxf_files_selected"))
			print("[DEBUG] FileDialog files_selected connected successfully")
		elif file_dialog.has_signal("file_selected"):
			file_dialog.file_selected.connect(Callable(self, "_on_dxf_file_selected"))
			print("[DEBUG] FileDialog file_selected connected successfully")
		else:
			print("[ERROR] No suitable signal found on FileDialog")
		
		# Debug info despre FileDialog
		print("[DEBUG] FileDialog file_mode:", file_dialog.file_mode)
		print("[DEBUG] FileDialog access:", file_dialog.access)
		print("[DEBUG] Available signals:", file_dialog.get_signal_list())
	else:
		print("[ERROR] DxfFolderDialog not found in scene!")
	
	print("[DEBUG] *** STEP 12: FileDialog section completed ***")
	
	# Integrare ReloadBtn
	print("[DEBUG] *** STEP 13: Searching for ReloadBtn ***")
	var reload_btn = $CanvasLayer/ReloadBtn if has_node("CanvasLayer/ReloadBtn") else null
	if reload_btn:
		reload_btn.pressed.connect(_on_reload_btn_pressed)
	
	# Integrare Cut Shader System
	_setup_cut_shader_integration()
	
	print("[DEBUG] *** ALL INITIALIZATION COMPLETE - SETTING UP WATCHDOG ***")
	# Watchdog pentru monitorizarea automată a fișierelor DXF (la sfârșit să nu blocheze inițializarea)
	_setup_dxf_watchdog()

# === DXF to GLB batch import ===
func _on_load_dxf_btn_pressed():
	print("[DEBUG] *** LOAD DXF BUTTON PRESSED ***")
	print("[DEBUG] 🔥 BUTTON CLICK CONFIRMED - FUNCTION IS WORKING! 🔥")
	
	# Salvează în fișier pentru debugging
	var debug_file = FileAccess.open("user://button_press_log.txt", FileAccess.WRITE)
	if debug_file:
		debug_file.store_line("Button pressed at: " + str(Time.get_unix_time_from_system()))
		debug_file.close()
	
	print("[DEBUG] Checking for FileDialog...")
	
	var file_dialog = $CanvasLayer/DxfFolderDialog if has_node("CanvasLayer/DxfFolderDialog") else null
	if file_dialog:
		print("[DEBUG] FileDialog found!")
		print("[DEBUG] FileDialog type:", file_dialog.get_class())
		print("[DEBUG] FileDialog file_mode:", file_dialog.file_mode)
		print("[DEBUG] FileDialog access:", file_dialog.access)
		print("[DEBUG] FileDialog current_dir:", file_dialog.current_dir)
		
		# Verifică conexiunile de semnal
		var connections = file_dialog.get_signal_connection_list("dir_selected")
		print("[DEBUG] dir_selected connections:", connections.size())
		for connection in connections:
			print("[DEBUG] - Connected to:", connection.callable.get_object(), "method:", connection.callable.get_method())
		
		# TEST RUNTIME: Forțează reconnectarea semnalului
		if connections.size() == 0:
			print("[DEBUG] Nu există conexiuni - conectez semnalul în runtime...")
			file_dialog.dir_selected.connect(Callable(self, "_on_dxf_folder_selected"))
			print("[DEBUG] Semnal conectat cu succes în runtime!")
		else:
			print("[DEBUG] Există", connections.size(), "conexiuni existente")
		
		# Verifică din nou după reconnectare
		connections = file_dialog.get_signal_connection_list("dir_selected")
		print("[DEBUG] dir_selected connections DUPĂ reconnectare:", connections.size())
		
		# BACKUP: Conectează și alte semnale pentru debugging
		if not file_dialog.file_selected.is_connected(_on_backup_file_selected):
			file_dialog.file_selected.connect(_on_backup_file_selected)
			print("[DEBUG] Conectat backup semnal file_selected")
		
		if not file_dialog.files_selected.is_connected(_on_backup_files_selected):
			file_dialog.files_selected.connect(_on_backup_files_selected)
			print("[DEBUG] Conectat backup semnal files_selected")
		
		print("[DEBUG] Opening FileDialog popup...")
		file_dialog.popup_centered(Vector2i(800, 600))
		print("[DEBUG] FileDialog should be visible now")
	else:
		print("[ERROR] DxfFolderDialog not found!")
		print("[DEBUG] Available CanvasLayer children:")
		if has_node("CanvasLayer"):
			var canvas = $CanvasLayer
			for child in canvas.get_children():
				print("[DEBUG] - Child:", child.name, "type:", child.get_class())
		push_error("DxfFolderDialog not found!")

func _on_dxf_folder_selected(dir_path):
	print("[DEBUG] *** _on_dxf_folder_selected CALLED ***")
	print("[DEBUG] Folder selectat:", dir_path)
	print("[DEBUG] Folder exists:", DirAccess.open(dir_path) != null)
	
	# Salvează folderul curent pentru reload
	current_project_folder = dir_path
	
	# Verifică conținutul folderului
	var dir = DirAccess.open(dir_path)
	if dir:
		var dxf_count = 0
		var glb_count = 0
		var diagram_count = 0
		dir.list_dir_begin()
		var file_name = dir.get_next()
		while file_name != "":
			if file_name.to_lower().ends_with(".dxf"):
				dxf_count += 1
			elif file_name.to_lower().ends_with(".glb"):
				glb_count += 1
			elif file_name.to_lower() == "diagram.xml":
				diagram_count += 1
			file_name = dir.get_next()
		dir.list_dir_end()
		print("[DEBUG] Found in folder - DXF:", dxf_count, " GLB:", glb_count, " Diagram.xml:", diagram_count)
	
	_process_dxf_folder(dir_path)

# Funcții alternative pentru diferite semnale de FileDialog
func _on_dxf_files_selected(files: PackedStringArray):
	print("[DEBUG] *** _on_dxf_files_selected CALLED ***")
	print("[DEBUG] Files selected:", files)
	if files.size() > 0:
		var dir_path = files[0].get_base_dir()
		print("[DEBUG] Extracted directory:", dir_path)
		_on_dxf_folder_selected(dir_path)

func _on_dxf_file_selected(file_path: String):
	print("[DEBUG] *** _on_dxf_file_selected CALLED ***")
	print("[DEBUG] File selected:", file_path)
	var dir_path = file_path.get_base_dir()
	print("[DEBUG] Extracted directory:", dir_path)
	_on_dxf_folder_selected(dir_path)

# Funcții de backup pentru debugging FileDialog
func _on_backup_file_selected(file_path: String):
	print("[DEBUG] *** BACKUP _on_backup_file_selected CALLED ***")
	print("[DEBUG] Backup file selected:", file_path)
	var dir_path = file_path.get_base_dir()
	print("[DEBUG] Redirecting to folder processing:", dir_path)
	_on_dxf_folder_selected(dir_path)

func _on_backup_files_selected(files: PackedStringArray):
	print("[DEBUG] *** BACKUP _on_backup_files_selected CALLED ***")
	print("[DEBUG] Backup files selected:", files.size(), "files")
	if files.size() > 0:
		var dir_path = files[0].get_base_dir()
		print("[DEBUG] Redirecting to folder processing:", dir_path)
		_on_dxf_folder_selected(dir_path)

func _on_reload_btn_pressed():
	if current_project_folder == "":
		print("[DEBUG] No project folder selected. Use Load DXF first.")
		return
	
	print("[DEBUG] Reloading project folder:", current_project_folder)
	# Șterge toate mesh-urile existente
	_clear_all_imported_projects()
	
	# Curăță cache-ul ResourceLoader și fișierele .import pentru toate GLB-urile din folder
	_clear_glb_cache_and_imports_for_folder(current_project_folder)
	
	# Așteaptă mai multe frame-uri pentru cleanup complet
	await get_tree().process_frame
	await get_tree().process_frame
	await get_tree().process_frame
	
	# Reprocessează folderul
	_process_dxf_folder(current_project_folder)

func _process_dxf_folder(dir_path: String):
	print("[DEBUG] *** _process_dxf_folder STARTED ***")
	print("[DEBUG] Processing folder:", dir_path)
	
	var dir = DirAccess.open(dir_path)
	if not dir:
		print("[ERROR] Could not open directory:", dir_path)
		return
	
	print("[DEBUG] Directory opened successfully")
	dir.list_dir_begin()
	var file_name = dir.get_next()
	var glb_paths = []
	var dxf_files_found = []
	var diagram_files_found = []
	
	while file_name != "":
		if not dir.current_is_dir():
			print("[DEBUG] Found file:", file_name)
			if file_name.to_lower().ends_with(".dxf"):
				dxf_files_found.append(file_name)
				var dxf_path = dir_path + "/" + file_name
				var glb_path = dir_path + "/" + file_name.get_basename() + ".glb"
				print("[DEBUG] Will convert DXF:", dxf_path, " -> ", glb_path)
			elif file_name.to_lower() == "diagram.xml":
				diagram_files_found.append(file_name)
				var xml_path = dir_path + "/" + file_name
				var glb_path = dir_path + "/model.glb"  # Standard name for diagram models
				print("[DEBUG] Will convert Diagram.xml:", xml_path, " -> ", glb_path)
		file_name = dir.get_next()
	dir.list_dir_end()
	
	print("[DEBUG] Found", dxf_files_found.size(), "DXF files:", dxf_files_found)
	print("[DEBUG] Found", diagram_files_found.size(), "Diagram.xml files:", diagram_files_found)
	
	# Procesează fiecare fișier DXF
	for dxf_file in dxf_files_found:
		var dxf_path = dir_path + "/" + dxf_file
		var glb_path = dir_path + "/" + dxf_file.get_basename() + ".glb"
		
		print("[DEBUG] Converting DXF:", dxf_path, "->", glb_path)
		var exit_code = _run_python_dxf_to_glb(dxf_path, glb_path)
		print("[DEBUG] DXF Conversion exit code:", exit_code)
		
		if FileAccess.file_exists(glb_path):
			print("[DEBUG] GLB file created successfully:", glb_path)
			glb_paths.append(glb_path)
		else:
			print("[ERROR] GLB file not created:", glb_path)
	
	# Procesează fiecare fișier Diagram.xml
	for diagram_file in diagram_files_found:
		var xml_path = dir_path + "/" + diagram_file
		var glb_path = dir_path + "/model.glb"
		var obj_path = dir_path + "/model.obj"
		
		# Verifică dacă există deja GLB generat
		if FileAccess.file_exists(glb_path):
			print("[DEBUG] Found existing GLB from Diagram.xml:", glb_path)
			# Verifică dacă XML-ul e mai recent decât GLB-ul (re-generare necesară)
			var xml_time = FileAccess.get_modified_time(xml_path)
			var glb_time = FileAccess.get_modified_time(glb_path)
			
			if xml_time > glb_time:
				print("[DEBUG] Diagram.xml is newer, re-converting...")
				var exit_code = _run_python_diagram_to_glb(xml_path, glb_path, obj_path)
				print("[DEBUG] Diagram re-conversion exit code:", exit_code)
			else:
				print("[DEBUG] Using existing GLB (up-to-date)")
			
			glb_paths.append(glb_path)
		else:
			# Generează GLB din Diagram.xml
			print("[DEBUG] Converting Diagram.xml:", xml_path, "->", glb_path)
			var exit_code = _run_python_diagram_to_glb(xml_path, glb_path, obj_path)
			print("[DEBUG] Diagram conversion exit code:", exit_code)
			
			if FileAccess.file_exists(glb_path):
				print("[DEBUG] GLB file created successfully from Diagram.xml:", glb_path)
				glb_paths.append(glb_path)
			else:
				print("[ERROR] GLB file not created from Diagram.xml:", glb_path)
	
	print("[DEBUG] Total GLB files to load:", glb_paths.size())
	if glb_paths.size() > 0:
		print("[DEBUG] Starting GLB loading...")
		_load_glb_meshes(glb_paths)
	else:
		print("[WARNING] No GLB files to load")

func _run_python_dxf_to_glb(dxf_path: String, glb_path: String):
	var script_path = "python/dxf_to_glb_trimesh.py"
	var args = [script_path, dxf_path, glb_path]
	var output = []
	print("[DEBUG] Running Python: python ", args)
	var exit_code = OS.execute("python", args, output, true)
	print("[PYTHON OUTPUT]", output)
	print("[PYTHON EXIT CODE]", exit_code)
	return exit_code


func _run_python_diagram_to_glb(xml_path: String, glb_path: String, obj_path: String):
	"""Convert Diagram.xml to GLB using graph_to_glb.py"""
	var script_path = "python/graph_to_glb.py"
	
	# Create a temporary Python script that calls export_to_glb with the right paths
	var temp_script = """
import sys
sys.path.insert(0, 'python')
from graph_to_glb import export_to_glb

xml_path = sys.argv[1]
glb_path = sys.argv[2]
obj_path = sys.argv[3]

try:
	export_to_glb(xml_path, glb_path, obj_path)
	print('[SUCCESS] Diagram.xml converted to GLB')
except Exception as e:
	print('[ERROR] Conversion failed:', e)
	import traceback
	traceback.print_exc()
	sys.exit(1)
"""
	
	# Write temp script
	var temp_script_path = "python/temp_convert_diagram.py"
	var file = FileAccess.open(temp_script_path, FileAccess.WRITE)
	if file:
		file.store_string(temp_script)
		file.close()
	else:
		print("[ERROR] Could not create temp script")
		return 1
	
	# Run the conversion
	var args = [temp_script_path, xml_path, glb_path, obj_path]
	var output = []
	print("[DEBUG] Running Python diagram converter: python ", args)
	var exit_code = OS.execute("python", args, output, true)
	print("[PYTHON OUTPUT]", output)
	print("[PYTHON EXIT CODE]", exit_code)
	
	# Clean up temp script
	if FileAccess.file_exists(temp_script_path):
		DirAccess.remove_absolute(temp_script_path)
	
	return exit_code


func _load_glb_meshes(glb_paths: Array):
	for glb_path in glb_paths:
		if FileAccess.file_exists(glb_path):
			print("[DEBUG] Loading GLB with forced reimport: ", glb_path)
			
			# Asigură-te că fișierul este complet scris
			var file_size = _get_file_size(glb_path)
			if file_size < 100:
				print("[DEBUG] Waiting for GLB file to be completely written...")
				await get_tree().create_timer(0.3).timeout
			
			# Forțează ștergerea cache-ului și fișierelor .import
			_force_clear_resource_cache(glb_path)
			_force_delete_import_files(glb_path)
			
			# Modifică timestamp-ul pentru reimport
			_touch_file_for_reimport(glb_path)
			
			# Încarcă cu sistema robustă de retry
			var success = await _load_glb_with_retry(glb_path)
			if not success:
				print("[ERROR] GLTF/GLB import failed after retries: ", glb_path)
		else:
			print("[ERROR] GLTF/GLB file not found: ", glb_path)
	
	# Populează tree-ul după import
	populate_tree_with_projects(imported_projects)

func _load_window_gltf_for_glb(glb_path: String):
	"""Încarcă ferestrele GLTF pentru un fișier GLB bazat pe mapping-ul JSON"""
	var mapping_path = glb_path.get_basename() + "_mapping.json"
	
	if not FileAccess.file_exists(mapping_path):
		print("[DEBUG] No mapping file found: ", mapping_path)
		return
	
	var mapping_file = FileAccess.open(mapping_path, FileAccess.READ)
	if not mapping_file:
		print("[ERROR] Cannot open mapping file: ", mapping_path)
		return
	
	var json_str = mapping_file.get_as_text()
	mapping_file.close()
	
	var json = JSON.new()
	var parse_result = json.parse(json_str)
	if parse_result != OK:
		print("[ERROR] Failed to parse mapping JSON: ", mapping_path)
		return
	
	var mapping_data = json.data
	if typeof(mapping_data) != TYPE_ARRAY:
		print("[ERROR] Invalid mapping data format")
		return
	
	# Procesează fiecare entry din mapping
	for entry in mapping_data:
		if typeof(entry) != TYPE_DICTIONARY:
			continue
		
		# Verifică dacă este un bloc de fereastră
		if entry.get("type", "") == "window_block":
			_load_single_window_gltf(entry, glb_path)

func _load_single_window_gltf(window_entry: Dictionary, source_glb_path: String):
	"""Încarcă o singură fereastră GLTF și o poziționează în scenă"""
	var gltf_file = window_entry.get("gltf_file", "")
	var window_name = window_entry.get("window_name", "UnknownWindow")
	var position = window_entry.get("position", {"x": 0.0, "y": 0.0, "z": 0.0})
	var rotation = window_entry.get("rotation", {"z": 0.0})
	var scale = window_entry.get("scale", {"x": 1.0, "y": 1.0, "z": 1.0})
	
	# Construiește calea completă la fișierul GLTF
	var full_gltf_path = gltf_file
	
	# Încearcă mai întâi ca resursă Godot (res://)
	if not full_gltf_path.begins_with("res://"):
		full_gltf_path = "res://" + gltf_file
	
	# Dacă nu există ca resursă, încearcă calea absolută în sistemul de fișiere
	if not ResourceLoader.exists(full_gltf_path) and not FileAccess.file_exists(full_gltf_path):
		# Încearcă calea relativă față de folderul curent al proiectului
		var project_relative_path = ProjectSettings.globalize_path("res://") + gltf_file
		if FileAccess.file_exists(project_relative_path):
			full_gltf_path = project_relative_path
	
	print("[DEBUG] Loading window GLTF: ", full_gltf_path)
	print("[DEBUG] Position: (%.2f, %.2f, %.2f), Rotation: %.1f°" % [position.x, position.y, position.z, rotation.z])
	
	# Verifică dacă fișierul GLTF există
	if not FileAccess.file_exists(full_gltf_path) and not ResourceLoader.exists(full_gltf_path):
		print("[ERROR] Window GLTF file not found: ", full_gltf_path)
		return
	
	# Încarcă scena GLTF
	var window_scene = ResourceLoader.load(full_gltf_path, "", ResourceLoader.CACHE_MODE_REUSE)
	if not window_scene or not window_scene is PackedScene:
		print("[ERROR] Failed to load window GLTF as PackedScene: ", full_gltf_path)
		return
	
	# Instanțiază scena
	var window_instance = window_scene.instantiate()
	if not window_instance:
		print("[ERROR] Failed to instantiate window scene")
		return
	
	# Setează poziția
	window_instance.transform.origin = Vector3(position.x, position.y, position.z)
	
	# Setează rotația (doar în jurul axei Z pentru ferestre)
	if rotation.z != 0.0:
		window_instance.transform.basis = Basis()
		window_instance.transform.basis = window_instance.transform.basis.rotated(Vector3(0, 0, 1), deg_to_rad(rotation.z))
	
	# Setează scala dacă este diferită de default
	if scale.x != 1.0 or scale.y != 1.0 or scale.z != 1.0:
		window_instance.scale = Vector3(scale.x, scale.y, scale.z)
	
	# Setează numele pentru identificare
	window_instance.name = window_name
	
	# Adaugă la scenă
	add_child(window_instance)
	
	# Adaugă în structura imported_projects pentru managementul în tree
	var glb_filename = source_glb_path.get_file()
	if not imported_projects.has(glb_filename):
		imported_projects[glb_filename] = {}
	if not imported_projects[glb_filename].has("IfcWindow"):
		imported_projects[glb_filename]["IfcWindow"] = {}
	imported_projects[glb_filename]["IfcWindow"][window_name] = window_instance
	
	print("[DEBUG] WINDOW LOADED: %s | GLTF: %s | Pos: (%.2f, %.2f, %.2f) | Rot: %.1f° | Visible: %s" % [
		window_name, 
		full_gltf_path.get_file(), 
		position.x, position.y, position.z, 
		rotation.z, 
		str(window_instance.visible)
	])

func _load_mapping_metadata_for_glb(glb_path: String, scene_root: Node3D):
	"""Încarcă metadata din fișierul de mapping și o atașează la mesh-uri pentru export IFC"""
	var mapping_path = glb_path.get_basename() + "_mapping.json"
	
	if not FileAccess.file_exists(mapping_path):
		print("[DEBUG] No mapping file found for metadata: ", mapping_path)
		return
	
	var mapping_file = FileAccess.open(mapping_path, FileAccess.READ)
	if not mapping_file:
		print("[ERROR] Cannot open mapping file for metadata: ", mapping_path)
		return
	
	var json_str = mapping_file.get_as_text()
	mapping_file.close()
	
	var json = JSON.new()
	var parse_result = json.parse(json_str)
	if parse_result != OK:
		print("[ERROR] Failed to parse mapping JSON for metadata: ", mapping_path)
		return
	
	var mapping_data = json.data
	if typeof(mapping_data) != TYPE_ARRAY:
		print("[ERROR] Invalid mapping data format for metadata")
		return
	
	print("[DEBUG] Loading metadata from mapping for %d entries" % mapping_data.size())
	
	# Creează un dicționar pentru căutare rapidă după mesh_name
	var mapping_by_name = {}
	for entry in mapping_data:
		if typeof(entry) == TYPE_DICTIONARY:
			var mesh_name = entry.get("mesh_name", "")
			if mesh_name != "":
				mapping_by_name[mesh_name] = entry
	
	# Aplică metadata la toate mesh-urile din scenă
	_apply_metadata_recursive(scene_root, mapping_by_name)

func _apply_metadata_recursive(node: Node, mapping_by_name: Dictionary):
	"""Aplică recursiv metadata la mesh-uri din mapping"""
	if node is MeshInstance3D:
		var mesh_name = str(node.name)
		
		# Caută în mapping după numele exact
		if mapping_by_name.has(mesh_name):
			var entry = mapping_by_name[mesh_name]
			_apply_metadata_to_mesh(node, entry)
		else:
			# Încearcă căutare parțială pentru mesh-uri cu nume modificate
			for key in mapping_by_name.keys():
				if mesh_name in key or key in mesh_name:
					var entry = mapping_by_name[key]
					_apply_metadata_to_mesh(node, entry)
					break
	
	# Recursiv în copii
	for child in node.get_children():
		_apply_metadata_recursive(child, mapping_by_name)

func _apply_metadata_to_mesh(mesh_node: MeshInstance3D, mapping_entry: Dictionary):
	"""Aplică metadata din mapping la un mesh"""
	# Metadata de bază
	mesh_node.set_meta("uuid", mapping_entry.get("uuid", ""))
	mesh_node.set_meta("layer", mapping_entry.get("layer", "default"))
	mesh_node.set_meta("mesh_name", mapping_entry.get("mesh_name", ""))
	
	# Proprietăți geometrice pentru IfcSpace
	var layer = mapping_entry.get("layer", "")
	if layer == "IfcSpace":
		mesh_node.set_meta("area", mapping_entry.get("area", 0.0))
		mesh_node.set_meta("perimeter", mapping_entry.get("perimeter", 0.0))
		mesh_node.set_meta("lateral_area", mapping_entry.get("lateral_area", 0.0))
		mesh_node.set_meta("volume", mapping_entry.get("volume", 0.0))
		mesh_node.set_meta("height", mapping_entry.get("height", 2.8))
		mesh_node.set_meta("vertices", mapping_entry.get("vertices", []))
		
		print("[DEBUG] Applied IfcSpace metadata to: %s | Area: %.2f | Volume: %.3f | UUID: %s" % [
			mapping_entry.get("mesh_name", ""),
			mapping_entry.get("area", 0.0),
			mapping_entry.get("volume", 0.0),
			mapping_entry.get("uuid", "")
		])

# Debug: Recursiv, afișează numele meshurilor și culoarea vertex principal (dacă există)
func _print_meshes_and_colors(node: Node, glb_path: String):

	if node is MeshInstance3D and node.mesh:
		var mesh_name = str(node.name)  # Convert StringName to String
		var mesh = node.mesh
		var color_str = "-"
		var layer_name = "default"
		
		# Extrage layer-ul din numele encodat (format: MeshName_LAYER_LayerName)
		var actual_layer = "default"
		if "_LAYER_" in mesh_name:
			var parts = mesh_name.split("_LAYER_")
			if parts.size() >= 2:
				actual_layer = parts[1]  # Layer-ul real din encoding
				print("[DEBUG] Detected encoded layer: %s from mesh: %s" % [actual_layer, mesh_name])
		else:
			# Fallback la metoda veche (prima parte până la _)
			if mesh_name.find("_") > 0:
				actual_layer = mesh_name.split("_")[0]
		
		# Verifică dacă mesh-ul are deja un material valid din GLB
		var existing_material = null
		var should_use_glb_material = false
		var material_source = "none"
		
		# Încearcă să găsească materialul din GLB în diferite locuri
		if node.mesh and node.mesh.get_surface_count() > 0:
			existing_material = node.mesh.surface_get_material(0)  # Material din mesh
			if existing_material != null:
				material_source = "mesh_surface"
		
		if existing_material == null and node.get_surface_count() > 0:
			existing_material = node.get_surface_override_material(0)  # Material override
			if existing_material != null:
				material_source = "surface_override"
		
		# De asemenea, verifică dacă există material override deja setat
		if existing_material == null and node.material_override != null:
			existing_material = node.material_override
			material_source = "material_override"
		
		print("[DEBUG] Material search for %s: source=%s, material=%s" % [mesh_name, material_source, existing_material])
		
		if existing_material != null:
			# Verifică dacă materialul din GLB are un nume care indică encoding-ul nostru
			var mat_name = existing_material.resource_name if existing_material else ""
			
			# Încearcă și numele materialului dacă resource_name nu există
			if mat_name == "" and existing_material.has_method("get_name"):
				mat_name = existing_material.get_name()
			
			print("[DEBUG] Found material name: '%s' (begins with Material_: %s)" % [mat_name, str(mat_name.begins_with("Material_"))])
			
			if mat_name != "" and mat_name.begins_with("Material_"):
				print("[DEBUG] ✓ Found GLB material with encoding: %s" % mat_name)
				should_use_glb_material = true
				
				# Încearcă să acceseze culoarea din material
				if existing_material is StandardMaterial3D:
					var std_mat = existing_material as StandardMaterial3D
					color_str = str(std_mat.albedo_color)
					print("[DEBUG] GLB StandardMaterial3D color: %s" % color_str)
				else:
					color_str = "GLB_Material(%s)" % existing_material.get_class()
					print("[DEBUG] GLB material type: %s" % existing_material.get_class())
			else:
				print("[DEBUG] ✗ Material name doesn't match encoding pattern: '%s'" % mat_name)
		
		# Doar suprascrie materialul dacă nu există unul valid din GLB
		if not should_use_glb_material:
			# Mapare insensibilă la majuscule/minuscule și fallback la 'default'
			var found_layer = ""
			for k in layer_materials.keys():
				if k.to_lower() == actual_layer.to_lower():
					found_layer = k
					break
			if found_layer == "":
				found_layer = "default"
			
			var lconf = layer_materials[found_layer]
			var mat = StandardMaterial3D.new()
			mat.albedo_color = Color(lconf["color"][0], lconf["color"][1], lconf["color"][2], lconf["alpha"])
			if lconf["alpha"] < 1.0:
				mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
			node.material_override = mat
			color_str = str(mat.albedo_color)
			print("[DEBUG] SCENE LOAD (Override): %s | Mesh: %s | Layer: %s->%s | Alpha: %.2f | Color: %s" % [glb_path, mesh_name, actual_layer, found_layer, lconf["alpha"], color_str])
		else:
			print("[DEBUG] SCENE LOAD (GLB Material): %s | Mesh: %s | Layer: %s | Material: %s | Color: %s | Preserved from GLB" % [glb_path, mesh_name, actual_layer, existing_material.resource_name if existing_material else "Unknown", color_str])
		
		# Setează layer_name pentru structura de date
		layer_name = actual_layer

		# --- Populare structură pentru tree ---
		if not imported_projects.has(glb_path):
			imported_projects[glb_path] = {}
		if not imported_projects[glb_path].has(layer_name):
			imported_projects[glb_path][layer_name] = {}
		imported_projects[glb_path][layer_name][mesh_name] = node

	for child in node.get_children():
		_print_meshes_and_colors(child, glb_path)

func _on_view_button_pressed(view_name: String):
	match view_name:
		"TOP": _set_top_view()
		"FRONT": _set_front_view()
		"LEFT": _set_left_view()
		"RIGHT": _set_right_view()
		"BACK": _set_back_view()
		"FREE 3D": _set_free_view()

# View functions
func _set_top_view():
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = 20
	camera.transform.origin = Vector3(0,0,10)
	camera.look_at(Vector3(0,0,0), Vector3(0,1,0))
	set_section_for_view("top")

func _set_front_view():
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = 20
	camera.transform.origin = Vector3(0,-10,0)
	camera.look_at(Vector3(0,0,0), Vector3(0,0,1))
	set_section_for_view("front")

func _set_left_view():
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = 20
	camera.transform.origin = Vector3(-10,0,0)
	camera.look_at(Vector3(0,0,0), Vector3(0,0,1))
	set_section_for_view("left")

func _set_right_view():
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = 20
	camera.transform.origin = Vector3(10,0,0)
	camera.look_at(Vector3(0,0,0), Vector3(0,0,1))
	set_section_for_view("right")

func _set_back_view():
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = 20
	camera.transform.origin = Vector3(0,10,0)
	camera.look_at(Vector3(0,0,0), Vector3(0,0,1))
	set_section_for_view("back")

func _set_free_view():
	camera.projection = Camera3D.PROJECTION_PERSPECTIVE
	camera.fov = 60
	camera.transform.origin = Vector3(10,10,10)
	camera.look_at(Vector3(0,0,0), Vector3(0,0,1))
	set_section_for_view("free")

func _on_fit_all_pressed():
	"""Încadrează toate obiectele în camera curentă"""
	var bbox = _calculate_scene_bounding_box()
	if bbox.has_volume():
		_fit_camera_to_bbox(bbox)
		print("[CADViewer] Fit All: fitted to bbox ", bbox)
	else:
		print("[CADViewer] Fit All: no objects found or invalid bbox")

func _calculate_scene_bounding_box() -> AABB:
	"""Calculează bounding box-ul întregii scene"""
	var combined_bbox = AABB()
	var first_object = true
	
	# Parcurge toate copiii pentru a găsi MeshInstance3D
	for child in get_children():
		if child is MeshInstance3D:
			var mesh_instance = child as MeshInstance3D
			if mesh_instance.mesh != null:
				var mesh_bbox = mesh_instance.get_aabb()
				# Transformă bbox-ul în spațiul global
				mesh_bbox = mesh_instance.transform * mesh_bbox
				
				if first_object:
					combined_bbox = mesh_bbox
					first_object = false
				else:
					combined_bbox = combined_bbox.merge(mesh_bbox)
	
	return combined_bbox

func _fit_camera_to_bbox(bbox: AABB):
	"""Pozitionează camera pentru a încadra bbox-ul"""
	var bbox_center = bbox.get_center()
	var bbox_size = bbox.size
	
	if camera.projection == Camera3D.PROJECTION_ORTHOGONAL:
		# Pentru camera ortogonală, calculează dimensiunea necesară
		var max_extent = max(bbox_size.x, max(bbox_size.y, bbox_size.z))
		camera.size = max_extent * 1.2  # 20% padding
		
		# Păstrează direcția curentă a camerei, dar centrează pe bbox
		var current_forward = -camera.transform.basis.z
		var distance = max_extent * 2.0  # Distanța optimă
		camera.transform.origin = bbox_center - current_forward * distance
		camera.look_at(bbox_center, Vector3.UP)
		
	else:
		# Pentru camera perspective
		var max_extent = bbox_size.length()
		var distance = max_extent * 1.5  # Distanța pentru perspective
		
		var current_forward = -camera.transform.basis.z
		camera.transform.origin = bbox_center - current_forward * distance
		camera.look_at(bbox_center, Vector3.UP)






# Grid creation
func _create_infinite_grid():
	"""Creează un grid infinit cu linii vizibile"""
	print("[GRID_DEBUG] Starting infinite grid creation...")
	print("[GRID_DEBUG] Grid parameters - size: 500, spacing:", grid_spacing, "z_position:", grid_z_position, "visible:", grid_visible)
	print("[GRID_DEBUG] Grid color:", grid_color)
	
	# Creează liniile grid-ului într-un mod dinamic și mare
	var grid_vertices = PackedVector3Array()
	var grid_colors = PackedColorArray()
	
	# Grid foarte mare pentru efectul "infinit"
	var grid_size = 500  # Mult mai mare decât înainte
	var spacing = grid_spacing
	
	# Linii pe X (paralele cu axa X)
	for i in range(-grid_size, grid_size + 1):
		grid_vertices.append(Vector3(-grid_size * spacing, i * spacing, grid_z_position))
		grid_vertices.append(Vector3(grid_size * spacing, i * spacing, grid_z_position))
		grid_colors.append(grid_color)
		grid_colors.append(grid_color)
	
	# Liniile pe Y (paralele cu axa Y) 
	for i in range(-grid_size, grid_size + 1):
		grid_vertices.append(Vector3(i * spacing, -grid_size * spacing, grid_z_position))
		grid_vertices.append(Vector3(i * spacing, grid_size * spacing, grid_z_position))
		grid_colors.append(grid_color)
		grid_colors.append(grid_color)
	
	# Creează mesh-ul
	var grid_arrays = []
	grid_arrays.resize(Mesh.ARRAY_MAX)
	grid_arrays[Mesh.ARRAY_VERTEX] = grid_vertices
	grid_arrays[Mesh.ARRAY_COLOR] = grid_colors
	var grid_mesh = ArrayMesh.new()
	grid_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_LINES, grid_arrays)
	
	# Creează material transparent
	grid_material = StandardMaterial3D.new()
	grid_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	grid_material.vertex_color_use_as_albedo = true
	grid_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	grid_material.no_depth_test = false
	grid_material.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_OPAQUE_ONLY
	
	# Creează instanța
	infinite_grid = MeshInstance3D.new()
	infinite_grid.mesh = grid_mesh
	infinite_grid.material_override = grid_material
	infinite_grid.position.z = grid_z_position
	infinite_grid.visible = grid_visible
	add_child(infinite_grid)
	
	print("[GRID_DEBUG] Infinite grid MeshInstance3D created successfully!")
	print("[GRID_DEBUG] Grid stats: ", grid_vertices.size() / 2, " lines, mesh surfaces:", grid_mesh.get_surface_count())
	print("[GRID_DEBUG] Grid position:", infinite_grid.position)
	print("[GRID_DEBUG] Grid visible:", infinite_grid.visible)
	print("[GRID_DEBUG] Grid material transparency:", grid_material.transparency)
	print("[GRID_DEBUG] Grid added to scene tree as child of:", get_name())
	print("[CADViewer] Infinite grid created with ", grid_vertices.size() / 2, " lines at Z=", grid_z_position)

func _create_center_lines(size: float):
	var mesh = ArrayMesh.new()
	var verts = PackedVector3Array([
		Vector3(-size, 0, drawing_plane_z), Vector3(size, 0, drawing_plane_z),
		Vector3(0, -size, drawing_plane_z), Vector3(0, size, drawing_plane_z)
	])
	var colors = PackedColorArray([
		Color.RED, Color.RED,
		Color.GREEN, Color.GREEN
	])
	var arrays = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = verts
	arrays[Mesh.ARRAY_COLOR] = colors
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_LINES, arrays)
	var axes = MeshInstance3D.new()
	axes.mesh = mesh
	add_child(axes)

# Input handling cu snap
func _unhandled_input(event):
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP:
			_zoom_at_mouse(1/zoom_speed)
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			_zoom_at_mouse(zoom_speed)
		elif event.button_index == MOUSE_BUTTON_MIDDLE:
			if event.pressed:
				pan_last_pos = event.position
				is_panning = true
			else:
				is_panning = false
		elif event.button_index == MOUSE_BUTTON_RIGHT:
			if event.pressed:
				rotate_last_pos = event.position
				is_rotating = true
				orbit_pivot = get_mouse_pos_in_xy()
			else:
				is_rotating = false

	if event is InputEventMouseMotion and is_panning:
		var delta = event.position - pan_last_pos
		if camera.projection == Camera3D.PROJECTION_ORTHOGONAL:
			var scale = camera.size / 200.0
			camera.translate(Vector3(-delta.x*scale, delta.y*scale, 0))
		else:
			var scale = 0.01 * camera.transform.origin.length()
			camera.translate(Vector3(-delta.x*scale, delta.y*scale, 0))
		pan_last_pos = event.position

	if event is InputEventMouseMotion and is_rotating and camera.projection == Camera3D.PROJECTION_PERSPECTIVE:
		var delta = event.position - rotate_last_pos
		_orbit_camera(delta, orbit_pivot)
		rotate_last_pos = event.position

	if event is InputEventMouseMotion:
		_update_coordinate_display()
		_update_snap_preview()

	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		if camera.projection == Camera3D.PROJECTION_ORTHOGONAL:
			var world_pos = get_mouse_pos_in_xy()
			var snapped_pos = get_snapped_position(world_pos)
			print("Mouse position: ", world_pos, " Snapped: ", snapped_pos)

	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		var ray_origin = camera.project_ray_origin(event.position)
		var ray_dir = camera.project_ray_normal(event.position)
		var space_state = get_world_3d().direct_space_state
		var ray_params = PhysicsRayQueryParameters3D.new()
		ray_params.from = ray_origin
		ray_params.to = ray_origin + ray_dir * 1000
		var result = space_state.intersect_ray(ray_params)
		if result and result.has("collider"):
			var collider = result["collider"]
			# Acceptă și CSGPolygon3D ca selectabil
			if collider.has_meta("selectable") and collider.get_meta("selectable"):
				if selected_geometry:
					var prev_csg = selected_geometry.get_child(0) if selected_geometry.get_child_count() > 0 else null
					if prev_csg and prev_csg.has_method("set"):
						var layer_name = prev_csg.get_meta("layer_name") if prev_csg.has_meta("layer_name") else "default"
						var mat = default_material
						if layer_materials.has(layer_name):
							var lconf = layer_materials[layer_name]
							mat = StandardMaterial3D.new()
							mat.albedo_color = Color(lconf["color"][0], lconf["color"][1], lconf["color"][2], lconf["alpha"])
							mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
						prev_csg.material_override = mat
				selected_geometry = collider
				var sel_mat = StandardMaterial3D.new()
				sel_mat.albedo_color = Color.YELLOW
				var csg = selected_geometry.get_child(0) if selected_geometry.get_child_count() > 0 else null
				if csg and csg.has_method("set"):
					csg.material_override = sel_mat
				print("[DEBUG] Selected geometry: ", selected_geometry)

	# === HOTKEYS ===
	# F - Fit All (Frame All objects)
	if event is InputEventKey and event.pressed:
		match event.keycode:
			KEY_F:  # Fit All (Frame All)
				_on_fit_all_pressed()

func _update_snap_preview():
	if not snap_enabled:
		snap_preview_marker.visible = false
		return
	
	var world_pos = get_mouse_pos_in_xy()
	var snapped_pos = get_snapped_position(world_pos)
	
	# Verifică dacă există un punct snap în apropiere
	if world_pos.distance_to(snapped_pos) < snap_distance:
		snap_preview_marker.transform.origin = snapped_pos
		snap_preview_marker.visible = true
	else:
		snap_preview_marker.visible = false

# Z-depth control callbacks
func _on_z_min_changed(value: float):
	z_min = value
	_update_camera_clipping()
	_update_info_label()

func _on_z_max_changed(value: float):
	z_max = value
	_update_camera_clipping()
	_update_info_label()

func _on_drawing_plane_z_changed(value: float):
	drawing_plane_z = value
	_update_drawing_plane_visual()

func _set_ground_level():
	drawing_plane_z = 0.0
	z_min = -2.0
	z_max = 5.0
	_update_z_spinboxes()
	_update_camera_clipping()
	_update_drawing_plane_visual()

func _set_floor1_level():
	drawing_plane_z = 3.0
	_update_camera_clipping()
	_update_drawing_plane_visual()



func _update_camera_clipping():
	if camera.projection == Camera3D.PROJECTION_ORTHOGONAL:
		camera.near = 0.01  # Mai aproape pentru detalii fine
		# Far mult mai mare pentru a permite zoom out extrem
		var dynamic_far = max(1000.0, camera.size * 10.0)  # Se adaptează la nivelul de zoom
		camera.far = dynamic_far
		print("[DEBUG] Orthogonal camera: size=%.2f, near=%.2f, far=%.2f" % [camera.size, camera.near, camera.far])
	else:
		camera.near = 0.01
		camera.far = 10000.0  # Mult mai mare pentru perspective

func _update_drawing_plane_visual():
	# Pentru grid infinit, doar actualizăm poziția Z
	if infinite_grid:
		infinite_grid.position.z = grid_z_position

func _clear_grid_and_axes():
	for child in get_children():
		if child is MeshInstance3D and child != camera and child != snap_preview_marker and child != infinite_grid:
			child.queue_free()

func _update_coordinate_display():
	var world_pos = get_mouse_pos_in_xy()
	coord_label.text = "X: %.2f, Y: %.2f, Z: %.2f" % [world_pos.x, world_pos.y, grid_z_position]

func _zoom_at_mouse(factor: float):
	var world_before = get_mouse_pos_in_xy()
	if camera.projection == Camera3D.PROJECTION_ORTHOGONAL:
		var new_size = camera.size * factor
		# Limitează zoom-ul între min și max
		new_size = clamp(new_size, min_orthogonal_size, max_orthogonal_size)
		camera.size = new_size
		# Actualizează limitele de clipping după zoom
		_update_camera_clipping()
		var world_after = get_mouse_pos_in_xy()
		var offset = world_before - world_after
		camera.translate(Vector3(offset.x, offset.y, 0))
	else:
		var target = world_before
		var dir = (target - camera.transform.origin).normalized()
		var dist = camera.transform.origin.distance_to(target)
		camera.transform.origin += dir * (1.0 - 1.0/factor) * dist
		# Actualizează limitele de clipping și pentru perspective
		_update_camera_clipping()

func _orbit_camera(delta: Vector2, pivot: Vector3):
	var origin = camera.transform.origin
	var distance = origin.distance_to(pivot)

	var yaw = -delta.x * 0.01
	var pitch = -delta.y * 0.01

	var dir = (origin - pivot).normalized()
	var basis = Basis()
	basis = basis.rotated(Vector3(0,0,1), yaw)
	basis = basis.rotated(Vector3(1,0,0), pitch)
	dir = basis * dir

	camera.transform.origin = pivot + dir * distance
	camera.look_at(pivot, Vector3(0,0,1))

func get_mouse_pos_in_xy() -> Vector3:
	var viewport = get_viewport()
	var mouse_pos = viewport.get_mouse_position()
	var from = camera.project_ray_origin(mouse_pos)
	var dir = camera.project_ray_normal(mouse_pos)
	if dir.z == 0:
		return Vector3(0, 0, drawing_plane_z)
	var t = -(from.z - drawing_plane_z) / dir.z
	var result = from + dir * t
	result.z = drawing_plane_z
	return result
				

func populate_tree_with_projects(projects: Dictionary):
	print("[DEBUG] === POPULATING TREE WITH PROJECTS ===")
	print("[DEBUG] Projects structure: ", projects.keys())
	
	var tree_node = get_node_or_null("Objects")
	if tree_node == null:
		print("[ERROR] Nu există nodul Objects de tip Tree în scenă!")
		return
		
	print("[DEBUG] Tree node found successfully: ", tree_node)
	tree_node.clear()
	tree_node.set_columns(2)
	var root = tree_node.create_item()
	tree_node.set_column_title(0, "GLB File / IfcType / Element")
	tree_node.set_column_title(1, "Visible")
	tree_node.set_column_titles_visible(true)
	
	print("[DEBUG] Tree setup complete, columns: ", tree_node.columns)

	for file_name in projects.keys():
		print("[DEBUG] Creating file item: ", file_name)
		var file_item = tree_node.create_item(root)
		file_item.set_text(0, file_name)
		file_item.set_cell_mode(1, TreeItem.CELL_MODE_CHECK)
		file_item.set_checked(1, true)
		file_item.set_editable(1, true)
		var file_metadata = {"type": "file", "file": file_name}
		file_item.set_metadata(0, file_metadata)
		print("[DEBUG] File item created with metadata: ", file_metadata)

		var layer_groups = projects[file_name]
		for layer_group in layer_groups.keys():
			var group_item = tree_node.create_item(file_item)
			group_item.set_text(0, layer_group)
			group_item.set_cell_mode(1, TreeItem.CELL_MODE_CHECK)
			group_item.set_checked(1, true)
			group_item.set_editable(1, true)
			group_item.set_metadata(0, {"type": "group", "file": file_name, "group": layer_group})

			var elements = layer_groups[layer_group]
			for elem_name in elements.keys():
				var elem_item = tree_node.create_item(group_item)
				elem_item.set_text(0, elem_name)
				elem_item.set_cell_mode(1, TreeItem.CELL_MODE_CHECK)
				elem_item.set_checked(1, true)
				elem_item.set_editable(1, true)
				elem_item.set_metadata(0, {"type": "element", "file": file_name, "group": layer_group, "element": elem_name})

# --- Tree select & visibility logic ---
func _on_tree_item_selected():
	var tree_node = get_node_or_null("Objects")
	if not tree_node:
		return
	var item = tree_node.get_selected()
	if not item:
		return
	var meta = item.get_metadata(0)
	if typeof(meta) != TYPE_DICTIONARY:
		return
	if meta.has("type") and meta["type"] == "element":
		var file = meta["file"]
		var group = meta["group"]
		var elem = meta["element"]
		if imported_projects.has(file) and imported_projects[file].has(group) and imported_projects[file][group].has(elem):
			var node = imported_projects[file][group][elem]
			_highlight_selected_node(node)

func _highlight_selected_node(node):
	if not node:
		return
	# Reset previous selection
	if selected_geometry and selected_geometry != node:
		var mesh_name = selected_geometry.name
		var layer_name = mesh_name.split("_")[0] if mesh_name.find("_") > 0 else "default"
		var lconf = layer_materials.has(layer_name) if layer_materials.has(layer_name) else layer_materials["default"]
		var mat = StandardMaterial3D.new()
		mat.albedo_color = Color(lconf["color"][0], lconf["color"][1], lconf["color"][2], lconf["alpha"])
		if lconf["alpha"] < 1.0:
			mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		selected_geometry.material_override = mat
	# Highlight new selection
	selected_geometry = node
	var sel_mat = StandardMaterial3D.new()
	sel_mat.albedo_color = Color.YELLOW
	selected_geometry.material_override = sel_mat

func _on_tree_item_edited():
	print("[DEBUG] Tree item edited triggered!")
	
	var tree_node = get_node_or_null("Objects")
	if not tree_node:
		print("[ERROR] Tree node 'Objects' not found!")
		return
		
	var edited = tree_node.get_edited()
	if not edited:
		print("[ERROR] No edited item found!")
		return
		
	var meta = edited.get_metadata(0)
	if typeof(meta) != TYPE_DICTIONARY:
		print("[ERROR] Invalid metadata type: ", typeof(meta))
		return
		
	var checked = edited.is_checked(1)
	print("[DEBUG] Item edited: ", edited.get_text(0), " | Checked: ", checked, " | Type: ", meta.get("type", "unknown"))
	
	if meta.has("type"):
		match meta["type"]:
			"file":
				print("[DEBUG] Setting visibility for file: ", meta["file"], " to ", checked)
				_set_visibility_file(meta["file"], checked)
			"group":
				print("[DEBUG] Setting visibility for group: ", meta["group"], " in file: ", meta["file"], " to ", checked)
				_set_visibility_group(meta["file"], meta["group"], checked)
			"element":
				print("[DEBUG] Setting visibility for element: ", meta["element"], " in group: ", meta["group"], " file: ", meta["file"], " to ", checked)
				_set_visibility_element(meta["file"], meta["group"], meta["element"], checked)
	else:
		print("[ERROR] No 'type' in metadata: ", meta)

func _set_visibility_file(file, visible):
	print("[DEBUG] _set_visibility_file called for file: '%s', visible: %s" % [file, visible])
	print("[DEBUG] imported_projects has file: ", imported_projects.has(file))
	print("[DEBUG] Available files in imported_projects: ", imported_projects.keys())
	
	if imported_projects.has(file):
		print("[DEBUG] Processing groups in file '%s': %s" % [file, imported_projects[file].keys()])
		for group in imported_projects[file].keys():
			_set_visibility_group(file, group, visible)
	else:
		print("[ERROR] File '%s' not found in imported_projects!" % file)

func _set_visibility_group(file, group, visible):
	print("[DEBUG] _set_visibility_group called for group: '%s' in file: '%s', visible: %s" % [group, file, visible])
	
	if imported_projects.has(file) and imported_projects[file].has(group):
		print("[DEBUG] Processing elements in group '%s': %s" % [group, imported_projects[file][group].keys()])
		for elem in imported_projects[file][group].keys():
			_set_visibility_element(file, group, elem, visible)
	else:
		print("[ERROR] Group '%s' not found in file '%s'!" % [group, file])
		if imported_projects.has(file):
			print("[DEBUG] Available groups in file: ", imported_projects[file].keys())

func _set_visibility_element(file, group, elem, visible):
	if imported_projects.has(file) and imported_projects[file].has(group) and imported_projects[file][group].has(elem):
		var node = imported_projects[file][group][elem]
		if node:
			node.visible = visible
			print("[DEBUG] Set visibility for element '%s' to %s (node: %s)" % [elem, visible, node.name])
		else:
			print("[ERROR] Node is null for element: %s in group: %s, file: %s" % [elem, group, file])
	else:
		print("[ERROR] Path not found in imported_projects: file=%s, group=%s, elem=%s" % [file, group, elem])
		print("[DEBUG] Available files: ", imported_projects.keys())
		if imported_projects.has(file):
			print("[DEBUG] Available groups in file '%s': " % file, imported_projects[file].keys())
			if imported_projects[file].has(group):
				print("[DEBUG] Available elements in group '%s': " % group, imported_projects[file][group].keys())

	
func _setup_ui_buttons():
	print("[UI_DEBUG] Setting up UI buttons...")
	
	# Obține referința la panelul din dreapta din scene
	var right_panel = canvas.get_node_or_null("Panel")
	if not right_panel:
		print("[UI_DEBUG] ERROR: Right panel not found! Creating buttons in canvas instead.")
		right_panel = canvas
	else:
		print("[UI_DEBUG] Right panel found - size:", right_panel.size, "position:", right_panel.position)
	
	# Creează butoane de view preset în panelul din dreapta
	var names = ["TOP","FRONT","LEFT","RIGHT","BACK","FREE 3D"]
	for i in range(len(names)):
		var btn = Button.new()
		btn.text = names[i]
		# Poziționează butoanele în panel (poziții relative la panel)
		btn.position = Vector2(5, 5 + i*25)  # Poziții relative la panel
		btn.size = Vector2(80, 22)  # Butoane mai mici pentru a încăpea în panel
		btn.pressed.connect(Callable(self, "_on_view_button_pressed").bind(names[i]))
		right_panel.add_child(btn)
		print("[UI_DEBUG] Added button:", names[i], "at position:", btn.position)
	
	# Creează butonul Fit All în panelul din dreapta
	var fit_all_btn = Button.new()
	fit_all_btn.text = "FIT ALL"
	fit_all_btn.position = Vector2(5, 5 + len(names)*25)  # Sub ultimul buton
	fit_all_btn.size = Vector2(80, 22)
	fit_all_btn.pressed.connect(Callable(self, "_on_fit_all_pressed"))
	fit_all_btn.add_theme_color_override("font_color", Color.WHITE)
	fit_all_btn.add_theme_color_override("font_color_pressed", Color.WHITE)
	fit_all_btn.modulate = Color(0.2, 0.6, 0.8)  # Culoare albastră
	right_panel.add_child(fit_all_btn)
	print("[UI_DEBUG] Added FIT ALL button at position:", fit_all_btn.position)
	
	# Buton pentru încărcare GeoJSON
	var geojson_btn = Button.new()
	geojson_btn.text = "LOAD GEOJSON"
	geojson_btn.position = Vector2(5, 5 + (len(names)+1)*25)  # Sub FIT ALL
	geojson_btn.size = Vector2(110, 22)
	geojson_btn.modulate = Color(0.7, 0.5, 0.1)
	geojson_btn.add_theme_color_override("font_color", Color.WHITE)
	geojson_btn.pressed.connect(Callable(self, "_on_load_geojson_btn_pressed"))
	right_panel.add_child(geojson_btn)
	print("[UI_DEBUG] Added LOAD GEOJSON button at position:", geojson_btn.position)

	# Dialog de fișier pentru GeoJSON (dacă nu există deja)
	if not canvas.has_node("GeoJsonFileDialog"):
		var geojson_dialog = FileDialog.new()
		geojson_dialog.name = "GeoJsonFileDialog"
		geojson_dialog.access = FileDialog.ACCESS_FILESYSTEM
		geojson_dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILE
		geojson_dialog.filters = PackedStringArray(["*.geojson ; GeoJSON Files"])
		geojson_dialog.title = "Select GeoJSON file"
		geojson_dialog.size = Vector2(600, 400)
		geojson_dialog.file_selected.connect(Callable(self, "_on_geojson_file_selected"))
		canvas.add_child(geojson_dialog)
		print("[UI_DEBUG] Added GeoJsonFileDialog to canvas")
	
	# Buton pentru încărcare CityJSON
	var cityjson_btn = Button.new()
	cityjson_btn.text = "LOAD CITYJSON"
	cityjson_btn.position = Vector2(5, 5 + (len(names)+2)*25)  # Sub LOAD GEOJSON
	cityjson_btn.size = Vector2(110, 22)
	cityjson_btn.modulate = Color(0.1, 0.7, 0.5)  # Verde-albastru pentru diferențiere
	cityjson_btn.add_theme_color_override("font_color", Color.WHITE)
	cityjson_btn.pressed.connect(Callable(self, "_on_load_cityjson_btn_pressed"))
	right_panel.add_child(cityjson_btn)
	print("[UI_DEBUG] Added LOAD CITYJSON button at position:", cityjson_btn.position)
	
	# Dialog de fișier pentru CityJSON
	if not canvas.has_node("CityJsonFileDialog"):
		var cityjson_dialog = FileDialog.new()
		cityjson_dialog.name = "CityJsonFileDialog"
		cityjson_dialog.access = FileDialog.ACCESS_FILESYSTEM
		cityjson_dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILE
		cityjson_dialog.filters = PackedStringArray(["*.jsonl ; CityJSON Files", "*.json ; CityJSON Files"])
		cityjson_dialog.title = "Select CityJSON file"
		cityjson_dialog.size = Vector2(600, 400)
		cityjson_dialog.file_selected.connect(Callable(self, "_on_cityjson_file_selected"))
		canvas.add_child(cityjson_dialog)
		print("[UI_DEBUG] Added CityJsonFileDialog to canvas")
	
	# Buton pentru încărcare 3D Tiles (Cesium)
	var tiles3d_btn = Button.new()
	tiles3d_btn.text = "LOAD 3D TILES"
	tiles3d_btn.position = Vector2(5, 5 + (len(names)+3)*25)  # Sub LOAD CITYJSON
	tiles3d_btn.size = Vector2(110, 22)
	tiles3d_btn.modulate = Color(0.5, 0.2, 0.8)  # Violet pentru Cesium
	tiles3d_btn.add_theme_color_override("font_color", Color.WHITE)
	tiles3d_btn.pressed.connect(Callable(self, "_on_load_3dtiles_btn_pressed"))
	right_panel.add_child(tiles3d_btn)
	print("[UI_DEBUG] Added LOAD 3D TILES button at position:", tiles3d_btn.position)
	
	# Dialog de fișier pentru 3D Tiles (tileset.json)
	if not canvas.has_node("Tiles3DFileDialog"):
		var tiles3d_dialog = FileDialog.new()
		tiles3d_dialog.name = "Tiles3DFileDialog"
		tiles3d_dialog.access = FileDialog.ACCESS_FILESYSTEM
		tiles3d_dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILE
		tiles3d_dialog.filters = PackedStringArray(["tileset.json ; Cesium 3D Tiles", "*.json ; Tileset JSON"])
		tiles3d_dialog.title = "Select Cesium 3D Tiles tileset.json"
		tiles3d_dialog.size = Vector2(600, 400)
		tiles3d_dialog.file_selected.connect(Callable(self, "_on_3dtiles_file_selected"))
		canvas.add_child(tiles3d_dialog)
		print("[UI_DEBUG] Added Tiles3DFileDialog to canvas")

	print("[UI_DEBUG] UI buttons setup complete - all buttons added to right panel")

# Callback pentru butonul de încărcare GeoJSON
func _on_load_geojson_btn_pressed():
	var geojson_dialog = canvas.get_node_or_null("GeoJsonFileDialog")
	if geojson_dialog:
		geojson_dialog.popup_centered()
	else:
		push_error("GeoJsonFileDialog not found!")

# Callback pentru selecția fișierului GeoJSON
func _on_geojson_file_selected(path: String):
	# Poți ajusta valorile pentru scale_factor, extrusion_height, center_lat/lon după caz
	# extrusion_height = 15.0m înălțime default pentru clădiri
	load_geojson(path, 100000.0, 15.0, 46.6720031, 28.0620905)
	print("[UI_DEBUG] Loaded GeoJSON file:", path)

# === CITYJSON CALLBACKS ===
func _on_load_cityjson_btn_pressed():
	var cityjson_dialog = canvas.get_node_or_null("CityJsonFileDialog")
	if cityjson_dialog:
		cityjson_dialog.popup_centered()
	else:
		push_error("CityJsonFileDialog not found!")

func _on_cityjson_file_selected(path: String):
	print("[CityJSON] Loading file: ", path)
	# LoD 2.2 oferă cel mai mult detaliu (ferestre, decorații)
	# LoD 1.2/1.3 pentru performanță mai bună
	load_cityjson(path, "2.2")
	print("[CityJSON] File loaded:", path)

# === CESIUM 3D TILES CALLBACKS ===
func _on_load_3dtiles_btn_pressed():
	var tiles3d_dialog = canvas.get_node_or_null("Tiles3DFileDialog")
	if tiles3d_dialog:
		tiles3d_dialog.popup_centered()
	else:
		push_error("Tiles3DFileDialog not found!")

func _on_3dtiles_file_selected(path: String):
	print("[3D Tiles] Loading tileset: ", path)
	
	# Addon-ul Cesium pentru Godot este orientat spre editor, nu runtime
	# Folosim implementarea noastră manuală pentru încărcarea la runtime
	# 
	# Pentru a folosi addon-ul Cesium în editor:
	# 1. Activează plugin-ul din Project Settings > Plugins > Cesium for Godot
	# 2. Adaugă nodurile CesiumGeoreference și Cesium3DTileset din panelul Cesium
	# 3. Configurează URL-ul tileset-ului în Inspector
	# 4. Tileset-ul va fi vizibil în editor și la runtime
	
	# Pentru încărcare dinamică la runtime, folosim implementarea noastră:
	load_3d_tiles(path)
	print("[3D Tiles] Tileset loaded:", path)

func _setup_coordinate_label():
	coord_label = Label.new()
	coord_label.text = "X: 0.0, Y: 0.0, Z: 0.0"
	coord_label.position = Vector2(220, get_viewport().get_visible_rect().size.y - 50)  # Lângă panelul de grid
	coord_label.size = Vector2(300, 30)
	coord_label.add_theme_color_override("font_color", Color.BLACK)
	coord_label.add_theme_font_size_override("font_size", 14)
	canvas.add_child(coord_label)
	print("[UI_DEBUG] Coordinate label positioned next to grid controls panel")

func _setup_grid_controls():
	"""Creează controalele UI pentru grid infinit"""
	print("[UI_DEBUG] Setting up grid controls...")
	print("[UI_DEBUG] Canvas available:", canvas != null)
	print("[UI_DEBUG] Canvas name:", canvas.get_name() if canvas else "N/A")
	
	# Creează panelul de grid controls în partea de jos a ecranului pentru a nu se suprapune
	grid_controls_panel = Panel.new()
	grid_controls_panel.position = Vector2(10, get_viewport().get_visible_rect().size.y - 120)  # Jos în stânga
	grid_controls_panel.size = Vector2(200, 80)
	grid_controls_panel.add_theme_color_override("bg_color", Color(0.9, 0.9, 0.9, 0.8))
	canvas.add_child(grid_controls_panel)
	print("[UI_DEBUG] Grid controls panel created and added to canvas at bottom-left")
	
	# Title
	var title_label = Label.new()
	title_label.text = "Grid Controls"
	title_label.position = Vector2(10, 5)
	title_label.add_theme_color_override("font_color", Color.BLACK)
	title_label.add_theme_font_size_override("font_size", 12)
	grid_controls_panel.add_child(title_label)
	
	# Grid Visibility Checkbox
	grid_visible_checkbox = CheckBox.new()
	grid_visible_checkbox.text = "Show Grid"
	grid_visible_checkbox.position = Vector2(10, 25)
	grid_visible_checkbox.button_pressed = grid_visible
	grid_visible_checkbox.toggled.connect(_on_grid_visibility_toggled)
	grid_controls_panel.add_child(grid_visible_checkbox)
	
	# Grid Z Position Label
	grid_z_label = Label.new()
	grid_z_label.text = "Grid Z: 0.00"
	grid_z_label.position = Vector2(10, 50)
	grid_z_label.add_theme_color_override("font_color", Color.BLACK)
	grid_z_label.add_theme_font_size_override("font_size", 10)
	grid_controls_panel.add_child(grid_z_label)
	
	# Grid Z Position Slider
	grid_z_slider = HSlider.new()
	grid_z_slider.position = Vector2(70, 50)
	grid_z_slider.size = Vector2(120, 20)
	grid_z_slider.min_value = -100.0
	grid_z_slider.max_value = 100.0
	grid_z_slider.step = 0.01
	grid_z_slider.value = grid_z_position
	grid_z_slider.value_changed.connect(_on_grid_z_changed)
	grid_controls_panel.add_child(grid_z_slider)
	
	print("[UI_DEBUG] Grid controls setup complete!")
	print("[UI_DEBUG] - Panel position:", grid_controls_panel.position, "size:", grid_controls_panel.size)
	print("[UI_DEBUG] - Checkbox state:", grid_visible_checkbox.button_pressed)
	print("[UI_DEBUG] - Slider range:", grid_z_slider.min_value, "to", grid_z_slider.max_value, "current:", grid_z_slider.value)
	print("[UI_DEBUG] - Panel children count:", grid_controls_panel.get_child_count())

# === GRID CALLBACKS ===

func _on_grid_visibility_toggled(button_pressed: bool):
	"""Toggle grid visibility"""
	print("[CALLBACK_DEBUG] Grid visibility toggle called - new state:", button_pressed)
	grid_visible = button_pressed
	if infinite_grid:
		infinite_grid.visible = grid_visible
		print("[CALLBACK_DEBUG] Grid visibility updated - infinite_grid.visible:", infinite_grid.visible)
	else:
		print("[CALLBACK_DEBUG] ERROR: infinite_grid is null!")
	print("[CADViewer] Grid visibility: ", grid_visible)

func _on_grid_z_changed(value: float):
	"""Update grid Z position"""
	print("[CALLBACK_DEBUG] Grid Z position changed called - new value:", value)
	grid_z_position = value
	# Recreate grid with new Z position
	if infinite_grid:
		print("[CALLBACK_DEBUG] Freeing old grid instance...")
		infinite_grid.queue_free()
	print("[CALLBACK_DEBUG] Recreating grid at new Z position...")
	_create_infinite_grid()
	# Update label
	if grid_z_label:
		grid_z_label.text = "Grid Z: %.2f" % grid_z_position
		print("[CALLBACK_DEBUG] Label updated to:", grid_z_label.text)
	print("[CADViewer] Grid Z position: ", grid_z_position)
	
	# Horizontal Section Z Position
	var h_z_label = Label.new()
	h_z_label.text = "H-Section Z:"
	h_z_label.position = Vector2(10, 55)
	h_z_label.add_theme_color_override("font_color", Color.BLACK)
	section_controls_panel.add_child(h_z_label)
	
	h_section_slider = HSlider.new()
	h_section_slider.position = Vector2(90, 55)
	h_section_slider.size = Vector2(120, 20)
	h_section_slider.min_value = -10.0
	h_section_slider.max_value = 10.0
	h_section_slider.step = 0.1
	h_section_slider.value = horizontal_section_z
	h_section_slider.value_changed.connect(_on_horizontal_section_z_changed)
	section_controls_panel.add_child(h_section_slider)
	
	# Horizontal Section Depth
	var h_depth_label = Label.new()
	h_depth_label.text = "H-Depth:"
	h_depth_label.position = Vector2(10, 80)
	h_depth_label.add_theme_color_override("font_color", Color.BLACK)
	section_controls_panel.add_child(h_depth_label)
	
	h_depth_slider = HSlider.new()
	h_depth_slider.position = Vector2(90, 80)
	h_depth_slider.size = Vector2(120, 20)
	h_depth_slider.min_value = 0.5
	h_depth_slider.max_value = 10.0
	h_depth_slider.step = 0.1
	h_depth_slider.value = horizontal_section_depth
	h_depth_slider.value_changed.connect(_on_horizontal_depth_changed)
	section_controls_panel.add_child(h_depth_slider)
	
	# Vertical Section Toggle
	vertical_section_toggle = CheckBox.new()
	vertical_section_toggle.text = "Vertical Section"
	vertical_section_toggle.position = Vector2(10, 110)
	vertical_section_toggle.button_pressed = vertical_section_enabled
	vertical_section_toggle.toggled.connect(_on_vertical_section_toggled)
	section_controls_panel.add_child(vertical_section_toggle)
	
	# Vertical Section X Position
	var v_x_label = Label.new()
	v_x_label.text = "V-Section X:"
	v_x_label.position = Vector2(10, 135)
	v_x_label.add_theme_color_override("font_color", Color.BLACK)
	section_controls_panel.add_child(v_x_label)
	
	v_section_x_slider = HSlider.new()
	v_section_x_slider.position = Vector2(90, 135)
	v_section_x_slider.size = Vector2(120, 20)
	v_section_x_slider.min_value = -20.0
	v_section_x_slider.max_value = 20.0
	v_section_x_slider.step = 0.1
	v_section_x_slider.value = vertical_section_x
	v_section_x_slider.value_changed.connect(_on_vertical_section_x_changed)
	section_controls_panel.add_child(v_section_x_slider)
	
	# Vertical Section Y Position
	var v_y_label = Label.new()
	v_y_label.text = "V-Section Y:"
	v_y_label.position = Vector2(10, 160)
	v_y_label.add_theme_color_override("font_color", Color.BLACK)
	section_controls_panel.add_child(v_y_label)
	
	v_section_y_slider = HSlider.new()
	v_section_y_slider.position = Vector2(90, 160)
	v_section_y_slider.size = Vector2(120, 20)
	v_section_y_slider.min_value = -20.0
	v_section_y_slider.max_value = 20.0
	v_section_y_slider.step = 0.1
	v_section_y_slider.value = vertical_section_y
	v_section_y_slider.value_changed.connect(_on_vertical_section_y_changed)
	section_controls_panel.add_child(v_section_y_slider)
	
	# Vertical Section Depth
	var v_depth_label = Label.new()
	v_depth_label.text = "V-Depth:"
	v_depth_label.position = Vector2(10, 185)
	v_depth_label.add_theme_color_override("font_color", Color.BLACK)
	section_controls_panel.add_child(v_depth_label)
	
	v_depth_slider = HSlider.new()
	v_depth_slider.position = Vector2(90, 185)
	v_depth_slider.size = Vector2(120, 20)
	v_depth_slider.min_value = 1.0
	v_depth_slider.max_value = 20.0
	v_depth_slider.step = 0.1
	v_depth_slider.value = vertical_section_depth
	v_depth_slider.value_changed.connect(_on_vertical_depth_changed)
	section_controls_panel.add_child(v_depth_slider)
	
	print("[CADViewer] Section controls setup complete")

func _create_section_planes():
	"""Creează planurile vizuale pentru sectiuni"""
	# Material pentru planurile de sectiune
	section_material = StandardMaterial3D.new()
	section_material.albedo_color = Color(1.0, 0.0, 0.0, 0.3)  # Roșu transparent
	section_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	section_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	section_material.cull_mode = BaseMaterial3D.CULL_DISABLED  # Vizibil din ambele părți
	
	# Horizontal section plane (XY)
	section_plane_horizontal = MeshInstance3D.new()
	var plane_mesh_h = PlaneMesh.new()
	plane_mesh_h.size = Vector2(50, 50)  # Dimensiune mare pentru a acoperi scena
	section_plane_horizontal.mesh = plane_mesh_h
	section_plane_horizontal.material_override = section_material
	section_plane_horizontal.visible = false
	add_child(section_plane_horizontal)
	
	# Vertical section plane X (YZ)
	section_plane_vertical_x = MeshInstance3D.new()
	var plane_mesh_vx = PlaneMesh.new()
	plane_mesh_vx.size = Vector2(50, 50)
	section_plane_vertical_x.mesh = plane_mesh_vx
	section_plane_vertical_x.material_override = section_material.duplicate()
	section_plane_vertical_x.material_override.albedo_color = Color(0.0, 1.0, 0.0, 0.3)  # Verde
	section_plane_vertical_x.rotation_degrees = Vector3(0, 0, 90)  # Rotire pentru YZ plane
	section_plane_vertical_x.visible = false
	add_child(section_plane_vertical_x)
	
	# Vertical section plane Y (XZ)
	section_plane_vertical_y = MeshInstance3D.new()
	var plane_mesh_vy = PlaneMesh.new()
	plane_mesh_vy.size = Vector2(50, 50)
	section_plane_vertical_y.mesh = plane_mesh_vy
	section_plane_vertical_y.material_override = section_material.duplicate()
	section_plane_vertical_y.material_override.albedo_color = Color(0.0, 0.0, 1.0, 0.3)  # Albastru
	section_plane_vertical_y.rotation_degrees = Vector3(90, 0, 0)  # Rotire pentru XZ plane
	section_plane_vertical_y.visible = false
	add_child(section_plane_vertical_y)
	
	print("[CADViewer] Section planes created")

# === SECTION CALLBACKS ===

func _on_horizontal_section_toggled(button_pressed: bool):
	"""Toggle horizontal section"""
	horizontal_section_enabled = button_pressed
	section_plane_horizontal.visible = button_pressed
	_update_section_effects()
	print("[CADViewer] Horizontal section: ", button_pressed)

func _on_vertical_section_toggled(button_pressed: bool):
	"""Toggle vertical section"""
	vertical_section_enabled = button_pressed
	section_plane_vertical_x.visible = button_pressed
	section_plane_vertical_y.visible = button_pressed
	_update_section_effects()
	print("[CADViewer] Vertical section: ", button_pressed)

func _on_horizontal_section_z_changed(value: float):
	"""Update horizontal section Z position"""
	horizontal_section_z = value
	section_plane_horizontal.position.z = value
	_update_section_effects()

func _on_horizontal_depth_changed(value: float):
	"""Update horizontal section depth"""
	horizontal_section_depth = value
	_update_section_effects()

func _on_vertical_section_x_changed(value: float):
	"""Update vertical section X position"""
	vertical_section_x = value
	section_plane_vertical_x.position.x = value
	_update_section_effects()

func _on_vertical_section_y_changed(value: float):
	"""Update vertical section Y position"""
	vertical_section_y = value
	section_plane_vertical_y.position.y = value
	_update_section_effects()

func _on_vertical_depth_changed(value: float):
	"""Update vertical section depth"""
	vertical_section_depth = value
	_update_section_effects()

func _update_section_effects():
	"""Aplicare efecte de sectiune la toate obiectele din scenă"""
	_apply_section_to_node(self)

func _apply_section_to_node(node: Node):
	"""Aplică efectele de sectiune recursiv la un nod și copiii săi"""
	# Pentru MeshInstance3D nodes, aplică shader-ul de sectiune
	if node is MeshInstance3D:
		_apply_section_to_mesh(node)
	
	# Continuă recursiv pentru copii
	for child in node.get_children():
		_apply_section_to_node(child)

func _apply_section_to_mesh(mesh_instance: MeshInstance3D):
	"""Aplică efectul de sectiune la un MeshInstance3D"""
	if not mesh_instance.material_override:
		return
	
	var material = mesh_instance.material_override
	if material is StandardMaterial3D:
		var std_material = material as StandardMaterial3D
		
		# Calculează efectul de fade bazat pe distanța de la planurile de sectiune
		var mesh_pos = mesh_instance.global_position
		var fade_factor = 1.0
		
		# Horizontal section fade
		if horizontal_section_enabled:
			var distance_to_h_plane = abs(mesh_pos.z - horizontal_section_z)
			if distance_to_h_plane > horizontal_section_depth / 2.0:
				fade_factor *= 0.3  # Fade out
		
		# Vertical section fade  
		if vertical_section_enabled:
			var distance_to_v_plane_x = abs(mesh_pos.x - vertical_section_x)
			var distance_to_v_plane_y = abs(mesh_pos.y - vertical_section_y)
			
			if distance_to_v_plane_x > vertical_section_depth / 2.0 or distance_to_v_plane_y > vertical_section_depth / 2.0:
				fade_factor *= 0.3  # Fade out
		
		# Aplică fade factor la material
		var original_color = std_material.albedo_color
		std_material.albedo_color = Color(original_color.r, original_color.g, original_color.b, original_color.a * fade_factor)

func _create_snap_preview_marker():
	snap_preview_marker = MeshInstance3D.new()
	var sphere = SphereMesh.new()
	sphere.radius = 0.08
	snap_preview_marker.mesh = sphere
	var material = StandardMaterial3D.new()
	material.albedo_color = Color.MAGENTA
	material.emission_enabled = true
	material.emission = Color.MAGENTA * 0.5
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	snap_preview_marker.material_override = material
	snap_preview_marker.visible = false
	add_child(snap_preview_marker)

func get_snapped_position(world_pos: Vector3) -> Vector3:
	# Snap logic placeholder (return world_pos direct dacă nu ai snap grid)
	return world_pos

# === DXF Watchdog System ===
var watchdog_timer: Timer
var signal_file_path: String = "reload_signal.json"
var last_signal_timestamp: float = 0.0
var watchdog_process: int = -1

func _setup_dxf_watchdog():
	# Creează timer pentru verificarea signal file-ului
	watchdog_timer = Timer.new()
	watchdog_timer.wait_time = 1.0  # Verifică în fiecare secundă
	watchdog_timer.timeout.connect(_check_reload_signal)
	watchdog_timer.autostart = true
	add_child(watchdog_timer)
	
	# Pornește procesul Python watchdog în background
	_start_python_watchdog()

func _start_python_watchdog():
	var script_path = "python/dxf_watchdog.py"
	var args = [script_path]
	print("[DEBUG] Starting DXF watchdog process...")
	
	# Pornește procesul în background (non-blocking)
	watchdog_process = OS.create_process("python", args, false)
	if watchdog_process > 0:
		print("[DEBUG] DXF watchdog started with PID: ", watchdog_process)
	else:
		print("[ERROR] Failed to start DXF watchdog")

func _check_reload_signal():
	if not FileAccess.file_exists(signal_file_path):
		return
	
	var file = FileAccess.open(signal_file_path, FileAccess.READ)
	if not file:
		return
	
	var json_str = file.get_as_text()
	file.close()
	
	var json = JSON.new()
	var parse_result = json.parse(json_str)
	if parse_result != OK:
		return
	
	var signal_data = json.data
	if typeof(signal_data) != TYPE_DICTIONARY:
		return
	
	var timestamp = signal_data.get("timestamp", 0.0)
	if timestamp > last_signal_timestamp:
		last_signal_timestamp = timestamp
		var glb_file = signal_data.get("glb_file", "")
		var dxf_file = signal_data.get("dxf_file", "")
		
		print("[DEBUG] Watchdog signal received: reloading ", glb_file)
		_reload_single_glb(glb_file, dxf_file)

func _reload_single_glb(glb_path: String, dxf_path: String):
	if not FileAccess.file_exists(glb_path):
		print("[ERROR] GLB file not found for reload: ", glb_path)
		return
	
	print("[DEBUG] Hot reloading GLB: ", glb_path)
	
	# Elimină mesh-urile existente pentru acest fișier
	var filename = glb_path.get_file().get_basename()
	_remove_existing_meshes_for_file(filename)
	
	# Forțează ștergerea completă a cache-ului și fișierelor .import
	_force_clear_resource_cache(glb_path)
	_force_delete_import_files(glb_path)
	
	# Așteaptă mai multe frame-uri pentru cleanup complet
	await get_tree().process_frame
	await get_tree().process_frame
	await get_tree().process_frame
	
	# Verifică dimensiunea fișierului pentru a fi sigur că este complet
	var file_size = _get_file_size(glb_path)
	if file_size < 100:  # Fișier prea mic, probabil încă se scrie
		print("[DEBUG] Waiting for GLB file to be completely written...")
		await get_tree().create_timer(0.5).timeout
	
	# Forțează reimportul prin modificarea timestamp-ului fișierului
	_touch_file_for_reimport(glb_path)
	
	# Încearcă să încarce GLB-ul cu multiple tentative
	var success = await _load_glb_with_retry(glb_path)
	
	if success:
		# Flash vizual pentru confirmare
		_flash_reload_indicator()
	else:
		print("[ERROR] Failed to reload GLB after multiple attempts: ", glb_path)

func _remove_existing_meshes_for_file(filename: String):
	# Elimină din imported_projects
	var keys_to_remove = []
	for key in imported_projects.keys():
		if key.contains(filename):
			keys_to_remove.append(key)
	
	for key in keys_to_remove:
		# Elimină nodurile din scenă (inclusiv ferestrele GLTF)
		for layer in imported_projects[key].values():
			for mesh_node in layer.values():
				if mesh_node and is_instance_valid(mesh_node):
					mesh_node.queue_free()
		imported_projects.erase(key)
	
	print("[DEBUG] Removed existing meshes and windows for file: ", filename)

func _clear_all_imported_projects():
	print("[DEBUG] Clearing all imported projects")
	
	# Elimină toate nodurile din scenă
	for project_key in imported_projects.keys():
		for layer in imported_projects[project_key].values():
			for mesh_node in layer.values():
				if mesh_node and is_instance_valid(mesh_node):
					mesh_node.queue_free()
	
	# Curăță dicționarul
	imported_projects.clear()
	
	# Resetează tree-ul
	var tree_node = get_node_or_null("Objects")
	if tree_node:
		tree_node.clear()
	
	# Resetează selecția
	selected_geometry = null

func _clear_glb_cache_and_imports_for_folder(folder_path: String):
	print("[DEBUG] Clearing GLB cache and import files for folder: ", folder_path)
	var dir = DirAccess.open(folder_path)
	if not dir:
		print("[ERROR] Cannot access folder: ", folder_path)
		return
	
	dir.list_dir_begin()
	var file_name = dir.get_next()
	while file_name != "":
		if not dir.current_is_dir() and file_name.to_lower().ends_with(".glb"):
			var glb_path = folder_path + "/" + file_name
			print("[DEBUG] Processing GLB for cache clear: ", glb_path)
			
			# Curăță cache-ul și fișierele .import
			_force_clear_resource_cache(glb_path)
			_force_delete_import_files(glb_path)
			
			# Modifică timestamp-ul pentru reimport
			_touch_file_for_reimport(glb_path)
		file_name = dir.get_next()
	dir.list_dir_end()
	
	print("[DEBUG] ✓ Cache and import cleanup completed for folder")

func _force_clear_resource_cache(glb_path: String):
	"""Forțează curățarea completă a cache-ului pentru un fișier GLB"""
	# Șterge din cache ResourceLoader dacă există
	if ResourceLoader.has_cached(glb_path):
		print("[DEBUG] Clearing ResourceLoader cache for: ", glb_path)
		# Nu există o metodă directă, dar CACHE_MODE_IGNORE va ignora cache-ul
	
	# Notifică Godot să elibereze toate referințele la resursa
	if ResourceLoader.exists(glb_path):
		print("[DEBUG] Forcing resource cache clear for: ", glb_path)

func _force_delete_import_files(glb_path: String):
	"""Șterge toate fișierele .import asociate cu GLB-ul"""
	var base_dir = glb_path.get_base_dir()
	var file_name = glb_path.get_file()
	var dir = DirAccess.open(base_dir)
	
	if not dir:
		print("[ERROR] Cannot access directory: ", base_dir)
		return
	
	# Șterge fișierul .import principal
	var import_file = glb_path + ".import"
	if FileAccess.file_exists(import_file):
		if dir.remove(import_file.get_file()) == OK:
			print("[DEBUG] ✓ Removed import file: ", import_file)
		else:
			print("[ERROR] Failed to remove import file: ", import_file)
	
	# Șterge și fișierele .import pentru mapping-uri și alte fișiere asociate
	var mapping_file = glb_path.get_basename() + "_mapping.json"
	var mapping_import = mapping_file + ".import"
	if FileAccess.file_exists(mapping_import):
		if dir.remove(mapping_import.get_file()) == OK:
			print("[DEBUG] ✓ Removed mapping import file: ", mapping_import)
	
	# Șterge din .godot/imported/ dacă există
	var godot_imported_dir = ProjectSettings.globalize_path("res://.godot/imported/")
	var imported_dir = DirAccess.open(godot_imported_dir)
	if imported_dir:
		var search_name = file_name.get_basename()
		imported_dir.list_dir_begin()
		var imported_file = imported_dir.get_next()
		while imported_file != "":
			if imported_file.contains(search_name):
				if imported_dir.remove(imported_file) == OK:
					print("[DEBUG] ✓ Removed from .godot/imported/: ", imported_file)
			imported_file = imported_dir.get_next()
		imported_dir.list_dir_end()

func _touch_file_for_reimport(glb_path: String):
	"""Modifică timestamp-ul fișierului pentru a forța reimportul în Godot"""
	# Citește conținutul fișierului
	var file = FileAccess.open(glb_path, FileAccess.READ)
	if not file:
		print("[ERROR] Cannot open file for touch: ", glb_path)
		return
	
	var content = file.get_buffer(file.get_length())
	file.close()
	
	# Rescrie fișierul pentru a actualiza timestamp-ul
	file = FileAccess.open(glb_path, FileAccess.WRITE)
	if file:
		file.store_buffer(content)
		file.close()
		print("[DEBUG] ✓ File timestamp updated for reimport: ", glb_path)
	else:
		print("[ERROR] Cannot write file for touch: ", glb_path)

func _force_recreate_glb_file(glb_path: String) -> bool:
	"""Recreează complet fișierul GLB pentru a forța recunoașterea de către Godot"""
	var file = FileAccess.open(glb_path, FileAccess.READ)
	if not file:
		print("[ERROR] Cannot read GLB for recreation: ", glb_path)
		return false
	
	var content = file.get_buffer(file.get_length())
	file.close()
	
	# Creează backup temporar
	var temp_path = glb_path + ".temp_backup"
	var temp_file = FileAccess.open(temp_path, FileAccess.WRITE)
	if not temp_file:
		print("[ERROR] Cannot create temp backup: ", temp_path)
		return false
	
	temp_file.store_buffer(content)
	temp_file.close()
	
	# Șterge originalul
	var dir = DirAccess.open(glb_path.get_base_dir())
	if not dir or dir.remove(glb_path.get_file()) != OK:
		print("[ERROR] Cannot remove original GLB: ", glb_path)
		# Cleanup temp file
		dir.remove(temp_path.get_file())
		return false
	
	# Așteaptă puțin pentru ca sistemul să recunoască ștergerea
	await get_tree().process_frame
	await get_tree().process_frame
	
	# Recreează din backup
	var new_file = FileAccess.open(glb_path, FileAccess.WRITE)
	if not new_file:
		# Încearcă să restaurezi din backup
		dir.copy(temp_path, glb_path)
		print("[ERROR] Cannot recreate GLB, restored from backup: ", glb_path)
		dir.remove(temp_path.get_file())
		return false
	
	new_file.store_buffer(content)
	new_file.close()
	
	# Curăță backup-ul
	dir.remove(temp_path.get_file())
	
	print("[DEBUG] ✓ Successfully recreated GLB file: ", glb_path)
	return true

func _force_reimport_via_editor(glb_path: String):
	"""Forțează reimportul unui fișier prin EditorInterface"""
	if not Engine.is_editor_hint():
		return
		
	print("[DEBUG] Forcing reimport via EditorInterface: ", glb_path)
	var res_path = ProjectSettings.localize_path(glb_path)
	
	# Forțează actualizarea filesystem-ului pentru acest fișier
	EditorInterface.get_resource_filesystem().update_file(res_path)
	await get_tree().process_frame
	
	# Forțează reimport complet
	EditorInterface.get_resource_filesystem().reimport_files([res_path])
	await get_tree().process_frame
	await get_tree().process_frame

func _load_glb_with_gltf_document(glb_path: String) -> PackedScene:
	"""Încarcă GLB direct cu GLTFDocument - bypass pentru runtime loading"""
	print("[DEBUG] Attempting direct GLTFDocument loading: ", glb_path)
	
	var file = FileAccess.open(glb_path, FileAccess.READ)
	if not file:
		print("[ERROR] Cannot open GLB file: ", glb_path)
		return null
	
	var glb_data = file.get_buffer(file.get_length())
	file.close()
	
	if glb_data.size() == 0:
		print("[ERROR] Empty GLB file: ", glb_path)
		return null
	
	# Folosește GLTFDocument pentru încărcare directă
	var gltf_document = GLTFDocument.new()
	var gltf_state = GLTFState.new()
	
	# Încarcă din buffer binary
	var error = gltf_document.append_from_buffer(glb_data, "", gltf_state)
	if error != OK:
		print("[ERROR] GLTFDocument.append_from_buffer failed: ", error)
		return null
	
	# Generează scena (returnează Node3D)
	var scene_node = gltf_document.generate_scene(gltf_state)
	if not scene_node:
		print("[ERROR] GLTFDocument.generate_scene failed")
		return null
	
	# Creează PackedScene din Node3D
	var packed_scene = PackedScene.new()
	var pack_result = packed_scene.pack(scene_node)
	if pack_result != OK:
		print("[ERROR] Failed to pack scene into PackedScene: ", pack_result)
		scene_node.queue_free()
		return null
	
	print("[DEBUG] ✅ GLTFDocument loading successful: ", glb_path)
	return packed_scene

func _load_glb_with_retry(glb_path: String) -> bool:
	"""Încarcă GLB cu multiple tentative și verificări robuste"""
	var max_attempts = 5
	var base_delay = 0.5
	
	# Forțează reimportul prin ștergerea completă a cache-ului înainte de prima tentativă
	_force_clear_resource_cache(glb_path)
	_force_delete_import_files(glb_path)
	
	# Așteaptă mai mult timp pentru Godot să proceseze ștergerea
	await get_tree().create_timer(1.0).timeout
	
	for attempt in range(max_attempts):
		print("[DEBUG] Loading attempt %d/%d: %s" % [attempt + 1, max_attempts, glb_path.get_file()])
		
		# Verifică integritatea fișierului GLB
		var file_size = _get_file_size(glb_path)
		if file_size < 100:
			print("[DEBUG] ❌ GLB file too small (%d bytes), skipping" % file_size)
			return false
		
		# Verifică și fișierul .import
		var import_file = glb_path + ".import"
		var import_exists = FileAccess.file_exists(import_file)
		print("[DEBUG] Import file exists: %s (%s)" % [str(import_exists), import_file.get_file()])
		
		# Dacă nu există fișierul .import, forțează Godot să îl regenereze
		if not import_exists:
			print("[DEBUG] Forcing Godot to regenerate import file...")
			# Creează un timestamp dummy în fișier pentru a forța regenerarea
			_touch_file_for_reimport(glb_path)
			await get_tree().create_timer(0.8).timeout
		
		# Pentru runtime loading, încearcă GLTFDocument direct 
		if not Engine.is_editor_hint():
			print("[DEBUG] Runtime detected - trying GLTFDocument direct loading...")
			var direct_scene = _load_glb_with_gltf_document(glb_path)
			if direct_scene:
				var scene = direct_scene.instantiate()
				if scene:
					print("[DEBUG] ✅ GLTFDocument direct loading successful!")
					add_child(scene)
					print("[DEBUG] ✓ Hot reload successful: ", glb_path)
					
					# Adaugă metadata din mapping pentru export IFC
					_load_mapping_metadata_for_glb(glb_path, scene)
					
					_print_meshes_and_colors(scene, glb_path)
					
					# Încarcă ferestrele GLTF pentru acest GLB
					_load_window_gltf_for_glb(glb_path)
					
					# Actualizează structura de proiecte
					populate_tree_with_projects(imported_projects)
					
					# Flash vizual pentru confirmare
					_flash_reload_indicator()
					return true
		
		# Încearcă să încarce resursa cu diferite strategii
		var packed_scene = null
		
		if attempt == 0:
			# Prima tentativă: CACHE_MODE_IGNORE standard
			packed_scene = ResourceLoader.load(glb_path, "", ResourceLoader.CACHE_MODE_IGNORE)
		elif attempt == 1:
			# A doua tentativă: Încearcă să încarci direct fișierul .scn din cache
			if FileAccess.file_exists(import_file):
				print("[DEBUG] Attempting direct .scn cache loading...")
				var import_content = FileAccess.get_file_as_string(import_file)
				# Caută linia cu path="res://..."
				var lines = import_content.split("\n")
				var scn_path = ""
				for line in lines:
					if line.begins_with("path="):
						# Extrage calea dintre ghilimele
						var start_quote = line.find("\"")
						var end_quote = line.find("\"", start_quote + 1)
						if start_quote >= 0 and end_quote > start_quote:
							scn_path = line.substr(start_quote + 1, end_quote - start_quote - 1)
							break
				if scn_path != "":
					print("[DEBUG] Found .scn path: %s" % scn_path)
					packed_scene = ResourceLoader.load(scn_path, "", ResourceLoader.CACHE_MODE_REUSE)
					print("[DEBUG] Direct .scn load result: %s" % str(packed_scene))
				else:
					print("[DEBUG] Could not parse .scn path from .import file")
			
			# Fallback la încărcare standard dacă .scn nu a mers
			if not packed_scene:
				packed_scene = ResourceLoader.load(glb_path, "", ResourceLoader.CACHE_MODE_REPLACE)
		elif attempt == 2:
			# A treia tentativă: Forțează res:// path
			var res_path = ProjectSettings.localize_path(glb_path)
			print("[DEBUG] Attempting with res:// path: %s" % res_path)
			packed_scene = ResourceLoader.load(res_path, "", ResourceLoader.CACHE_MODE_IGNORE)
		elif attempt == 3:
			# A patra tentativă: Specifică explicit tipul + rescan filesystem
			packed_scene = ResourceLoader.load(glb_path, "PackedScene", ResourceLoader.CACHE_MODE_IGNORE)
			
			# Dacă încă nu merge, forțează rescan filesystem
			if not packed_scene:
				print("[DEBUG] Forcing filesystem rescan...")
				if Engine.is_editor_hint():
					EditorInterface.get_resource_filesystem().scan()
					await get_tree().process_frame
					await get_tree().process_frame
					packed_scene = ResourceLoader.load(glb_path, "PackedScene", ResourceLoader.CACHE_MODE_IGNORE)
				else:
					print("[DEBUG] Not in editor - skipping filesystem rescan")
		else:
			# Ultima tentativă: Combinație de strategii + GLTFDocument direct
			print("[DEBUG] Final attempt with multiple strategies...")
			
			# Pentru runtime (non-editor), încearcă GLTFDocument direct
			if not Engine.is_editor_hint():
				print("[DEBUG] Runtime detected - trying GLTFDocument direct loading...")
				packed_scene = _load_glb_with_gltf_document(glb_path)
			
			# Dacă GLTFDocument nu a mers sau suntem în editor, fallback tradițional
			if not packed_scene:
				var abs_path = ProjectSettings.globalize_path(glb_path)
				packed_scene = ResourceLoader.load(abs_path, "", ResourceLoader.CACHE_MODE_IGNORE)
				
				# Dacă nu merge, încearcă să reîncarci ca Resource generic
				if not packed_scene:
					packed_scene = ResourceLoader.load(glb_path, "Resource", ResourceLoader.CACHE_MODE_IGNORE)
					print("[DEBUG] Generic Resource load: %s" % str(packed_scene))
		
		print("[DEBUG] ResourceLoader result: %s (type: %s)" % [str(packed_scene), str(type_string(typeof(packed_scene)))])
		
		# Verifică dacă încărcarea a reușit
		if packed_scene and packed_scene is PackedScene:
			print("[DEBUG] ✅ PackedScene loaded successfully on attempt %d" % (attempt + 1))
			
			# Instanțiază scena
			var scene = packed_scene.instantiate()
			if scene:
				add_child(scene)
				print("[DEBUG] ✓ Hot reload successful: ", glb_path)
				
				# Adaugă metadata din mapping pentru export IFC
				_load_mapping_metadata_for_glb(glb_path, scene)
				
				_print_meshes_and_colors(scene, glb_path)
				
				# Încarcă ferestrele GLTF pentru acest GLB
				_load_window_gltf_for_glb(glb_path)
				
				# Actualizează structura de proiecte
				populate_tree_with_projects(imported_projects)
				
				# Flash vizual pentru confirmare
				_flash_reload_indicator()
				
				return true
			else:
				print("[DEBUG] ❌ Failed to instantiate scene on attempt %d" % (attempt + 1))
		else:
			print("[DEBUG] ❌ ResourceLoader failed on attempt %d: %s" % [attempt + 1, str(packed_scene)])
			
			# Diagnosticare avansată
			if packed_scene == null:
				print("[DEBUG] 🔍 Null result - possible GLB corruption or import failure")
				_diagnose_glb_file(glb_path)
			elif not packed_scene is PackedScene:
				print("[DEBUG] 🔍 Wrong type returned: %s instead of PackedScene" % str(type_string(typeof(packed_scene))))
				# Încearcă să convertim Resource-ul la PackedScene dacă e posibil
				if packed_scene.has_method("instantiate"):
					print("[DEBUG] Attempting direct instantiation of Resource...")
					var scene = packed_scene.instantiate()
					if scene:
						add_child(scene)
						print("[DEBUG] ✓ Success via direct Resource instantiation!")
						_print_meshes_and_colors(scene, glb_path)
						_load_window_gltf_for_glb(glb_path)
						populate_tree_with_projects(imported_projects)
						_flash_reload_indicator()
						return true
		
		# Între tentative, strategy diferită de curățare
		if attempt < max_attempts - 1:
			print("[DEBUG] Retrying with different cleanup strategy...")
			
			# Strategii diferite de curățare pe fiecare tentativă
			if attempt == 0:
				# Prima dată: curățare standard
				_force_clear_resource_cache(glb_path)
			elif attempt == 1:
				# A doua oară: curățare + restart ResourceLoader
				_force_clear_resource_cache(glb_path)
				_force_delete_import_files(glb_path) 
				# Forțează colectarea gunoiului
				if Engine.has_method("force_garbage_collect"):
					print("[DEBUG] Forcing garbage collection...")
					# Nu există în Godot, dar putem aștepta mai mult
			elif attempt == 2:
				# A treia oară: recreează complet fișierul GLB și forțează reimport
				print("[DEBUG] Recreating GLB file to force recognition...")
				await _force_recreate_glb_file(glb_path)
				await _force_reimport_via_editor(glb_path)
			
			await get_tree().create_timer(0.5).timeout
	
	print("[ERROR] All loading attempts failed for: %s" % glb_path)
	return false

func _get_file_size(file_path: String) -> int:
	"""Returnează dimensiunea fișierului în bytes"""
	var file = FileAccess.open(file_path, FileAccess.READ)
	if file:
		var size = file.get_length()
		file.close()
		return size
	return 0

func _create_glb_copy_for_reimport(glb_path: String):
	"""Creează o copie temporară a GLB-ului pentru a forța reimportul"""
	var dir = DirAccess.open(glb_path.get_base_dir())
	if not dir:
		print("[DEBUG] ❌ Cannot access GLB directory")
		return
	
	var original_name = glb_path.get_file()
	var temp_name = original_name.get_basename() + "_temp.glb"
	var temp_path = glb_path.get_base_dir() + "/" + temp_name
	
	# Copiază fișierul la un nume temporar
	if dir.copy(original_name, temp_name) == OK:
		print("[DEBUG] ✓ Created temporary copy: %s" % temp_name)
		
		# Șterge originalul și toate fișierele asociate
		dir.remove(original_name)
		var import_file = original_name + ".import"
		if dir.file_exists(import_file):
			dir.remove(import_file)
		
		# Așteaptă să se proceseze ștergerea
		await get_tree().create_timer(0.3).timeout
		
		# Redenumește temporarul înapoi la numele original
		if dir.rename(temp_name, original_name) == OK:
			print("[DEBUG] ✓ GLB renamed back with forced refresh")
		else:
			print("[DEBUG] ❌ Failed to rename GLB back")
			# Fallback: copiază înapoi
			dir.copy(temp_name, original_name)
			dir.remove(temp_name)
	else:
		print("[DEBUG] ❌ Failed to create temporary GLB copy")

func _diagnose_glb_file(glb_path: String):
	"""Diagnostichează probleme cu fișierul GLB"""
	print("[DIAGNOSTIC] Analyzing GLB file: ", glb_path.get_file())
	
	# Verifică existența și dimensiunea
	var file_size = _get_file_size(glb_path)
	print("[DIAGNOSTIC] File size: %d bytes" % file_size)
	
	# Verifică primii bytes pentru magic number GLB 
	var glb_file = FileAccess.open(glb_path, FileAccess.READ)
	if glb_file:
		var magic = glb_file.get_buffer(4)
		var magic_str = magic.get_string_from_ascii()
		print("[DIAGNOSTIC] Magic bytes: %s" % magic_str)
		glb_file.close()
		
		if magic_str != "glTF":
			print("[DIAGNOSTIC] ❌ Invalid GLB magic number, expected 'glTF'")
			return false
	
	# Verifică dacă Godot poate detecta tipul fișierului
	if ResourceLoader.exists(glb_path):
		print("[DIAGNOSTIC] ✓ ResourceLoader can detect file")
		
		# Încearcă să încărce resursa pentru a verifica tipul
		var test_resource = ResourceLoader.load(glb_path, "", ResourceLoader.CACHE_MODE_IGNORE)
		if test_resource:
			var type_name = test_resource.get_class()
			print("[DIAGNOSTIC] Detected type: %s" % type_name)
			
			if test_resource is PackedScene:
				print("[DIAGNOSTIC] ✓ Resource is PackedScene (correct for GLB)")
			else:
				print("[DIAGNOSTIC] ⚠️ Resource is not PackedScene: %s" % type_name)
		else:
			print("[DIAGNOSTIC] ⚠️ ResourceLoader exists but cannot load resource")
	else:
		print("[DIAGNOSTIC] ❌ ResourceLoader cannot detect file")
	
	# Verifică fișierul .import asociat
	var import_path = glb_path + ".import"
	if FileAccess.file_exists(import_path):
		print("[DIAGNOSTIC] ✓ Import file exists")
		var import_file = FileAccess.open(import_path, FileAccess.READ)
		if import_file:
			var import_content = import_file.get_as_text()
			import_file.close()
			if "PackedScene" in import_content:
				print("[DIAGNOSTIC] ✓ Import configured for PackedScene")
			else:
				print("[DIAGNOSTIC] ⚠️ Import NOT configured for PackedScene")
			
			if "scene" in import_content:
				print("[DIAGNOSTIC] ✓ Scene importer detected")
			else:
				print("[DIAGNOSTIC] ❌ Scene importer NOT detected")
	else:
		print("[DIAGNOSTIC] ❌ No import file - Godot hasn't processed this GLB")
	
	return true
	
	# Verifică existența fișierului
	if not FileAccess.file_exists(glb_path):
		print("[DIAGNOSTIC] ❌ GLB file does not exist")
		return
	
	# Verifică dimensiunea
	var size = _get_file_size(glb_path)
	print("[DIAGNOSTIC] File size: %d bytes" % size)
	
	if size < 100:
		print("[DIAGNOSTIC] ⚠️  File too small, may be incomplete")
		return
	
	# Verifică fișierul .import
	var import_file = glb_path + ".import"
	var import_exists = FileAccess.file_exists(import_file)
	print("[DIAGNOSTIC] Import file exists: %s" % str(import_exists))
	
	if import_exists:
		var import_size = _get_file_size(import_file)
		print("[DIAGNOSTIC] Import file size: %d bytes" % import_size)
	
	# Verifică dacă Godot poate recunoaște fișierul
	var resource_exists = ResourceLoader.exists(glb_path)
	print("[DIAGNOSTIC] ResourceLoader recognizes file: %s" % str(resource_exists))
	
	# Verifică cache-ul
	var cached = ResourceLoader.has_cached(glb_path)
	print("[DIAGNOSTIC] File is cached: %s" % str(cached))
	
	# Încearcă să citească headerul GLB pentru validare
	var header_file = FileAccess.open(glb_path, FileAccess.READ)
	if header_file:
		var header = header_file.get_buffer(12)  # GLB header = 12 bytes
		header_file.close()
		
		if header.size() >= 4:
			var magic = header.slice(0, 4).get_string_from_ascii()
			print("[DIAGNOSTIC] File magic: '%s' (should be 'glTF')" % magic)
			
			if magic != "glTF":
				print("[DIAGNOSTIC] ❌ Invalid GLB file format - magic bytes incorrect")
			else:
				print("[DIAGNOSTIC] ✅ GLB header appears valid")
		else:
			print("[DIAGNOSTIC] ❌ Cannot read GLB header")
	else:
		print("[DIAGNOSTIC] ❌ Cannot open GLB file for reading")

func _flash_reload_indicator():
	"""Flash vizual pentru a indica reload-ul reușit"""
	var flash_label = Label.new()
	flash_label.text = "🔄 RELOADED"
	flash_label.position = Vector2(get_viewport().get_visible_rect().size.x - 150, 10)
	flash_label.size = Vector2(140, 30)
	flash_label.add_theme_color_override("font_color", Color.GREEN)
	flash_label.add_theme_font_size_override("font_size", 16)
	canvas.add_child(flash_label)
	
	# Animație fade out
	var tween = create_tween()
	tween.tween_property(flash_label, "modulate:a", 0.0, 2.0)
	tween.tween_callback(flash_label.queue_free.bind())

# === IFC Space Export ===
func _on_export_ifc_btn_pressed():
	"""Exportă IfcSpace-urile din scena curentă în format IFC"""
	print("[DEBUG] Starting IFC Space export...")
	
	# Verifică dacă avem IfcSpace-uri în scenă
	var space_nodes = _find_ifcspace_nodes()
	if space_nodes.is_empty():
		print("[WARNING] No IfcSpace elements found in scene")
		_show_export_message("No IfcSpace elements found to export", false)
		return
	
	# Creează folder pentru export dacă nu există
	var export_dir = "exported_ifc"
	if not DirAccess.dir_exists_absolute(export_dir):
		DirAccess.open(".").make_dir(export_dir)
	
	# Generează nume fișier cu timestamp
	var timestamp = Time.get_datetime_string_from_system().replace(":", "-").replace(" ", "_")
	var base_name = "spaces_export_" + timestamp
	var godot_data_path = export_dir + "/" + base_name + "_geometry.json"
	var ifc_output_path = export_dir + "/" + base_name + ".ifc"
	
	# Exportă geometria din Godot
	var geometry_data = _extract_space_geometry_data(space_nodes)
	if not _save_json_file(godot_data_path, geometry_data):
		_show_export_message("Failed to save geometry data", false)
		return
	
	# Găsește cel mai recent fișier de mapping
	var mapping_path = _find_latest_mapping_file()
	if mapping_path == "":
		print("[ERROR] No mapping file found. Import a DXF/GLB project first.")
		_show_export_message("No mapping file found. Import a DXF/GLB project first.", false)
		return
	
	# Rulează exportul Python IFC
	var success = _run_python_ifc_export(godot_data_path, mapping_path, ifc_output_path)
	
	if success:
		print("[SUCCESS] IFC export completed: ", ifc_output_path)
		_show_export_message("IFC export completed successfully!\nFile: " + ifc_output_path, true)
	else:
		print("[ERROR] IFC export failed")
		_show_export_message("IFC export failed. Check console for details.", false)

func _find_ifcspace_nodes() -> Array:
	"""Găsește toate nodurile IfcSpace din scenă"""
	var space_nodes = []
	_find_ifcspace_recursive(self, space_nodes)
	print("[DEBUG] Found %d IfcSpace nodes" % space_nodes.size())
	return space_nodes

func _find_ifcspace_recursive(node: Node, space_nodes: Array):
	"""Caută recursiv nodurile IfcSpace"""
	var is_ifcspace = false
	
	# Verifică dacă nodul curent este un MeshInstance3D
	if node is MeshInstance3D:
		# Prioritate 1: Verifică metadata layer
		if node.has_meta("layer"):
			var layer = node.get_meta("layer")
			if layer == "IfcSpace":
				is_ifcspace = true
				print("[DEBUG] Found IfcSpace by metadata: ", node.name)
		
		# Prioritate 2: Verifică numele nodului doar dacă nu a fost găsit prin metadata
		elif "IfcSpace" in str(node.name):
			is_ifcspace = true
			print("[DEBUG] Found IfcSpace by name: ", node.name)
		
		# Adaugă nodul doar o singură dată
		if is_ifcspace:
			# Verifică dacă nodul nu există deja în array (pentru siguranță extra)
			if node not in space_nodes:
				space_nodes.append(node)
			else:
				print("[WARNING] Prevented duplicate IfcSpace node: ", node.name)
	
	# Recursiv în copii
	for child in node.get_children():
		_find_ifcspace_recursive(child, space_nodes)

func _extract_space_geometry_data(space_nodes: Array) -> Dictionary:
	"""Extrage datele geometrice din nodurile IfcSpace și le îmbogățește cu datele din JSON de mapare"""
	var spaces_data = []
	
	# Încarcă datele din fișierul de mapare JSON pentru a obține valorile corecte
	var mapping_data = _load_mapping_data_for_spaces()
	
	for node in space_nodes:
		if not node is MeshInstance3D or not node.mesh:
			continue
			
		var space_data = {}
		space_data["mesh_name"] = str(node.name)
		space_data["uuid"] = node.get_meta("uuid") if node.has_meta("uuid") else ""
		
		# Extrage vertices din mesh pentru geometria 3D
		var vertices = []
		var mesh = node.mesh
		
		if mesh is ArrayMesh and mesh.get_surface_count() > 0:
			var arrays = mesh.surface_get_arrays(0)
			if arrays[Mesh.ARRAY_VERTEX]:
				var vertex_array = arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array
				for vertex in vertex_array:
					# Transformă vertex-ul în spațiul world
					var world_vertex = node.to_global(vertex)
					vertices.append([world_vertex.x, world_vertex.y, world_vertex.z])
		
		# Limitează numărul de vertices pentru a evita duplicatele (în general conturul de bază)
		if vertices.size() > 100:
			# Încearcă să extragi doar conturul exterior (primul segment)
			var step = max(1, vertices.size() / 20)  # Max 20 puncte pentru contur
			var simplified_vertices = []
			for i in range(0, vertices.size(), step):
				simplified_vertices.append(vertices[i])
			vertices = simplified_vertices
		
		space_data["vertices"] = vertices
		space_data["vertex_count"] = vertices.size()
		
		# IMPORTANT: Înlocuiește valorile din metadata cu cele corecte din JSON de mapare
		var mapping_entry = _find_mapping_entry_for_space(space_data["uuid"], space_data["mesh_name"], mapping_data)
		if mapping_entry:
			# Folosește valorile calculate corect din JSON (inclusiv Opening_area)
			space_data["height"] = _calculate_space_height_from_xdata(mapping_entry)
			space_data["area"] = float(mapping_entry.get("area", 0.0))
			space_data["volume"] = float(mapping_entry.get("volume", 0.0))
			space_data["perimeter"] = float(mapping_entry.get("perimeter", 0.0))
			space_data["lateral_area"] = float(mapping_entry.get("lateral_area", 0.0))
			
			print("[DEBUG] Enhanced space data from JSON mapping: %s" % space_data["mesh_name"])
			print("  - Area: %.3fm², Perimeter: %.3fm, Lateral Area: %.3fm²" % [space_data["area"], space_data["perimeter"], space_data["lateral_area"]])
			print("  - Volume: %.3fm³, Height: %.3fm, UUID: %s" % [space_data["volume"], space_data["height"], space_data["uuid"]])
		else:
			# Fallback: folosește metadata din Godot dacă nu găsim în JSON
			space_data["height"] = node.get_meta("height") if node.has_meta("height") else 2.8
			space_data["area"] = node.get_meta("area") if node.has_meta("area") else 0.0
			space_data["volume"] = node.get_meta("volume") if node.has_meta("volume") else 0.0
			space_data["perimeter"] = 0.0  # Nu există în metadata Godot
			space_data["lateral_area"] = 0.0  # Nu există în metadata Godot
			
			print("[WARNING] Could not find mapping data for space: %s, using fallback values" % space_data["mesh_name"])
		
		spaces_data.append(space_data)
		print("[DEBUG] Extracted enhanced geometry for space: %s (%d vertices)" % [space_data["mesh_name"], vertices.size()])
	
	return {"spaces": spaces_data, "export_timestamp": Time.get_unix_time_from_system()}

func _load_mapping_data_for_spaces() -> Array:
	"""Încarcă datele din fișierul JSON de mapare pentru spații IfcSpace"""
	var mapping_file = _find_latest_mapping_file()
	if mapping_file.is_empty():
		print("[WARNING] No mapping file found for IFC Space export")
		return []
	
	print("[DEBUG] Loading mapping data from: %s" % mapping_file)
	
	var file = FileAccess.open(mapping_file, FileAccess.READ)
	if not file:
		print("[ERROR] Could not open mapping file: %s" % mapping_file)
		return []
	
	var json_string = file.get_as_text()
	file.close()
	
	var json = JSON.new()
	var parse_result = json.parse(json_string)
	if parse_result != OK:
		print("[ERROR] Failed to parse JSON mapping file: %s" % json.get_error_message())
		return []
	
	var mapping_data = json.data
	if not mapping_data is Array:
		print("[ERROR] Mapping file does not contain an array")
		return []
	
	# Filtrează doar entitățile IfcSpace
	var space_entries = []
	for entry in mapping_data:
		if entry is Dictionary and entry.get("layer", "") == "IfcSpace":
			space_entries.append(entry)
	
	print("[DEBUG] Found %d IfcSpace entries in mapping file" % space_entries.size())
	return space_entries

func _find_mapping_entry_for_space(uuid: String, mesh_name: String, mapping_data: Array) -> Dictionary:
	"""Găsește intrarea din mapping care corespunde cu spațiul dat"""
	
	# Prioritate 1: Caută după UUID exact
	for entry in mapping_data:
		if entry.get("uuid", "") == uuid and not uuid.is_empty():
			print("[DEBUG] Found mapping entry by UUID: %s" % uuid)
			return entry
	
	# Prioritate 2: Caută după mesh_name exact
	for entry in mapping_data:
		if entry.get("mesh_name", "") == mesh_name and not mesh_name.is_empty():
			print("[DEBUG] Found mapping entry by mesh_name: %s" % mesh_name)
			return entry
	
	# Prioritate 3: Caută după partea de bază a numelui (fără sufixe)
	var base_name = mesh_name.split("_")[0] if "_" in mesh_name else mesh_name
	for entry in mapping_data:
		var entry_base_name = entry.get("mesh_name", "").split("_")[0] if "_" in entry.get("mesh_name", "") else entry.get("mesh_name", "")
		if entry_base_name == base_name and not base_name.is_empty():
			print("[DEBUG] Found mapping entry by base name: %s -> %s" % [base_name, entry.get("mesh_name", "")])
			return entry
	
	print("[WARNING] No mapping entry found for space: UUID=%s, mesh_name=%s" % [uuid, mesh_name])
	return {}

func _calculate_space_height_from_xdata(mapping_entry: Dictionary) -> float:
	"""Calculează înălțimea spațiului din datele XDATA din mapping"""
	
	# Caută în XDATA pentru înălțime
	var xdata = mapping_entry.get("xdata", {})
	if xdata is Dictionary:
		# Caută câmpuri comune pentru înălțime
		for height_field in ["Height", "height", "Space_Height", "floor_height"]:
			if xdata.has(height_field):
				var height_value = xdata[height_field]
				if height_value is String:
					# Dacă este string, încearcă să-l convertești la float
					return float(height_value) if height_value.is_valid_float() else 2.8
				elif height_value is float or height_value is int:
					return float(height_value)
		
		print("[DEBUG] XDATA found but no height field: %s" % str(xdata.keys()))
	
	# Fallback: calculează înălțimea din volum și arie dacă sunt disponibile
	var volume = float(mapping_entry.get("volume", 0.0))
	var area = float(mapping_entry.get("area", 0.0))
	
	if volume > 0.0 and area > 0.0:
		var calculated_height = volume / area
		print("[DEBUG] Calculated height from volume/area: %.3fm (V=%.3f, A=%.3f)" % [calculated_height, volume, area])
		return calculated_height
	
	# Fallback final: înălțime standard
	print("[DEBUG] Using default height: 2.8m")
	return 2.8

func _find_latest_mapping_file() -> String:
	"""Găsește cel mai recent fișier de mapping din folderul curent"""
	var mapping_files = []
	var dir = DirAccess.open(".")
	
	if dir:
		dir.list_dir_begin()
		var file_name = dir.get_next()
		while file_name != "":
			if file_name.ends_with("_mapping.json"):
				var full_path = dir.get_current_dir() + "/" + file_name
				var file_time = FileAccess.get_modified_time(full_path)
				mapping_files.append({"path": full_path, "time": file_time})
			file_name = dir.get_next()
		dir.list_dir_end()
	
	if mapping_files.is_empty():
		return ""
	
	# Sortează după timp și returnează cel mai recent
	mapping_files.sort_custom(func(a, b): return a.time > b.time)
	var latest = mapping_files[0]["path"]
	print("[DEBUG] Using mapping file: ", latest)
	return latest

func _save_json_file(file_path: String, data: Dictionary) -> bool:
	"""Salvează datele în format JSON"""
	var file = FileAccess.open(file_path, FileAccess.WRITE)
	if not file:
		print("[ERROR] Cannot create file: ", file_path)
		return false
	
	var json_string = JSON.stringify(data, "\t")
	file.store_string(json_string)
	file.close()
	
	print("[DEBUG] Saved geometry data: ", file_path)
	return true

func _run_python_ifc_export(godot_data_path: String, mapping_path: String, ifc_output_path: String) -> bool:
	"""Rulează script-ul Python pentru exportul IFC"""
	var script_path = "python/ifc_space_exporter.py"
	var project_name = "Godot CAD Viewer Spaces"
	
	var args = [script_path, godot_data_path, mapping_path, ifc_output_path, project_name]
	var output = []
	
	print("[DEBUG] Running Python IFC export: python ", args)
	var exit_code = OS.execute("python", args, output, true)
	
	print("[PYTHON IFC OUTPUT] ", output)
	print("[PYTHON IFC EXIT CODE] ", exit_code)
	
	return exit_code == 0

func _show_export_message(message: String, success: bool):
	"""Afișează un mesaj de export în UI"""
	var message_label = Label.new()
	message_label.text = message
	message_label.position = Vector2(get_viewport().get_visible_rect().size.x / 2 - 200, 100)
	message_label.size = Vector2(400, 100)
	message_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	message_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	message_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	
	if success:
		message_label.add_theme_color_override("font_color", Color.GREEN)
	else:
		message_label.add_theme_color_override("font_color", Color.RED)
	
	message_label.add_theme_font_size_override("font_size", 14)
	
	# Fundal semi-transparent
	var panel = Panel.new()
	panel.position = message_label.position - Vector2(10, 10)
	panel.size = message_label.size + Vector2(20, 20)
	panel.add_theme_color_override("bg_color", Color(0, 0, 0, 0.7))
	
	canvas.add_child(panel)
	canvas.add_child(message_label)
	
	# Animație fade out după 5 secunde
	var tween = create_tween()
	tween.tween_interval(5.0)  # Schimbat din tween_delay în tween_interval
	tween.tween_property(panel, "modulate:a", 0.0, 1.0)
	tween.parallel().tween_property(message_label, "modulate:a", 0.0, 1.0)
	tween.tween_callback(panel.queue_free.bind())
	tween.tween_callback(message_label.queue_free.bind())

# === MULTI-LEVEL IFC EXPORT ===
func _on_export_multi_ifc_btn_pressed():
	"""Exportă toate fișierele DXF încărcate ca multi-level building în IFC"""
	print("[DEBUG] Starting Multi-Level IFC export...")
	
	# Verifică dacă avem proiecte importate
	if imported_projects.is_empty():
		print("[WARNING] No DXF projects loaded")
		_show_export_message("No DXF projects loaded. Import some DXF files first.", false)
		return
	
	# Creează folder pentru export dacă nu există
	var export_dir = "exported_ifc"
	if not DirAccess.dir_exists_absolute(export_dir):
		DirAccess.open(".").make_dir(export_dir)
	
	# Generează nume fișier cu timestamp
	var timestamp = Time.get_datetime_string_from_system().replace(":", "-").replace(" ", "_")
	var building_name = "multi_level_building_" + timestamp
	var ifc_output_path = export_dir + "/" + building_name + ".ifc"
	
	# Colectează toate fișierele DXF importate
	var dxf_files = []
	for project_name in imported_projects.keys():
		if project_name.ends_with(".dxf"):
			dxf_files.append(project_name)
	
	if dxf_files.is_empty():
		print("[WARNING] No DXF files found in imported projects")
		_show_export_message("No DXF files found. Only DXF files can be exported to multi-level IFC.", false)
		return
	
	# Rulează exportul Python Multi-Level IFC
	var success = _run_python_multi_ifc_export(dxf_files, ifc_output_path)
	
	if success:
		print("[SUCCESS] Multi-Level IFC export completed: ", ifc_output_path)
		_show_export_message("Multi-Level IFC export completed successfully!\nFile: " + ifc_output_path + "\nLevels: " + str(dxf_files.size()), true)
	else:
		print("[ERROR] Multi-Level IFC export failed")
		_show_export_message("Multi-Level IFC export failed. Check console for details.", false)

func _run_python_multi_ifc_export(dxf_files: Array, ifc_output_path: String) -> bool:
	"""Rulează script-ul Python pentru exportul Multi-Level IFC"""
	var script_path = "python/ifc_integration.py"
	
	var args = [script_path, ifc_output_path]
	for dxf_file in dxf_files:
		args.append(dxf_file)
	
	var output = []
	
	print("[DEBUG] Running Python Multi-Level IFC export: python ", args)
	var exit_code = OS.execute("python", args, output, true)
	
	print("[PYTHON MULTI IFC OUTPUT] ", output)
	print("[PYTHON MULTI IFC EXIT CODE] ", exit_code)
	
	return exit_code == 0

# === CUT SHADER INTEGRATION METHODS ===

func _setup_cut_shader_integration():
	"""Inițializează integrarea sistemului cut shader"""
	print("[CutShader] Setting up cut shader integration...")
	
	# Găsește nodul de integrare cut shader
	cut_shader_integration = get_node_or_null("CutShaderIntegration")
	if cut_shader_integration:
		print("[CutShader] Found cut shader integration node")
		# Conectează semnalele
		if cut_shader_integration.has_signal("section_dxf_exported"):
			cut_shader_integration.section_dxf_exported.connect(_on_cut_shader_dxf_exported)
		if cut_shader_integration.has_signal("cut_shader_preview_updated"):
			cut_shader_integration.cut_shader_preview_updated.connect(_on_cut_shader_preview_updated)
	else:
		print("[CutShader] Cut shader integration node not found")
	
	# Inițializează materialul pentru secțiuni
	_init_section_material()
	
	# Setup section controls în UI - DISABLED (UI removal while keeping backend)
	# _setup_section_controls()
	
	print("[CutShader] Cut shader integration setup complete")

func _init_section_material():
	"""Inițializează materialul pentru efectele de secțiune"""
	section_material = StandardMaterial3D.new()
	section_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	section_material.albedo_color = Color(1.0, 0.0, 0.0, 0.3)  # Roșu semi-transparent
	section_material.no_depth_test = false
	section_material.cull_mode = BaseMaterial3D.CULL_DISABLED

func _setup_section_controls():
	"""Creează controalele UI pentru secțiuni"""
	if not canvas:
		print("[CutShader] No canvas found for section controls")
		return
	
	# Creează panelul pentru controalele de secțiune
	section_controls_panel = Panel.new()
	section_controls_panel.name = "SectionControlsPanel"
	section_controls_panel.position = Vector2(10, get_viewport().get_visible_rect().size.y - 200)
	section_controls_panel.size = Vector2(220, 180)
	section_controls_panel.add_theme_color_override("bg_color", Color(0.1, 0.1, 0.2, 0.9))
	canvas.add_child(section_controls_panel)
	
	var y_offset = 10
	
	# Title
	var title = Label.new()
	title.text = "Section Controls"
	title.position = Vector2(10, y_offset)
	title.add_theme_color_override("font_color", Color.WHITE)
	title.add_theme_font_size_override("font_size", 12)
	section_controls_panel.add_child(title)
	y_offset += 25
	
	# Horizontal Section
	h_section_checkbox = CheckBox.new()
	h_section_checkbox.text = "Horizontal Section"
	h_section_checkbox.position = Vector2(10, y_offset)
	h_section_checkbox.button_pressed = horizontal_section_enabled
	h_section_checkbox.toggled.connect(_on_horizontal_section_toggled)
	section_controls_panel.add_child(h_section_checkbox)
	y_offset += 25
	
	# Horizontal Section Z Position
	var h_z_label = Label.new()
	h_z_label.text = "H-Section Z:"
	h_z_label.position = Vector2(10, y_offset)
	h_z_label.add_theme_color_override("font_color", Color.WHITE)
	section_controls_panel.add_child(h_z_label)
	
	h_section_slider = HSlider.new()
	h_section_slider.position = Vector2(90, y_offset)
	h_section_slider.size = Vector2(120, 20)
	h_section_slider.min_value = -10.0
	h_section_slider.max_value = 10.0
	h_section_slider.step = 0.1
	h_section_slider.value = horizontal_section_z
	h_section_slider.value_changed.connect(_on_horizontal_section_z_changed)
	section_controls_panel.add_child(h_section_slider)
	y_offset += 25
	
	# Horizontal Section Depth
	var h_depth_label = Label.new()
	h_depth_label.text = "H-Depth:"
	h_depth_label.position = Vector2(10, y_offset)
	h_depth_label.add_theme_color_override("font_color", Color.WHITE)
	section_controls_panel.add_child(h_depth_label)
	
	h_depth_slider = HSlider.new()
	h_depth_slider.position = Vector2(90, y_offset)
	h_depth_slider.size = Vector2(120, 20)
	h_depth_slider.min_value = 0.1
	h_depth_slider.max_value = 5.0
	h_depth_slider.step = 0.1
	h_depth_slider.value = horizontal_section_depth
	h_depth_slider.value_changed.connect(_on_horizontal_depth_changed)
	section_controls_panel.add_child(h_depth_slider)
	y_offset += 30
	
	# Vertical Section
	v_section_checkbox = CheckBox.new()
	v_section_checkbox.text = "Vertical Section"
	v_section_checkbox.position = Vector2(10, y_offset)
	v_section_checkbox.button_pressed = vertical_section_enabled
	v_section_checkbox.toggled.connect(_on_vertical_section_toggled)
	section_controls_panel.add_child(v_section_checkbox)
	y_offset += 25
	
	# Cut Shader Export Button
	var export_btn = Button.new()
	export_btn.text = "Export Cut Shader DXF"
	export_btn.position = Vector2(10, y_offset)
	export_btn.size = Vector2(200, 25)
	export_btn.pressed.connect(_export_cut_shader_dxf)
	section_controls_panel.add_child(export_btn)

func _get_current_section_data() -> Dictionary:
	"""Returnează datele curente ale secțiunilor pentru integrarea cut shader"""
	var section_data = {}
	
	if horizontal_section_enabled:
		section_data["horizontal"] = {
			"origin": Vector3(0, 0, horizontal_section_z),
			"normal": Vector3(0, 0, 1),
			"enabled": true,
			"depth_range": [horizontal_section_z - horizontal_section_depth/2, 
							horizontal_section_z + horizontal_section_depth/2]
		}
	
	if vertical_section_enabled:
		section_data["vertical"] = {
			"origin": Vector3(vertical_section_x, vertical_section_y, 0),
			"normal": Vector3(1, 0, 0),  # sau Vector3(0, 1, 0) pentru vertical Y
			"enabled": true,
			"depth_range": [vertical_section_x - vertical_section_depth/2,
							vertical_section_x + vertical_section_depth/2]
		}
	
	# Adaugă informații despre camera pentru secțiuni dinamice
	if camera:
		var cam_pos = camera.global_transform.origin
		var cam_forward = -camera.global_transform.basis.z
		
		section_data["camera_section"] = {
			"origin": cam_pos,
			"normal": cam_forward,
			"enabled": true,
			"depth_range": [0.0, 3.0]
		}
	
	return section_data

func _export_cut_shader_dxf():
	"""Exportă secțiunea curentă folosind sistemul cut shader"""
	if not cut_shader_integration:
		print("[CutShader] Cut shader integration not available")
		return
	
	print("[CutShader] Initiating cut shader DXF export...")
	
	# Actualizează datele de secțiune
	current_section_state = _get_current_section_data()
	
	# Apelează sistemul cut shader pentru export
	if cut_shader_integration.has_method("_export_dxf_section"):
		cut_shader_integration._export_dxf_section()
	else:
		print("[CutShader] Export method not found in cut shader integration")

func _on_cut_shader_dxf_exported(file_path: String):
	"""Handler pentru semnalul de export DXF completat"""
	print("[CutShader] DXF export completed: ", file_path)
	
	# Afișează mesaj de succes
	var message = "Cut Shader DXF exported successfully!\nFile: " + file_path.get_file()
	_show_export_message(message, true)

func _on_cut_shader_preview_updated(preview_data: Dictionary):
	"""Handler pentru actualizarea preview-ului cut shader"""
	print("[CutShader] Preview updated: ", preview_data)
	
	# Aici poți adăuga logica pentru afișarea preview-ului în viewer
	# De exemplu, overlay-uri sau highlight-uri pe mesh-uri

func set_section_for_view(view_name: String):
	"""Setează parametrii de secțiune bazați pe view-ul curent"""
	match view_name:
		"top":
			horizontal_section_enabled = true
			horizontal_section_z = 1.5  # Secțiune standard la înălțimea camerei
			_update_section_ui()
		"front", "back":
			vertical_section_enabled = true
			vertical_section_y = 0.0
			_update_section_ui()
		"left", "right":
			vertical_section_enabled = true
			vertical_section_x = 0.0
			_update_section_ui()
		"free":
			# În view-ul liber, folosește poziția camerei pentru secțiuni dinamice
			_update_dynamic_sections()

func _update_section_ui():
	"""Actualizează UI-ul pentru a reflecta starea curentă a secțiunilor"""
	if h_section_checkbox:
		h_section_checkbox.button_pressed = horizontal_section_enabled
	if h_section_slider:
		h_section_slider.value = horizontal_section_z
	if h_depth_slider:
		h_depth_slider.value = horizontal_section_depth
	if v_section_checkbox:
		v_section_checkbox.button_pressed = vertical_section_enabled

func _update_dynamic_sections():
	"""Actualizează secțiunile dinamice bazate pe poziția camerei"""
	if camera and cut_shader_integration:
		var cam_pos = camera.global_transform.origin
		var cam_forward = -camera.global_transform.basis.z
		
		# Actualizează secțiunea bazată pe camera
		horizontal_section_z = cam_pos.z
		
		# Sincronizează cu sistemul cut shader
		if cut_shader_integration.has_method("_sync_with_existing_sections"):
			cut_shader_integration._sync_with_existing_sections()

# === FUNCȚII UTILITARE LIPSĂ ===

func _update_info_label():
	"""Actualizează label-ul cu informații despre starea curentă"""
	if coord_label:
		var info_text = "Z-Min: %.2f | Z-Max: %.2f | Drawing Plane: %.2f" % [z_min, z_max, drawing_plane_z]
		coord_label.text = info_text

func _update_z_spinboxes():
	"""Actualizează controalele UI pentru Z-depth"""
	# Această funcție ar trebui să actualizeze SpinBox-urile pentru z_min, z_max și drawing_plane_z
	# Dacă controalele UI există, le actualizează cu valorile curente
	print("[DEBUG] Z-spinboxes updated: z_min=%.2f, z_max=%.2f, drawing_plane_z=%.2f" % [z_min, z_max, drawing_plane_z])



func _exit_tree():
	# Oprește procesul watchdog la ieșire
	if watchdog_process > 0:
		OS.kill(watchdog_process)
		print("[DEBUG] Stopped DXF watchdog process")

# === GEOJSON INTEGRATION ===
# Integrează suport pentru încărcare și afișare GeoJSON, cu centrare automată și vedere de sus
func load_geojson(file_path: String, scale_factor: float = 100000.0, extrusion_height: float = 15.0, center_lat: float = 0.0, center_lon: float = 0.0):
	var buildings := []
	var all_points := []
	if not FileAccess.file_exists(file_path):
		push_error("GeoJSON file does not exist: " + file_path)
		return
	var file = FileAccess.open(file_path, FileAccess.READ)
	if file == null:
		push_error("Cannot open GeoJSON file: " + file_path)
		return
	var json_text = file.get_as_text()
	file.close()
	var json = JSON.new()
	var error = json.parse(json_text)
	if error != OK:
		push_error("GeoJSON parse error: " + json.get_error_message())
		return
	var data = json.data
	if not data.has("features"):
		push_error("GeoJSON has no features array!")
		return
	
	print("[GeoJSON] Loading ", data.features.size(), " features...")
	var feature_count = 0
	var skipped_count = 0
	
	for feature in data.features:
		if not feature.has("geometry"):
			continue
		var geometry = feature.geometry
		var properties = feature.get("properties", {})
		var geom_type = geometry.get("type", "")
		
		# Filtrare: Skip puncte simple care nu sunt importante (ex: stâlpi de electricitate)
		if geom_type == "Point":
			# Păstrează doar puncte importante (clădiri, POI-uri importante)
			if not properties.has("amenity") and not properties.has("place") and not properties.has("tourism"):
				skipped_count += 1
				continue  # Skip power towers și alte puncte nesemnificative
		
		match geom_type:
			"Polygon":
				_geojson_create_polygon(geometry.coordinates, properties, scale_factor, extrusion_height, center_lat, center_lon, buildings, all_points)
			"MultiPolygon":
				for polygon in geometry.coordinates:
					_geojson_create_polygon(polygon, properties, scale_factor, extrusion_height, center_lat, center_lon, buildings, all_points)
			"LineString":
				# Filtrare opțională: doar drumuri importante
				if properties.has("highway"):
					_geojson_create_linestring(geometry.coordinates, properties, scale_factor, center_lat, center_lon, all_points)
			"Point":
				_geojson_create_point(geometry.coordinates, properties, scale_factor, center_lat, center_lon, all_points)
		
		feature_count += 1
		# Afișează progres la fiecare 100 de features
		if feature_count % 100 == 0:
			print("[GeoJSON] Processed ", feature_count, "/", data.features.size(), " features...")
			await get_tree().process_frame  # Permite UI-ului să răspundă
	
	print("[GeoJSON] Loaded ", feature_count, " features (skipped ", skipped_count, " insignificant points)")
	# Centrează camera pe centrul geometric
	if all_points.size() > 0:
		var bbox := AABB(all_points[0], Vector3.ZERO)
		for pt in all_points:
			bbox = bbox.expand(pt)
		var center = bbox.position + bbox.size * 0.5
		_fit_camera_to_bbox(bbox)
		_set_top_view()
		# Camera deasupra centrului (Z = verticală în sistemul nostru)
		camera.global_position = Vector3(center.x, center.y, camera.global_position.z)
		camera.look_at(center, Vector3.UP)
	print("GeoJSON loaded: ", buildings.size(), " buildings/objects created.")

# Helpers pentru meshuri GeoJSON
func _geojson_create_polygon(coordinates: Array, properties: Dictionary, scale_factor: float, extrusion_height: float, center_lat: float, center_lon: float, buildings: Array, all_points: Array):
	if coordinates.is_empty():
		return
	var outer_ring = coordinates[0]
	if outer_ring.size() < 3:
		return
	var points = []
	for coord in outer_ring:
		var lon = coord[0]
		var lat = coord[1]
		var pos = _geojson_latlon_to_local(lat, lon, scale_factor, center_lat, center_lon)
		points.append(pos)
		all_points.append(pos)
	
	# Verifică dacă ultimul punct este identic cu primul (poligon închis) și elimină duplicatul
	if points.size() > 0 and points[0].distance_to(points[points.size() - 1]) < 0.001:
		points.remove_at(points.size() - 1)
	
	if points.size() < 3:
		return
	
	var mesh_instance = MeshInstance3D.new()
	var array_mesh = ArrayMesh.new()
	var arrays = []
	arrays.resize(Mesh.ARRAY_MAX)
	var vertices = PackedVector3Array()
	var indices = PackedInt32Array()
	var normals = PackedVector3Array()
	
	var is_building = properties.has("building") and properties.building != "no"
	var height = extrusion_height
	if is_building:
		if properties.has("height"):
			height = float(properties.get("height", extrusion_height))
		elif properties.has("building:levels"):
			height = float(properties.get("building:levels", 1)) * 3.0
		
		# Creează baza (jos) cu triangulație corectă
		var base_indices = _triangulate_polygon_2d(points)
		var base_start = vertices.size()
		for point in points:
			vertices.append(point)
			normals.append(Vector3(0, 0, -1))  # Normală în jos pentru bază
		for idx in base_indices:
			indices.append(base_start + idx)
		
		# Creează pereții laterali
		var wall_start = vertices.size()
		for i in range(points.size()):
			var p1 = points[i]
			var p2 = points[(i + 1) % points.size()]
			
			# Calculează normala pentru perete (perpendiculară pe segmentul p1-p2)
			var edge = p2 - p1
			var wall_normal = Vector3(-edge.y, edge.x, 0).normalized()
			
			var idx = vertices.size()
			vertices.append(p1)
			normals.append(wall_normal)
			vertices.append(p2)
			normals.append(wall_normal)
			vertices.append(p2 + Vector3(0, 0, height))
			normals.append(wall_normal)
			vertices.append(p1 + Vector3(0, 0, height))
			normals.append(wall_normal)
			
			# Două triunghiuri pentru perete
			indices.append(idx)
			indices.append(idx + 1)
			indices.append(idx + 2)
			indices.append(idx)
			indices.append(idx + 2)
			indices.append(idx + 3)
		
		# Creează acoperișul (sus) cu triangulație corectă
		var roof_points = []
		for point in points:
			roof_points.append(point + Vector3(0, 0, height))
		var roof_indices = _triangulate_polygon_2d(points)  # Aceeași triangulație
		var roof_start = vertices.size()
		for point in roof_points:
			vertices.append(point)
			normals.append(Vector3(0, 0, 1))  # Normală în sus pentru acoperiș
		# Inversăm ordinea pentru ca fața să fie corectă (în sus)
		for i in range(roof_indices.size() - 1, -1, -1):
			indices.append(roof_start + roof_indices[i])
	else:
		# Pentru non-clădiri (parcuri, terenuri), doar o suprafață plană
		var flat_indices = _triangulate_polygon_2d(points)
		var flat_start = vertices.size()
		for point in points:
			vertices.append(point)
			normals.append(Vector3(0, 0, 1))
		for idx in flat_indices:
			indices.append(flat_start + idx)
	
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_INDEX] = indices
	arrays[Mesh.ARRAY_NORMAL] = normals
	array_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	mesh_instance.mesh = array_mesh
	var material = StandardMaterial3D.new()
	# Activează fața dublă și dezactivează culling pentru vizibilitate din toate unghiurile
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	if is_building:
		material.albedo_color = Color(0.8, 0.7, 0.6, 1.0)
	elif properties.has("landuse"):
		material.albedo_color = Color(0.4, 0.7, 0.3, 0.7)
	elif properties.has("leisure"):
		material.albedo_color = Color(0.3, 0.8, 0.4, 0.8)
	else:
		material.albedo_color = Color(0.7, 0.7, 0.7, 0.5)
	mesh_instance.set_surface_override_material(0, material)
	add_child(mesh_instance)
	buildings.append(mesh_instance)

# Triangulație Ear Clipping pentru poligoane 2D (concave sau convexe)
func _triangulate_polygon_2d(points_3d: Array) -> PackedInt32Array:
	var indices = PackedInt32Array()
	if points_3d.size() < 3:
		return indices
	
	# Convertim la 2D (ignorăm Z)
	var points_2d = []
	for p in points_3d:
		points_2d.append(Vector2(p.x, p.y))
	
	# Lista de indici rămași
	var remaining = []
	for i in range(points_2d.size()):
		remaining.append(i)
	
	# Ear Clipping Algorithm
	var max_iterations = points_2d.size() * 3  # Prevenire buclă infinită
	var iteration = 0
	while remaining.size() > 3 and iteration < max_iterations:
		iteration += 1
		var ear_found = false
		
		for i in range(remaining.size()):
			var prev_idx = remaining[(i - 1 + remaining.size()) % remaining.size()]
			var curr_idx = remaining[i]
			var next_idx = remaining[(i + 1) % remaining.size()]
			
			var p_prev = points_2d[prev_idx]
			var p_curr = points_2d[curr_idx]
			var p_next = points_2d[next_idx]
			
			# Verifică dacă este un vertex convex
			if not _is_convex_vertex(p_prev, p_curr, p_next):
				continue
			
			# Verifică dacă nu există alte puncte în interiorul triunghiului
			var is_ear = true
			for j in range(remaining.size()):
				if j == i or j == (i - 1 + remaining.size()) % remaining.size() or j == (i + 1) % remaining.size():
					continue
				var p_test = points_2d[remaining[j]]
				if _point_in_triangle_2d(p_test, p_prev, p_curr, p_next):
					is_ear = false
					break
			
			if is_ear:
				# Adaugă triunghiul
				indices.append(prev_idx)
				indices.append(curr_idx)
				indices.append(next_idx)
				
				# Elimină vertex-ul curent
				remaining.remove_at(i)
				ear_found = true
				break
		
		if not ear_found:
			# Fallback: dacă nu găsim o ureche, ieșim pentru a evita bucla infinită
			break
	
	# Adaugă ultimul triunghi
	if remaining.size() == 3:
		indices.append(remaining[0])
		indices.append(remaining[1])
		indices.append(remaining[2])
	
	return indices

# Verifică dacă un vertex este convex (produs încrucișat pozitiv)
func _is_convex_vertex(p_prev: Vector2, p_curr: Vector2, p_next: Vector2) -> bool:
	var cross = (p_curr.x - p_prev.x) * (p_next.y - p_curr.y) - (p_curr.y - p_prev.y) * (p_next.x - p_curr.x)
	return cross > 0

# Verifică dacă un punct este în interiorul unui triunghi 2D
func _point_in_triangle_2d(p: Vector2, a: Vector2, b: Vector2, c: Vector2) -> bool:
	var v0 = c - a
	var v1 = b - a
	var v2 = p - a
	
	var dot00 = v0.dot(v0)
	var dot01 = v0.dot(v1)
	var dot02 = v0.dot(v2)
	var dot11 = v1.dot(v1)
	var dot12 = v1.dot(v2)
	
	var inv_denom = 1.0 / (dot00 * dot11 - dot01 * dot01)
	var u = (dot11 * dot02 - dot01 * dot12) * inv_denom
	var v = (dot00 * dot12 - dot01 * dot02) * inv_denom
	
	return (u >= 0) and (v >= 0) and (u + v < 1)

func _geojson_create_linestring(coordinates: Array, properties: Dictionary, scale_factor: float, center_lat: float, center_lon: float, all_points: Array):
	# Convertește coordonatele în puncte 3D
	var points = []
	for coord in coordinates:
		var lon = coord[0]
		var lat = coord[1]
		var pos = _geojson_latlon_to_local(lat, lon, scale_factor, center_lat, center_lon)
		points.append(pos)
		all_points.append(pos)
	
	if points.size() < 2:
		return
	
	# Determină lățimea drumului
	var road_width = _get_road_width(properties)
	
	if road_width > 0:
		# Creează mesh 3D pentru drum (suprafață cu lățime)
		_create_road_mesh(points, road_width, properties)
	else:
		# Fallback: linie simplă pentru non-drumuri
		var line = MeshInstance3D.new()
		var immediate_mesh = ImmediateMesh.new()
		immediate_mesh.surface_begin(Mesh.PRIMITIVE_LINE_STRIP)
		for point in points:
			immediate_mesh.surface_add_vertex(point)
		immediate_mesh.surface_end()
		line.mesh = immediate_mesh
		var material = StandardMaterial3D.new()
		material.cull_mode = BaseMaterial3D.CULL_DISABLED
		material.albedo_color = Color(0.5, 0.5, 0.5, 1.0)
		material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		line.set_surface_override_material(0, material)
		add_child(line)

# Determină lățimea drumului din proprietăți sau estimată din tip
func _get_road_width(properties: Dictionary) -> float:
	# 1. Verifică dacă există width explicit
	if properties.has("width"):
		var width_str = str(properties.width)
		# Elimină unitatea "m" dacă există
		width_str = width_str.replace("m", "").replace(" ", "")
		return float(width_str)
	
	# 2. Calculează din număr de benzi (lanes)
	if properties.has("lanes"):
		var lanes = int(properties.lanes)
		return lanes * 3.5  # 3.5m per bandă (standard)
	
	# 3. Estimează din tipul de drum (highway type)
	if properties.has("highway"):
		var highway_type = properties.highway
		# Lățimi standard în metri bazate pe tipul de drum
		var default_widths = {
			"motorway": 12.0,
			"trunk": 10.0,
			"primary": 8.0,
			"secondary": 7.0,
			"tertiary": 6.0,
			"residential": 5.0,
			"service": 3.0,
			"unclassified": 4.0,
			"living_street": 4.0,
			"footway": 2.0,
			"path": 1.5,
			"cycleway": 2.0,
			"pedestrian": 3.0,
			"steps": 1.5
		}
		if default_widths.has(highway_type):
			return default_widths[highway_type]
		else:
			return 4.0  # Lățime default pentru tipuri necunoscute
	
	return 0.0  # Nu este drum, returnează 0

# Creează mesh 3D pentru drum cu lățime
func _create_road_mesh(points: Array, width: float, properties: Dictionary):
	if points.size() < 2:
		return
	
	var mesh_instance = MeshInstance3D.new()
	var array_mesh = ArrayMesh.new()
	var arrays = []
	arrays.resize(Mesh.ARRAY_MAX)
	var vertices = PackedVector3Array()
	var indices = PackedInt32Array()
	var normals = PackedVector3Array()
	
	var half_width = width / 2.0
	var road_elevation = 0.05  # Ridică drumul 5cm deasupra solului pentru vizibilitate
	
	# Generează vârfurile pentru fiecare segment
	for i in range(points.size()):
		var point = points[i]
		point.z += road_elevation  # Ridică drumul puțin deasupra nivelului 0
		
		# Calculează direcția perpendiculară (pentru lățimea drumului)
		var direction = Vector3.ZERO
		if i == 0:
			# Primul punct - folosește direcția către următorul
			direction = (points[i + 1] - point).normalized()
		elif i == points.size() - 1:
			# Ultimul punct - folosește direcția de la precedent
			direction = (point - points[i - 1]).normalized()
		else:
			# Punct intermediar - medie între direcțiile adiacente
			var dir_prev = (point - points[i - 1]).normalized()
			var dir_next = (points[i + 1] - point).normalized()
			direction = (dir_prev + dir_next).normalized()
		
		# Perpendicular în plan XY (Z este verticală)
		var perpendicular = Vector3(-direction.y, direction.x, 0).normalized()
		
		# Adaugă vârfurile pentru laturile drumului
		var left = point + perpendicular * half_width
		var right = point - perpendicular * half_width
		
		vertices.append(left)
		normals.append(Vector3(0, 0, 1))  # Normală în sus
		vertices.append(right)
		normals.append(Vector3(0, 0, 1))
	
	# Creează triunghiuri pentru suprafața drumului
	for i in range(points.size() - 1):
		var base = i * 2
		# Primul triunghi
		indices.append(base)
		indices.append(base + 1)
		indices.append(base + 2)
		# Al doilea triunghi
		indices.append(base + 1)
		indices.append(base + 3)
		indices.append(base + 2)
	
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_INDEX] = indices
	arrays[Mesh.ARRAY_NORMAL] = normals
	array_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	mesh_instance.mesh = array_mesh
	
	# Material pentru drum
	var material = StandardMaterial3D.new()
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	
	# Culori bazate pe tip
	if properties.has("highway"):
		var highway_type = properties.highway
		if highway_type in ["motorway", "trunk"]:
			material.albedo_color = Color(0.2, 0.2, 0.2, 1.0)  # Negru pentru drumuri majore
		elif highway_type in ["primary", "secondary", "tertiary"]:
			material.albedo_color = Color(0.3, 0.3, 0.3, 1.0)  # Gri închis
		elif highway_type == "residential":
			material.albedo_color = Color(0.4, 0.4, 0.4, 1.0)  # Gri mediu
		elif highway_type in ["footway", "path", "cycleway"]:
			material.albedo_color = Color(0.6, 0.5, 0.4, 1.0)  # Maro pentru poteci
		else:
			material.albedo_color = Color(0.45, 0.45, 0.45, 1.0)  # Gri default
	else:
		material.albedo_color = Color(0.5, 0.5, 0.5, 1.0)
	
	mesh_instance.set_surface_override_material(0, material)
	add_child(mesh_instance)

func _geojson_create_point(coordinates: Array, properties: Dictionary, scale_factor: float, center_lat: float, center_lon: float, all_points: Array):
	var marker = CSGSphere3D.new()
	marker.radius = 1.0
	var lon = coordinates[0]
	var lat = coordinates[1]
	marker.position = _geojson_latlon_to_local(lat, lon, scale_factor, center_lat, center_lon)
	all_points.append(marker.position)
	var material = StandardMaterial3D.new()
	material.cull_mode = BaseMaterial3D.CULL_DISABLED  # Fața dublă pentru markere
	material.albedo_color = Color(1.0, 0.3, 0.3, 1.0)
	marker.material = material
	add_child(marker)

func _geojson_latlon_to_local(lat: float, lon: float, scale_factor: float, center_lat: float, center_lon: float) -> Vector3:
	var x = (lon - center_lon) * scale_factor
	var y = (lat - center_lat) * scale_factor
	return Vector3(x, y, 0)

# === CITYJSON INTEGRATION ===
# Încarcă și afișează fișiere CityJSON (format 3D Tiles pentru clădiri urbane)
func load_cityjson(file_path: String, lod_preference: String = "2.2"):
	"""
	Încarcă fișiere CityJSON/JSONL cu clădiri 3D complete
	@param file_path: Calea către fișierul .jsonl sau .json
	@param lod_preference: Nivel de detaliu preferat (1.2, 1.3, 2.2, etc.)
	"""
	print("[CityJSON] Starting CityJSON load from: ", file_path)
	
	var file = FileAccess.open(file_path, FileAccess.READ)
	if not file:
		print("[CityJSON] ERROR: Cannot open file: ", file_path)
		return
	
	var transform_data = {}
	var buildings_count = 0
	var vertices_cache = []
	var line_number = 0
	var global_center = Vector3.ZERO
	var global_bounds_min = Vector3(INF, INF, INF)
	var global_bounds_max = Vector3(-INF, -INF, -INF)
	var all_buildings_data = []  # Stocăm temporar toate clădirile pentru procesare în două treceri
	
	# Citește fișierul linie cu linie (format JSONL)
	while not file.eof_reached():
		var line = file.get_line().strip_edges()
		line_number += 1
		
		if line.is_empty():
			continue
		
		var json = JSON.new()
		var parse_result = json.parse(line)
		
		if parse_result != OK:
			print("[CityJSON] ERROR parsing line ", line_number, ": ", json.get_error_message())
			continue
		
		var data = json.data
		
		# Prima linie conține metadata și transform
		if data.has("type") and data["type"] == "CityJSON":
			print("[CityJSON] Found metadata - version: ", data.get("version", "unknown"))
			if data.has("transform"):
				transform_data = data["transform"]
				print("[CityJSON] Transform found - scale: ", transform_data.get("scale"), " translate: ", transform_data.get("translate"))
			continue
		
		# Liniile următoare sunt CityJSONFeature cu clădiri
		if data.has("type") and data["type"] == "CityJSONFeature":
			var feature_id = data.get("id", "unknown")
			var city_objects = data.get("CityObjects", {})
			vertices_cache = data.get("vertices", [])
			
			# Transformă vertexurile și calculează bounds
			var transformed_vertices = _cityjson_transform_vertices(vertices_cache, transform_data)
			
			# Actualizează bounds globale
			for vertex in transformed_vertices:
				global_bounds_min.x = min(global_bounds_min.x, vertex.x)
				global_bounds_min.y = min(global_bounds_min.y, vertex.y)
				global_bounds_min.z = min(global_bounds_min.z, vertex.z)
				global_bounds_max.x = max(global_bounds_max.x, vertex.x)
				global_bounds_max.y = max(global_bounds_max.y, vertex.y)
				global_bounds_max.z = max(global_bounds_max.z, vertex.z)
			
			# Stochează datele pentru procesare ulterioară
			all_buildings_data.append({
				"city_objects": city_objects,
				"vertices": transformed_vertices
			})
	
	file.close()
	
	# Calculează centrul scenei
	global_center = (global_bounds_min + global_bounds_max) * 0.5
	print("[CityJSON] Scene bounds: min=", global_bounds_min, " max=", global_bounds_max)
	print("[CityJSON] Scene center: ", global_center, " - centering all buildings to origin")
	
	# Acum procesează toate clădirile cu offset către centru
	for building_data in all_buildings_data:
		var city_objects = building_data["city_objects"]
		var vertices = building_data["vertices"]
		
		# Centrează vertexurile la origine
		var centered_vertices = []
		for vertex in vertices:
			centered_vertices.append(vertex - global_center)
		
		# Procesează fiecare obiect din feature (clădiri, părți de clădiri, etc.)
		for obj_id in city_objects.keys():
			var city_obj = city_objects[obj_id]
			var obj_type = city_obj.get("type", "")
			
			# Doar clădiri și părți de clădiri
			if obj_type in ["Building", "BuildingPart"]:
				_cityjson_create_building_direct(city_obj, obj_id, centered_vertices, lod_preference)
				buildings_count += 1
				
				# Așteaptă periodic pentru a nu bloca UI-ul
				if buildings_count % 50 == 0:
					print("[CityJSON] Processed ", buildings_count, " buildings...")
					await get_tree().process_frame
	
	print("[CityJSON] ✓ Loaded ", buildings_count, " buildings from CityJSON")
	
	# Încadrează camera la toate clădirile
	_fit_camera_to_scene()

func _cityjson_create_building_direct(city_obj: Dictionary, obj_id: String, centered_vertices: Array, lod_preference: String):
	"""
	Creează meshuri 3D pentru o clădire din CityJSON (cu vertexuri deja transformate și centrate)
	"""
	var geometries = city_obj.get("geometry", [])
	
	if geometries.is_empty():
		return
	
	# Lista de prioritate pentru LoD (încearcă mai multe variante)
	var lod_priority = [lod_preference, "2.2", "1.3", "1.2", "1.0", "0"]
	
	# Caută geometria cu cel mai bun LoD disponibil
	var selected_geom = null
	var selected_lod = ""
	
	for preferred_lod in lod_priority:
		for geom in geometries:
			if str(geom.get("lod", "")) == str(preferred_lod):
				selected_geom = geom
				selected_lod = str(preferred_lod)
				break
		if selected_geom:
			break
	
	# Dacă nimic nu s-a găsit, ia prima geometrie disponibilă
	if not selected_geom and geometries.size() > 0:
		selected_geom = geometries[0]
		selected_lod = str(selected_geom.get("lod", "unknown"))
		print("[CityJSON] Warning: No standard LoD found for ", obj_id, ", using LoD ", selected_lod)
	
	if not selected_geom:
		return
	
	# Afișează doar dacă nu e LoD-ul preferat
	if selected_lod != lod_preference and selected_lod != "0":
		print("[CityJSON] Info: Using LoD ", selected_lod, " for ", obj_id, " (preferred ", lod_preference, " not available)")
	
	var geom_type = selected_geom.get("type", "")
	var boundaries = selected_geom.get("boundaries", [])
	
	# Procesează geometria în funcție de tip (vertexurile sunt deja centrate)
	match geom_type:
		"Solid":
			_cityjson_create_solid(boundaries, centered_vertices, obj_id, city_obj)
		"MultiSurface":
			_cityjson_create_multisurface(boundaries, centered_vertices, obj_id, city_obj)
		"CompositeSolid":
			# CompositeSolid = array de Solid-uri
			for solid_boundaries in boundaries:
				_cityjson_create_solid(solid_boundaries, centered_vertices, obj_id, city_obj)
		_:
			print("[CityJSON] Unsupported geometry type: ", geom_type)

func _cityjson_transform_vertices(vertices: Array, transform: Dictionary) -> Array:
	"""
	Aplică transformarea CityJSON (scale + translate) pe vertexuri
	"""
	var scale = transform.get("scale", [0.001, 0.001, 0.001])
	var translate = transform.get("translate", [0.0, 0.0, 0.0])
	
	var result = []
	
	for vertex in vertices:
		if vertex.size() != 3:
			continue
		
		# Aplică scale și translate conform spec CityJSON
		var x = vertex[0] * scale[0] + translate[0]
		var y = vertex[1] * scale[1] + translate[1]
		var z = vertex[2] * scale[2] + translate[2]
		
		# Sistemul nostru: X=est-vest, Y=nord-sud, Z=verticală
		# CityJSON folosește coordonate geografice locale
		result.append(Vector3(x, y, z))
	
	return result

func _cityjson_create_solid(boundaries: Array, vertices: Array, obj_id: String, city_obj: Dictionary):
	"""
	Creează mesh pentru geometrie Solid (volum 3D închis)
	Un Solid conține un array de shell-uri (exterior + eventuale hole-uri interioare)
	Fiecare shell e un array de suprafețe (poligoane)
	"""
	if boundaries.is_empty():
		return
	
	# Primul element e shell-ul exterior, restul sunt hole-uri (de obicei nu există)
	var exterior_shell = boundaries[0]
	
	var surface_tool = SurfaceTool.new()
	surface_tool.begin(Mesh.PRIMITIVE_TRIANGLES)
	
	# Procesează fiecare suprafață (perete, acoperiș, podea, etc.)
	for surface in exterior_shell:
		# O suprafață e un array de ring-uri (primul = exterior, restul = hole-uri)
		if surface.is_empty():
			continue
		
		var exterior_ring = surface[0]
		
		# Exterior ring = lista de indecși în array-ul de vertexuri
		if exterior_ring.size() < 3:
			continue
		
		# Triangulează poligonul (convertește indices în vertexuri 3D)
		var poly_vertices = []
		for idx in exterior_ring:
			if idx < vertices.size():
				poly_vertices.append(vertices[idx])
		
		# Adaugă triunghiuri cu Ear Clipping
		var indices = _triangulate_polygon_3d(poly_vertices)
		
		for i in range(0, indices.size(), 3):
			if i + 2 < indices.size():
				var v0 = poly_vertices[indices[i]]
				var v1 = poly_vertices[indices[i + 1]]
				var v2 = poly_vertices[indices[i + 2]]
				
				# Calculează normala
				var normal = (v1 - v0).cross(v2 - v0).normalized()
				
				surface_tool.set_normal(normal)
				surface_tool.add_vertex(v0)
				surface_tool.set_normal(normal)
				surface_tool.add_vertex(v1)
				surface_tool.set_normal(normal)
				surface_tool.add_vertex(v2)
	
	var mesh = surface_tool.commit()
	
	# Creează MeshInstance3D
	var mesh_instance = MeshInstance3D.new()
	mesh_instance.mesh = mesh
	mesh_instance.name = obj_id
	
	# Material cu culoare bazată pe proprietăți
	var mat = StandardMaterial3D.new()
	mat.albedo_color = _cityjson_get_building_color(city_obj)
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED  # Double-sided
	mesh_instance.material_override = mat
	
	add_child(mesh_instance)
	print("[CityJSON] Created Solid mesh: ", obj_id, " with ", mesh.get_surface_count(), " surfaces")

func _cityjson_create_multisurface(boundaries: Array, vertices: Array, obj_id: String, city_obj: Dictionary):
	"""
	Creează mesh pentru geometrie MultiSurface (colecție de suprafețe 2D, folosit pentru LoD 0)
	Pentru LoD 0 (footprint), extrudăm în sus pentru a crea un volum simplu
	"""
	# Încearcă să obții înălțimea din atribute
	var attributes = city_obj.get("attributes", {})
	var height = attributes.get("b3_h_dak_max", attributes.get("measuredHeight", 10.0))
	
	# Dacă înălțimea e prea mică sau invalida, folosește 10m ca default
	if height < 1.0:
		height = 10.0
	
	var surface_tool = SurfaceTool.new()
	surface_tool.begin(Mesh.PRIMITIVE_TRIANGLES)
	
	# Procesează fiecare suprafață (de obicei e doar footprint-ul)
	for surface in boundaries:
		if surface.is_empty():
			continue
		
		var exterior_ring = surface[0]
		
		if exterior_ring.size() < 3:
			continue
		
		var poly_vertices_base = []
		for idx in exterior_ring:
			if idx < vertices.size():
				poly_vertices_base.append(vertices[idx])
		
		# Creează și vertexurile de sus (extrudate pe Z)
		var poly_vertices_top = []
		for v in poly_vertices_base:
			poly_vertices_top.append(v + Vector3(0, 0, height))
		
		# Triangulează baza (jos)
		var indices = _triangulate_polygon_3d(poly_vertices_base)
		for i in range(0, indices.size(), 3):
			if i + 2 < indices.size():
				var v0 = poly_vertices_base[indices[i]]
				var v1 = poly_vertices_base[indices[i + 1]]
				var v2 = poly_vertices_base[indices[i + 2]]
				
				var normal = Vector3(0, 0, -1)  # Normal în jos pentru bază
				
				surface_tool.set_normal(normal)
				surface_tool.add_vertex(v2)
				surface_tool.set_normal(normal)
				surface_tool.add_vertex(v1)
				surface_tool.set_normal(normal)
				surface_tool.add_vertex(v0)
		
		# Triangulează acoperișul (sus)
		for i in range(0, indices.size(), 3):
			if i + 2 < indices.size():
				var v0 = poly_vertices_top[indices[i]]
				var v1 = poly_vertices_top[indices[i + 1]]
				var v2 = poly_vertices_top[indices[i + 2]]
				
				var normal = Vector3(0, 0, 1)  # Normal în sus pentru acoperiș
				
				surface_tool.set_normal(normal)
				surface_tool.add_vertex(v0)
				surface_tool.set_normal(normal)
				surface_tool.add_vertex(v1)
				surface_tool.set_normal(normal)
				surface_tool.add_vertex(v2)
		
		# Creează pereții laterali
		for i in range(poly_vertices_base.size()):
			var next_i = (i + 1) % poly_vertices_base.size()
			
			var v0_base = poly_vertices_base[i]
			var v1_base = poly_vertices_base[next_i]
			var v0_top = poly_vertices_top[i]
			var v1_top = poly_vertices_top[next_i]
			
			# Calculează normala pentru perete
			var edge = v1_base - v0_base
			var up = Vector3(0, 0, 1)
			var normal = edge.cross(up).normalized()
			
			# Triunghi 1
			surface_tool.set_normal(normal)
			surface_tool.add_vertex(v0_base)
			surface_tool.set_normal(normal)
			surface_tool.add_vertex(v1_base)
			surface_tool.set_normal(normal)
			surface_tool.add_vertex(v1_top)
			
			# Triunghi 2
			surface_tool.set_normal(normal)
			surface_tool.add_vertex(v0_base)
			surface_tool.set_normal(normal)
			surface_tool.add_vertex(v1_top)
			surface_tool.set_normal(normal)
			surface_tool.add_vertex(v0_top)
	
	var mesh = surface_tool.commit()
	
	var mesh_instance = MeshInstance3D.new()
	mesh_instance.mesh = mesh
	mesh_instance.name = obj_id
	
	var mat = StandardMaterial3D.new()
	mat.albedo_color = _cityjson_get_building_color(city_obj)
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	mesh_instance.material_override = mat
	
	add_child(mesh_instance)
	print("[CityJSON] Created MultiSurface (extruded LoD 0) mesh: ", obj_id, " with height ", height, "m")

func _triangulate_polygon_3d(points: Array) -> PackedInt32Array:
	"""
	Triangulează un poligon 3D arbitrar prin proiectare pe cel mai bun plan
	"""
	if points.size() < 3:
		return PackedInt32Array()
	
	# Calculează normala poligonului pentru a determina planul de proiectare
	var normal = Vector3.ZERO
	for i in range(points.size()):
		var v0 = points[i]
		var v1 = points[(i + 1) % points.size()]
		normal += v0.cross(v1)
	normal = normal.normalized()
	
	# Determină care axă să eliminăm pentru proiectare 2D
	# Eliminăm axa cu cea mai mare componentă în normală
	var abs_normal = Vector3(abs(normal.x), abs(normal.y), abs(normal.z))
	var project_axis = 2  # Default: proiectăm pe XY (eliminăm Z)
	
	if abs_normal.x > abs_normal.y and abs_normal.x > abs_normal.z:
		project_axis = 0  # Proiectăm pe YZ (eliminăm X)
	elif abs_normal.y > abs_normal.x and abs_normal.y > abs_normal.z:
		project_axis = 1  # Proiectăm pe XZ (eliminăm Y)
	
	# Proiectează pe 2D
	var points_2d = []
	for p in points:
		match project_axis:
			0: points_2d.append(Vector2(p.y, p.z))
			1: points_2d.append(Vector2(p.x, p.z))
			_: points_2d.append(Vector2(p.x, p.y))
	
	# Folosește algoritmul existent de triangulație 2D
	return _triangulate_polygon_2d_from_3d(points_2d)

func _triangulate_polygon_2d_from_3d(points_2d: Array) -> PackedInt32Array:
	"""
	Ear Clipping pentru poligoane 2D proiectate din 3D
	"""
	if points_2d.size() < 3:
		return PackedInt32Array()
	
	var indices = PackedInt32Array()
	var remaining = []
	for i in range(points_2d.size()):
		remaining.append(i)
	
	var iterations = 0
	var max_iterations = points_2d.size() * 3
	
	while remaining.size() > 3 and iterations < max_iterations:
		iterations += 1
		var found_ear = false
		
		for i in range(remaining.size()):
			var i_prev = (i - 1 + remaining.size()) % remaining.size()
			var i_next = (i + 1) % remaining.size()
			
			var idx_prev = remaining[i_prev]
			var idx_curr = remaining[i]
			var idx_next = remaining[i_next]
			
			var p_prev = points_2d[idx_prev]
			var p_curr = points_2d[idx_curr]
			var p_next = points_2d[idx_next]
			
			if not _is_convex_vertex(p_prev, p_curr, p_next):
				continue
			
			var is_ear = true
			for j in range(remaining.size()):
				if j == i_prev or j == i or j == i_next:
					continue
				
				var p_test = points_2d[remaining[j]]
				if _point_in_triangle_2d(p_test, p_prev, p_curr, p_next):
					is_ear = false
					break
			
			if is_ear:
				indices.append(idx_prev)
				indices.append(idx_curr)
				indices.append(idx_next)
				remaining.remove_at(i)
				found_ear = true
				break
		
		if not found_ear:
			break
	
	if remaining.size() == 3:
		indices.append(remaining[0])
		indices.append(remaining[1])
		indices.append(remaining[2])
	
	return indices

func _cityjson_get_building_color(city_obj: Dictionary) -> Color:
	"""
	Determină culoarea clădirii bazată pe atribute
	"""
	var attributes = city_obj.get("attributes", {})
	
	# Culoare bazată pe tipul de clădire sau înălțime
	var obj_type = city_obj.get("type", "")
	
	if obj_type == "BuildingPart":
		return Color(0.8, 0.7, 0.6)  # Bej pentru părți de clădiri
	
	# Culoare bazată pe înălțime
	var height = attributes.get("b3_h_dak_max", 10.0)
	
	if height > 20.0:
		return Color(0.3, 0.3, 0.5)  # Albastru închis pentru clădiri înalte
	elif height > 10.0:
		return Color(0.6, 0.6, 0.7)  # Gri pentru clădiri medii
	else:
		return Color(0.85, 0.8, 0.75)  # Bej deschis pentru clădiri mici
	
func _fit_camera_to_scene():
	"""
	Încadrează camera pentru a vedea toate clădirile din scenă
	"""
	var bbox = _calculate_scene_bounding_box()
	if bbox.has_volume():
		_fit_camera_to_bbox(bbox)
		print("[CityJSON] Camera fitted to scene bounds: ", bbox)

# === CESIUM 3D TILES INTEGRATION ===
# Încarcă și afișează Cesium 3D Tiles (format standard pentru date geospațiale 3D masive)
func load_3d_tiles(tileset_path: String, max_depth: int = 3):
	"""
	Încarcă un tileset Cesium 3D Tiles și creează geometrie în scenă
	@param tileset_path: Calea către fișierul tileset.json principal
	@param max_depth: Adâncimea maximă de traversare a ierarhiei (pentru performanță)
	"""
	print("[3D Tiles] Starting Cesium 3D Tiles load from: ", tileset_path)
	
	var file = FileAccess.open(tileset_path, FileAccess.READ)
	if not file:
		print("[3D Tiles] ERROR: Cannot open tileset file: ", tileset_path)
		return
	
	var json_str = file.get_as_text()
	file.close()
	
	var json = JSON.new()
	var parse_result = json.parse(json_str)
	
	if parse_result != OK:
		print("[3D Tiles] ERROR parsing tileset JSON: ", json.get_error_message())
		return
	
	var tileset_data = json.data
	
	# Verifică versiunea și asset
	var asset = tileset_data.get("asset", {})
	var version = asset.get("version", "unknown")
	print("[3D Tiles] Tileset version: ", version)
	
	# Obține transformarea geometrică globală (dacă există)
	var geometric_error = tileset_data.get("geometricError", 0.0)
	print("[3D Tiles] Root geometric error: ", geometric_error)
	
	# Procesează root tile-ul
	var root_tile = tileset_data.get("root", {})
	var base_path = tileset_path.get_base_dir()
	
	var tiles_loaded = 0
	var global_bounds_min = Vector3(INF, INF, INF)
	var global_bounds_max = Vector3(-INF, -INF, -INF)
	var all_tiles_data = []
	
	# Colectează toate tile-urile recursiv
	_collect_3dtiles_recursive(root_tile, base_path, 0, max_depth, all_tiles_data)
	
	print("[3D Tiles] Collected ", all_tiles_data.size(), " tiles, loading content...")
	
	# Încarcă conținutul fiecărui tile
	for tile_data in all_tiles_data:
		var content_uri = tile_data["content_uri"]
		var transform_matrix = tile_data["transform"]
		
		# Încarcă fișierul de conținut (.b3dm, .glb, .gltf, etc.)
		var content_loaded = await _load_3dtile_content(content_uri, transform_matrix, global_bounds_min, global_bounds_max)
		
		if content_loaded:
			tiles_loaded += 1
		
		# Așteaptă periodic pentru UI
		if tiles_loaded % 10 == 0:
			print("[3D Tiles] Loaded ", tiles_loaded, " tiles...")
			await get_tree().process_frame
	
	print("[3D Tiles] ✓ Loaded ", tiles_loaded, " tiles from Cesium 3D Tiles")
	
	# Centrează scena la origine doar dacă am încărcat cel puțin un tile
	if tiles_loaded > 0 and global_bounds_min.x != INF:
		var global_center = (global_bounds_min + global_bounds_max) * 0.5
		print("[3D Tiles] Scene bounds: min=", global_bounds_min, " max=", global_bounds_max)
		print("[3D Tiles] Centering to origin from: ", global_center)
		
		# Offset toate obiectele încărcate
		for child in get_children():
			if child is MeshInstance3D and child.has_meta("3dtiles"):
				child.position -= global_center
		
		# Încadrează camera doar dacă am încărcat tile-uri cu succes
		_fit_camera_to_scene()
	elif tiles_loaded == 0:
		print("[3D Tiles] WARNING: No tiles were loaded successfully, skipping camera fit")

func _collect_3dtiles_recursive(tile: Dictionary, base_path: String, depth: int, max_depth: int, collected: Array):
	"""
	Colectează recursiv toate tile-urile din ierarhie
	"""
	if depth > max_depth:
		return
	
	# Obține conținutul tile-ului
	var content = tile.get("content", {})
	var content_uri = content.get("uri", content.get("url", ""))
	
	if not content_uri.is_empty():
		# Construiește calea completă
		var full_path = base_path + "/" + content_uri
		
		# Obține transformarea tile-ului (matrice 4x4 sau boundingVolume)
		var transform = tile.get("transform", null)
		
		collected.append({
			"content_uri": full_path,
			"transform": transform,
			"depth": depth
		})
	
	# Procesează copiii recursiv
	var children = tile.get("children", [])
	for child_tile in children:
		_collect_3dtiles_recursive(child_tile, base_path, depth + 1, max_depth, collected)

func _load_3dtile_content(content_uri: String, transform_matrix, bounds_min: Vector3, bounds_max: Vector3) -> bool:
	"""
	Încarcă conținutul unui tile (b3dm, glb, gltf, pnts, i3dm, cmpt)
	"""
	var extension = content_uri.get_extension().to_lower()
	
	match extension:
		"b3dm":
			return _load_b3dm_tile(content_uri, transform_matrix, bounds_min, bounds_max)
		"glb", "gltf":
			return _load_gltf_tile(content_uri, transform_matrix, bounds_min, bounds_max)
		"i3dm":
			return await _load_i3dm_tile(content_uri, transform_matrix, bounds_min, bounds_max)
		"pnts":
			print("[3D Tiles] Point cloud tiles (PNTS) not yet supported: ", content_uri)
			return false
		"cmpt":
			print("[3D Tiles] Composite tiles (CMPT) not yet supported: ", content_uri)
			return false
		_:
			print("[3D Tiles] Unknown tile format: ", extension)
			return false

func _load_b3dm_tile(file_path: String, transform_matrix, bounds_min: Vector3, bounds_max: Vector3) -> bool:
	"""
	Încarcă un tile Batched 3D Model (.b3dm)
	Format: Header (28 bytes) + Feature Table (JSON + Binary) + Batch Table + GLB
	"""
	var file = FileAccess.open(file_path, FileAccess.READ)
	if not file:
		print("[3D Tiles] ERROR: Cannot open B3DM file: ", file_path)
		return false
	
	# Citește header-ul B3DM (28 bytes)
	var magic = file.get_buffer(4).get_string_from_ascii()
	if magic != "b3dm":
		print("[3D Tiles] ERROR: Invalid B3DM magic header: ", magic)
		file.close()
		return false
	
	var version = file.get_32()
	var byte_length = file.get_32()
	var feature_table_json_byte_length = file.get_32()
	var feature_table_binary_byte_length = file.get_32()
	var batch_table_json_byte_length = file.get_32()
	var batch_table_binary_byte_length = file.get_32()
	
	print("[3D Tiles] B3DM Header - version: ", version, " total bytes: ", byte_length)
	
	# Skip feature table și batch table (nu le folosim pentru moment)
	file.seek(file.get_position() + feature_table_json_byte_length + feature_table_binary_byte_length)
	file.seek(file.get_position() + batch_table_json_byte_length + batch_table_binary_byte_length)
	
	# Restul e GLB - extrage-l într-un fișier temporar
	var glb_data = file.get_buffer(file.get_length() - file.get_position())
	file.close()
	
	# Salvează temporar GLB-ul
	var temp_glb_path = "user://temp_b3dm_" + str(file_path.get_file().get_basename()) + ".glb"
	var temp_file = FileAccess.open(temp_glb_path, FileAccess.WRITE)
	if temp_file:
		temp_file.store_buffer(glb_data)
		temp_file.close()
		
		# Încarcă GLB-ul cu funcția existentă
		var success = _load_gltf_tile(temp_glb_path, transform_matrix, bounds_min, bounds_max)
		
		# Șterge fișierul temporar
		DirAccess.remove_absolute(temp_glb_path)
		
		return success
	
	return false

func _load_i3dm_tile(file_path: String, transform_matrix, bounds_min: Vector3, bounds_max: Vector3) -> bool:
	"""
	Încarcă un tile Instanced 3D Model (.i3dm)
	Format: Header (32 bytes) + Feature Table (JSON + Binary) + Batch Table + GLB/GLTF (extern sau încapsulat)
	I3DM permite instanțierea aceluiași model 3D în mai multe locații (ex: copaci, stâlpi, etc.)
	"""
	var file = FileAccess.open(file_path, FileAccess.READ)
	if not file:
		print("[3D Tiles] ERROR: Cannot open I3DM file: ", file_path)
		return false
	
	# Citește header-ul I3DM (32 bytes)
	var magic = file.get_buffer(4).get_string_from_ascii()
	if magic != "i3dm":
		print("[3D Tiles] ERROR: Invalid I3DM magic header: ", magic)
		file.close()
		return false
	
	var version = file.get_32()
	var byte_length = file.get_32()
	var feature_table_json_byte_length = file.get_32()
	var feature_table_binary_byte_length = file.get_32()
	var batch_table_json_byte_length = file.get_32()
	var batch_table_binary_byte_length = file.get_32()
	var gltf_format = file.get_32()  # 0 = URI extern, 1 = GLB încapsulat
	
	print("[3D Tiles] I3DM Header - version: ", version, " gltf_format: ", gltf_format)
	
	# Citește Feature Table JSON pentru a obține pozițiile instanțelor
	var feature_table_json_str = file.get_buffer(feature_table_json_byte_length).get_string_from_utf8()
	var json = JSON.new()
	var parse_result = json.parse(feature_table_json_str)
	
	if parse_result != OK:
		print("[3D Tiles] ERROR parsing I3DM feature table: ", json.get_error_message())
		file.close()
		return false
	
	var feature_table = json.data
	var instances_length = feature_table.get("INSTANCES_LENGTH", 0)
	
	if instances_length == 0:
		print("[3D Tiles] WARNING: No instances in I3DM tile")
		file.close()
		return false
	
	print("[3D Tiles] I3DM contains ", instances_length, " instances")
	
	# Obține pozițiile instanțelor din feature table binary
	var position_offset = feature_table.get("POSITION", {}).get("byteOffset", 0)
	
	# Skip la binary data
	file.seek(32 + feature_table_json_byte_length + position_offset)
	
	var instance_positions = []
	for i in range(instances_length):
		var x = file.get_float()
		var y = file.get_float()
		var z = file.get_float()
		instance_positions.append(Vector3(x, y, z))
	
	# Skip batch table
	file.seek(32 + feature_table_json_byte_length + feature_table_binary_byte_length)
	file.seek(file.get_position() + batch_table_json_byte_length + batch_table_binary_byte_length)
	
	# Încarcă modelul GLB (încapsulat sau extern)
	var gltf_document = GLTFDocument.new()
	var gltf_state = GLTFState.new()
	var error = OK
	
	if gltf_format == 1:
		# GLB încapsulat - extrage-l
		var glb_data = file.get_buffer(file.get_length() - file.get_position())
		file.close()
		
		# Verifică dacă avem date valide GLB (header magic: "glTF")
		if glb_data.size() < 12:
			print("[3D Tiles] ERROR: GLB data too small: ", glb_data.size(), " bytes")
			return false
		
		var glb_magic = glb_data.slice(0, 4).get_string_from_ascii()
		if glb_magic != "glTF":
			print("[3D Tiles] ERROR: Invalid GLB magic in I3DM: ", glb_magic, " (expected 'glTF')")
			return false
		
		print("[3D Tiles] Extracted GLB size: ", glb_data.size(), " bytes")
		
		# Debug: verifică primii 20 bytes din GLB
		var debug_bytes = glb_data.slice(0, min(20, glb_data.size()))
		var debug_str = ""
		for i in range(min(20, glb_data.size())):
			debug_str += "%02x " % debug_bytes[i]
		print("[3D Tiles] GLB first bytes: ", debug_str)
		
		# Salvează GLB temporar în același director cu I3DM (nu user://)
		# Acest lucru asigură că path-urile relative din GLB funcționează
		var base_path = file_path.get_base_dir()
		var temp_glb_name = "_temp_" + file_path.get_file().get_basename() + ".glb"
		var temp_glb_path = base_path + "/" + temp_glb_name
		
		var temp_file = FileAccess.open(temp_glb_path, FileAccess.WRITE)
		if not temp_file:
			print("[3D Tiles] ERROR: Cannot create temp GLB at: ", temp_glb_path)
			return false
		
		temp_file.store_buffer(glb_data)
		temp_file.close()
		
		print("[3D Tiles] Saved temp GLB to: ", temp_glb_path)
		
		# Încarcă din fișierul temporar
		error = gltf_document.append_from_file(temp_glb_path, gltf_state)
		
		# Șterge imediat fișierul temporar
		DirAccess.remove_absolute(temp_glb_path)
		
		if error != OK:
			print("[3D Tiles] append_from_file failed with code ", error, " for temp GLB: ", temp_glb_name)
			print("[3D Tiles] NOTE: This GLB may use unsupported GLTF extensions (e.g., KHR_techniques_webgl)")
			print("[3D Tiles] Skipping this tile and continuing with others...")
	else:
		# URI extern - citește URI din feature table
		var gltf_uri = feature_table.get("glTF", "")
		if gltf_uri.is_empty():
			print("[3D Tiles] ERROR: No glTF URI in I3DM")
			file.close()
			return false
		
		var gltf_path = file_path.get_base_dir() + "/" + gltf_uri
		file.close()
		
		# Încarcă din fișier extern
		error = gltf_document.append_from_file(gltf_path, gltf_state)
	
	if error != OK:
		print("[3D Tiles] ERROR loading I3DM GLTF, error code: ", error)
		return false
	
	var base_scene = gltf_document.generate_scene(gltf_state)
	
	if not base_scene:
		print("[3D Tiles] ERROR: Failed to generate scene from I3DM GLTF")
		return false
	
	# Debug: afișează informații despre modelul de bază
	print("[3D Tiles] Base model loaded, type: ", base_scene.get_class())
	if base_scene is Node3D:
		print("[3D Tiles] Base model has ", base_scene.get_child_count(), " children")
		# Caută mesh-uri în copii
		for child in base_scene.get_children():
			if child is MeshInstance3D:
				var aabb = child.get_aabb()
				print("[3D Tiles] Found MeshInstance3D with AABB: ", aabb)
				print("[3D Tiles] Mesh size: ", aabb.size)
	
	# Creează instanțe pentru fiecare poziție
	var instance_count = 0
	var first_pos_logged = false
	
	# Calculează centrul pozițiilor pentru a normaliza coordonatele ECEF
	var positions_center = Vector3.ZERO
	for pos in instance_positions:
		positions_center += pos
	positions_center /= instance_positions.size()
	
	print("[3D Tiles] Positions center (ECEF): ", positions_center)
	print("[3D Tiles] Will offset all instances by this center to bring them near origin")
	
	for pos in instance_positions:
		var instance = base_scene.duplicate()
		
		# Offsetează poziția relativă la centru pentru a aduce geometria la origine
		var centered_pos = pos - positions_center
		
		# Convertește de la GLTF (Y în sus) la sistemul aplicației (Z în sus)
		# GLTF: X=right, Y=up, Z=back
		# App:  X=right, Y=back, Z=up
		# Conversie: swap Y și Z
		instance.position = Vector3(centered_pos.x, centered_pos.z, centered_pos.y)
		
		# Debug: afișează primele 3 poziții
		if instance_count < 3:
			print("[3D Tiles] Instance ", instance_count, " original position (ECEF): ", pos)
			print("[3D Tiles] Instance ", instance_count, " centered position (GLTF Y-up): ", centered_pos)
			print("[3D Tiles] Instance ", instance_count, " final position (App Z-up): ", instance.position)
		
		# Aplică transformarea tile-ului dacă există
		if transform_matrix and typeof(transform_matrix) == TYPE_ARRAY and transform_matrix.size() == 16:
			var mat = _array_to_transform3d(transform_matrix)
			instance.transform = mat * instance.transform
		
		# Marchează cu metadata
		instance.set_meta("3dtiles", true)
		instance.set_meta("i3dm_instance", true)
		instance.set_meta("source", file_path)
		
		# Actualizează bounds - trebuie să traversăm ierarhia
		var instance_bounds = _get_node_bounds(instance)
		if instance_bounds.has_volume():
			var pos_min = instance_bounds.position
			var pos_max = instance_bounds.position + instance_bounds.size
			
			bounds_min.x = min(bounds_min.x, pos_min.x)
			bounds_min.y = min(bounds_min.y, pos_min.y)
			bounds_min.z = min(bounds_min.z, pos_min.z)
			
			bounds_max.x = max(bounds_max.x, pos_max.x)
			bounds_max.y = max(bounds_max.y, pos_max.y)
			bounds_max.z = max(bounds_max.z, pos_max.z)
		
		add_child(instance)
		instance_count += 1
		
		# Așteaptă periodic pentru UI
		if instance_count % 50 == 0:
			await get_tree().process_frame
	
	base_scene.queue_free()
	
	print("[3D Tiles] Loaded I3DM tile with ", instance_count, " instances: ", file_path.get_file())
	print("[3D Tiles] Instance bounds updated: min=", bounds_min, " max=", bounds_max)
	return true

func _load_gltf_tile(file_path: String, transform_matrix, bounds_min: Vector3, bounds_max: Vector3) -> bool:
	"""
	Încarcă un tile GLB/GLTF folosind GLTFDocument
	"""
	var gltf_document = GLTFDocument.new()
	var gltf_state = GLTFState.new()
	
	var error = gltf_document.append_from_file(file_path, gltf_state)
	
	if error != OK:
		print("[3D Tiles] ERROR loading GLTF: ", file_path, " error code: ", error)
		return false
	
	var scene = gltf_document.generate_scene(gltf_state)
	
	if not scene:
		print("[3D Tiles] ERROR: Failed to generate scene from GLTF")
		return false
	
	# Aplică transformarea dacă există
	if transform_matrix and typeof(transform_matrix) == TYPE_ARRAY and transform_matrix.size() == 16:
		var mat = _array_to_transform3d(transform_matrix)
		scene.transform = mat
	
	# Marchează cu metadata
	scene.set_meta("3dtiles", true)
	scene.set_meta("source", file_path)
	
	# Actualizează bounds
	_update_bounds_from_node(scene, bounds_min, bounds_max)
	
	add_child(scene)
	print("[3D Tiles] Loaded GLTF tile: ", file_path.get_file())
	
	return true

func _array_to_transform3d(matrix_array: Array) -> Transform3D:
	"""
	Convertește un array de 16 elemente (matrice 4x4 column-major) în Transform3D
	"""
	# Cesium folosește column-major order
	var transform = Transform3D()
	
	transform.basis.x = Vector3(matrix_array[0], matrix_array[1], matrix_array[2])
	transform.basis.y = Vector3(matrix_array[4], matrix_array[5], matrix_array[6])
	transform.basis.z = Vector3(matrix_array[8], matrix_array[9], matrix_array[10])
	transform.origin = Vector3(matrix_array[12], matrix_array[13], matrix_array[14])
	
	return transform

func _get_node_bounds(node: Node3D) -> AABB:
	"""
	Calculează AABB-ul complet al unui nod, inclusiv copiii săi
	"""
	var combined_aabb = AABB()
	var has_aabb = false
	
	# Verifică dacă acest nod are AABB
	if node is MeshInstance3D:
		var local_aabb = node.get_aabb()
		combined_aabb = node.global_transform * local_aabb
		has_aabb = true
	elif node is VisualInstance3D and node.has_method("get_aabb"):
		var local_aabb = node.get_aabb()
		combined_aabb = node.global_transform * local_aabb
		has_aabb = true
	
	# Merge cu AABB-urile copiilor
	for child in node.get_children():
		if child is Node3D:
			var child_aabb = _get_node_bounds(child)
			if child_aabb.has_volume():
				if has_aabb:
					combined_aabb = combined_aabb.merge(child_aabb)
				else:
					combined_aabb = child_aabb
					has_aabb = true
	
	return combined_aabb

func _update_bounds_from_node(node: Node3D, bounds_min: Vector3, bounds_max: Vector3):
	"""
	Actualizează bounds globale din geometria unui nod
	"""
	if node is MeshInstance3D:
		var aabb = node.get_aabb()
		var global_aabb = node.global_transform * aabb
		
		bounds_min.x = min(bounds_min.x, global_aabb.position.x)
		bounds_min.y = min(bounds_min.y, global_aabb.position.y)
		bounds_min.z = min(bounds_min.z, global_aabb.position.z)
		
		var end = global_aabb.position + global_aabb.size
		bounds_max.x = max(bounds_max.x, end.x)
		bounds_max.y = max(bounds_max.y, end.y)
		bounds_max.z = max(bounds_max.z, end.z)
	
	for child in node.get_children():
		if child is Node3D:
			_update_bounds_from_node(child, bounds_min, bounds_max)
