extends Node3D

# Setări
@export_file("*.geojson") var geojson_file_path: String = "res://planet_28.05672,46.66998_28.08867,46.68417.osm.geojson"
@export var scale_factor: float = 100000.0  # Scalare coordonate pentru OSM
@export var extrusion_height: float = 3.0  # Înălțime clădiri
@export var center_lat: float = 46.6720031  # Centru Huși
@export var center_lon: float = 28.0620905

# Setări cameră
@export_group("Camera Settings")
@export var camera_distance: float = 150.0
@export var camera_angle: float = 45.0
@export var zoom_speed: float = 10.0
@export var pan_speed: float = 1.0
@export var rotate_speed: float = 2.0
@export var min_distance: float = 20.0
@export var max_distance: float = 1000.0

var buildings: Array = []
var camera: Camera3D
var camera_pivot: Node3D
var camera_target: Vector3 = Vector3.ZERO
var is_rotating: bool = false
var last_mouse_pos: Vector2

func _ready():
	setup_camera()
	load_geojson()

func setup_camera():
	camera_pivot = Node3D.new()
	camera_pivot.position = camera_target
	add_child(camera_pivot)
	
	camera = Camera3D.new()
	camera_pivot.add_child(camera)
	
	update_camera_position()

func update_camera_position():
	var angle_rad = deg_to_rad(camera_angle)
	camera.position = Vector3(0, camera_distance * sin(angle_rad), camera_distance * cos(angle_rad))
	camera.look_at(camera_pivot.global_position, Vector3.UP)

func _input(event):
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP:
			camera_distance = max(min_distance, camera_distance - zoom_speed)
			update_camera_position()
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			camera_distance = min(max_distance, camera_distance + zoom_speed)
			update_camera_position()
		elif event.button_index == MOUSE_BUTTON_RIGHT:
			is_rotating = event.pressed
			if event.pressed:
				last_mouse_pos = event.position
	
	if event is InputEventMouseMotion and is_rotating:
		var delta = event.position - last_mouse_pos
		camera_pivot.rotate_y(-delta.x * 0.01 * rotate_speed)
		camera_angle = clamp(camera_angle - delta.y * rotate_speed, 10, 89)
		update_camera_position()
		last_mouse_pos = event.position

func _process(delta):
	var move_dir = Vector3.ZERO
	
	if Input.is_key_pressed(KEY_W) or Input.is_key_pressed(KEY_UP):
		move_dir -= camera_pivot.global_transform.basis.z
	if Input.is_key_pressed(KEY_S) or Input.is_key_pressed(KEY_DOWN):
		move_dir += camera_pivot.global_transform.basis.z
	if Input.is_key_pressed(KEY_A) or Input.is_key_pressed(KEY_LEFT):
		move_dir -= camera_pivot.global_transform.basis.x
	if Input.is_key_pressed(KEY_D) or Input.is_key_pressed(KEY_RIGHT):
		move_dir += camera_pivot.global_transform.basis.x
	
	if move_dir.length() > 0:
		move_dir = move_dir.normalized()
		move_dir.y = 0
		camera_pivot.position += move_dir * pan_speed * camera_distance * delta

func load_geojson():
	if not FileAccess.file_exists(geojson_file_path):
		push_error("Fișierul GeoJSON nu există: " + geojson_file_path)
		return
	
	var file = FileAccess.open(geojson_file_path, FileAccess.READ)
	if file == null:
		push_error("Nu pot deschide fișierul: " + geojson_file_path)
		return
	
	var json_text = file.get_as_text()
	file.close()
	
	var json = JSON.new()
	var error = json.parse(json_text)
	if error != OK:
		push_error("Eroare parsare JSON: " + json.get_error_message())
		return
	
	var data = json.data
	
	if data.has("features"):
		var feature_count = 0
		for feature in data.features:
			if feature_count % 10 == 0:
				print("Procesare feature ", feature_count, "/", data.features.size())
			process_feature(feature)
			feature_count += 1
	
	print("GeoJSON încărcat: ", buildings.size(), " obiecte create")

