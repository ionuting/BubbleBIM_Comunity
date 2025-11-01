# Registry pentru tipuri de elemente CAD/BIM
# Poate fi folosit independent sau importat în Viewer2D

class_name ElementRegistry

var factories := {}

# Înregistrează o funcție de creare pentru un tip nou
tool
static func register_type(type_name: String, factory_func: Callable) -> void:
	factories[type_name] = factory_func

# Creează un element pe baza tipului și parametrilor din JSON
static func create_element(obj: Dictionary):
	var type = obj.get("type", "")
	if factories.has(type):
		return factories[type](obj)
	else:
		push_error("Tip necunoscut: " + type)
		return null

# Exemplu de funcții de creare (pot fi mutate în scripturi separate)
static func create_column(obj):
	# Returnează un nod/mesh/structură pentru column
	# Exemplu: return Node3D.new() sau mesh generat
	return {"type": "column", "params": obj}

static func create_wall(obj):
	return {"type": "wall", "params": obj}

static func create_shell(obj):
	return {"type": "shell", "params": obj}

# Înregistrare tipuri de bază
static func register_defaults():
	register_type("column", Callable(self, "create_column"))
	register_type("wall", Callable(self, "create_wall"))
	register_type("shell", Callable(self, "create_shell"))
