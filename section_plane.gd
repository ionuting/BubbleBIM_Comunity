extends Node3D

# SectionPlane.gd
# This script handles the creation and management of a section plane with different materials for room objects.

@export var room_material: StandardMaterial3D = StandardMaterial3D.new()
@export var default_material: StandardMaterial3D = StandardMaterial3D.new()

# Declare section_plane_instance
var section_plane_instance: Node3D = null

func _ready():
	# Initialize section_plane_instance
	section_plane_instance = self

	# Set default materials
	room_material.albedo_color = Color(1.0, 0.0, 0.0) # Red for rooms
	default_material.albedo_color = Color(0.5, 0.5, 0.5) # Gray for others

	print("[DEBUG] Section plane initialized")

func _on_section_plane_position_changed(value):
	if section_plane_instance:
		# Update the plane position along the Z-axis
		section_plane_instance.update_section_plane(Vector3(0, 0, value), Vector3(0, 0, 1))

func _on_section_plane_rotation_changed(value):
	if section_plane_instance:
		# Update the plane normal based on rotation
		var radians = deg_to_rad(value)
		var normal = Vector3(cos(radians), sin(radians), 0)
		section_plane_instance.update_section_plane(Vector3(0, 0, 0), normal)
