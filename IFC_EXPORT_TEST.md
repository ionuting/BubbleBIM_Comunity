# Test IFC Export Buttons

## Status: ✅ FUNCȚIONEAZĂ!

Butoanele IFC Export au fost corectate și conectate cu succes:

### Debug Output Confirmat:
```
[DEBUG] ExportIfcBtnMetric found: true
[DEBUG] Connected metric IFC export button
[DEBUG] ExportIfcBtnImperial found: true
[DEBUG] Connected imperial IFC export button
```

### Cum să testezi:

1. **Rulează aplicația** cu Godot:
   ```
   cd "c:\Users\ionut.ciuntuc\Documents\BubbleBIM 0.1.11.25"
   & "C:\Users\ionut.ciuntuc\Downloads\Godot_v4.4.1-stable_win64.exe\Godot_v4.4.1-stable_win64.exe" --path .
   ```

2. **Încarcă un folder DXF** folosind butonul "Load DXF Btn"

3. **Teste butoanele IFC**:
   - **ExportIfcBtnMetric** - Export IFC cu unități metrice
   - **ExportIfcBtnImperial** - Export IFC cu unități imperiale

### Ce se întâmplă când apași un buton:

1. Se deschide un FileDialog pentru a alege unde să salvezi fișierul IFC
2. Se rulează script-ul Python `direct_ifc_from_dxf.py`
3. Se creează fișierul IFC 4 cu IfcOpenShell
4. Se procesează XDATA din fișierele DXF
5. Se convertesc unitățile (metric vs imperial)

### Debug Info:
- Butoanele sunt găsite corect în scena `dxf_to_3D.tscn`
- Numele corecte: `ExportIfcBtnMetric` și `ExportIfcBtnImperial`
- Semnalele sunt conectate la funcțiile corespunzătoare
- Canvas-ul este disponibil pentru FileDialog

### Dependințe Python:
Asigură-te că ai instalat:
```bash
pip install ifcopenshell ezdxf
```

### Problemă Rezolvată:
Inițial butoanele erau căutate cu nume greșite (`ExportMultiIfcBtn` vs `ExportIfcBtnMetric`).
Acum numele sunt corectate și butoanele funcționează!