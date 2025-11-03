# IFC Export Parameter Fix

## Problemă Identificată și Rezolvată ✅

### Problema:
Butoanele IFC Export transmiseră argumentele în ordine greșită către script-ul Python.

### Cauza:
În GDScript, când conectez signal-ul FileDialog cu `.bind()`, ordinea parametrilor devine confuză:

```gdscript
file_dialog.file_selected.connect(_on_ifc_export_path_selected.bind(unit_system))
```

FileDialog emit `file_selected(file_path)`, dar cu `.bind(unit_system)`, funcția primește:
- Primul parametru: `file_path` (din signal)
- Al doilea parametru: `unit_system` (din bind)

### Fix Aplicat:
Schimbat ordinea parametrilor în funcție:

**ÎNAINTE (greșit):**
```gdscript
func _on_ifc_export_path_selected(unit_system: String, file_path: String):
```

**DUPĂ (corect):**
```gdscript
func _on_ifc_export_path_selected(file_path: String, unit_system: String):
```

### Rezultat:
Acum argumentele sunt transmise corect către Python:
- `sys.argv[1]` = calea fișierului IFC (output_ifc)
- `sys.argv[2]` = sistemul de unități ("metric" sau "imperial")
- `sys.argv[3:]` = lista de fișiere DXF

### Test:
Butoanele IFC Export ar trebui să funcționeze corect acum!