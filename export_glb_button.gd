extends Control

@onready var export_btn: Button = $ExportButton
@onready var export_ifc_btn: Button = $ExportIFC
@onready var status_label: Label = $StatusLabel

func _ready():
	export_btn.pressed.connect(_on_export_btn_pressed)
	export_ifc_btn.pressed.connect(_on_export_ifc_btn_pressed)

func _on_export_btn_pressed():
	status_label.text = "Export GLB în curs..."
	var python_exe = "python"
	var script_path = "python/dxf_to_glb_trimesh.py"
	var input_dxf = "python/dxf/etaj_01.dxf"
	var output_glb = "python/dxf/etaj_02.glb"
	var args = [script_path, input_dxf, output_glb]
	var output = []
	var exit_code = OS.execute(python_exe, args, output, true)
	if exit_code == 0:
		status_label.text = "Export GLB reușit: %s" % output_glb
	else:
		var msg = "Eroare la export GLB!\n"
		for line in output:
			msg += str(line) + "\n"
		status_label.text = msg
		print(msg)

func _on_export_ifc_btn_pressed():
	status_label.text = "Export IFC în curs..."
	var python_exe = "python"
	var script_path = "python/dxf_to_ifc43.py"
	var input_dxf = "python/dxf/etaj_01.dxf"
	var output_ifc = "python/dxf/etaj_02.ifc"
	var args = [script_path, input_dxf, output_ifc]
	var output = []
	var exit_code = OS.execute(python_exe, args, output, true)
	if exit_code == 0:
		status_label.text = "Export IFC reușit: %s" % output_ifc
	else:
		var msg = "Eroare la export IFC!\n"
		for line in output:
			msg += str(line) + "\n"
		status_label.text = msg
		print(msg)