func process_feature(feature: Dictionary):
	if not feature.has("geometry"):
		return
	
	var geometry = feature.geometry
	var properties = feature.get("properties", {})
	var geom_type = geometry.get("type", "")
	
	match geom_type:
		"Polygon":
			create_polygon(geometry.coordinates, properties)
		"MultiPolygon":
			for polygon in geometry.coordinates:
				create_polygon(polygon, properties)
		"LineString":
			create_linestring(geometry.coordinates, properties)
		"Point":
			create_point(geometry.coordinates, properties)

func create_polygon(coordinates: Array, properties: Dictionary):
	if coordinates.is_empty():
		return
	
	var outer_ring = coordinates[0]
	if outer_ring.size() < 3:
		return
	
	var points = []
	for coord in outer_ring:
		var lon = coord[0]
		var lat = coord[1]
		var pos = latlon_to_local(lat, lon)
		points.append(pos)
	
	# Creează mesh 2D pentru clădiri/zone
	var mesh_instance = MeshInstance3D.new()
	var array_mesh = ArrayMesh.new()
	var arrays = []
	arrays.resize(Mesh.ARRAY_MAX)
	
	var vertices = PackedVector3Array()
	var indices = PackedInt32Array()
	
	# Adaugă baza poligonului
	for point in points:
		vertices.append(point)
	
	# Triangulație fan simplă
	for i in range(1, points.size() - 2):
		indices.append(0)
		indices.append(i)
		indices.append(i + 1)
	
	# Verifică dacă e clădire pentru extrudare
	var is_building = properties.has("building") and properties.building != "no"
	var height = extrusion_height
	
	if is_building:
		if properties.has("height"):
			height = float(properties.get("height", extrusion_height))
		elif properties.has("building:levels"):
			height = float(properties.get("building:levels", 1)) * 3.0
		
		# Adaugă pereți
		var base_count = points.size()
		for i in range(base_count - 1):
			var p1 = points[i]
			var p2 = points[i + 1]
			
			var idx = vertices.size()
			vertices.append(p1)
			vertices.append(p2)
			vertices.append(p2 + Vector3(0, height, 0))
			vertices.append(p1 + Vector3(0, height, 0))
			
			indices.append(idx)
			indices.append(idx + 1)
			indices.append(idx + 2)
			indices.append(idx)
			indices.append(idx + 2)
			indices.append(idx + 3)
		
		# Acoperiș
		var roof_start = vertices.size()
		for point in points:
			vertices.append(point + Vector3(0, height, 0))
		
		for i in range(1, points.size() - 2):
			indices.append(roof_start)
			indices.append(roof_start + i)
			indices.append(roof_start + i + 1)
	
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_INDEX] = indices
	
	array_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	mesh_instance.mesh = array_mesh
	
	# Material bazat pe tip
	var material = StandardMaterial3D.new()
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

func create_linestring(coordinates: Array, properties: Dictionary):
	var line = MeshInstance3D.new()
	var immediate_mesh = ImmediateMesh.new()
	
	immediate_mesh.surface_begin(Mesh.PRIMITIVE_LINE_STRIP)
	for coord in coordinates:
		var lon = coord[0]
		var lat = coord[1]
		var pos = latlon_to_local(lat, lon)
		immediate_mesh.surface_add_vertex(pos)
	immediate_mesh.surface_end()
	
	line.mesh = immediate_mesh
	
	var material = StandardMaterial3D.new()
	if properties.has("highway"):
		material.albedo_color = Color(0.3, 0.3, 0.3, 1.0)
	else:
		material.albedo_color = Color(0.5, 0.5, 0.5, 1.0)
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	line.set_surface_override_material(0, material)
	
	add_child(line)

func create_point(coordinates: Array, properties: Dictionary):
	var marker = CSGSphere3D.new()
	marker.radius = 1.0
	
	var lon = coordinates[0]
	var lat = coordinates[1]
	marker.position = latlon_to_local(lat, lon)
	
	var material = StandardMaterial3D.new()
	material.albedo_color = Color(1.0, 0.3, 0.3, 1.0)
	marker.material = material
	
	add_child(marker)

func latlon_to_local(lat: float, lon: float) -> Vector3:
	# Conversie lat/lon la coordonate Godot
	var x = (lon - center_lon) * scale_factor
	var z = (lat - center_lat) * scale_factor
	
	return Vector3(x, 0, -z)
