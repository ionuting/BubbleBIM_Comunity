#!/usr/bin/env python3
"""
IFC Material Layer Set Inspector
==============================

Acest tool inspectează materialele dintr-un fișier IFC, 
în special IfcMaterialLayerSet pentru a vedea structura pe straturi.
"""

import ifcopenshell
import sys
from pathlib import Path

def inspect_ifc_materials(ifc_path: str):
    """Inspectează materialele dintr-un fișier IFC"""
    
    try:
        model = ifcopenshell.open(ifc_path)
        print(f"=== IFC Material Inspector: {Path(ifc_path).name} ===\n")
        
        # 1. Materiale simple
        materials = model.by_type("IfcMaterial")
        if materials:
            print(f"📦 Found {len(materials)} IfcMaterial entities:")
            for mat in materials:
                category = getattr(mat, 'Category', 'N/A')
                print(f"  - {mat.Name} (Category: {category})")
            print()
        
        # 2. Material Layer Sets
        layer_sets = model.by_type("IfcMaterialLayerSet")
        if layer_sets:
            print(f"🏗️  Found {len(layer_sets)} IfcMaterialLayerSet entities:")
            for ls in layer_sets:
                print(f"\n  📋 LayerSet: {ls.LayerSetName}")
                print(f"     Description: {getattr(ls, 'Description', 'N/A')}")
                
                if hasattr(ls, 'MaterialLayers') and ls.MaterialLayers:
                    total_thickness = 0
                    print(f"     Layers ({len(ls.MaterialLayers)}):")
                    
                    for i, layer in enumerate(ls.MaterialLayers, 1):
                        thickness = layer.LayerThickness
                        total_thickness += thickness
                        material_name = layer.Material.Name if layer.Material else 'Unknown'
                        material_category = getattr(layer.Material, 'Category', 'N/A') if layer.Material else 'N/A'
                        
                        print(f"       {i}. {material_name}")
                        print(f"          Thickness: {thickness:.3f}m")
                        print(f"          Category: {material_category}")
                    
                    print(f"     📏 Total Thickness: {total_thickness:.3f}m")
            print()
        
        # 3. Elemente cu materiale atribuite
        print("🔗 Elements with assigned materials:")
        
        # Găsește toate relațiile de material
        material_relations = model.by_type("IfcRelAssociatesMaterial")
        
        for rel in material_relations:
            material = rel.RelatingMaterial
            elements = rel.RelatedObjects
            
            if hasattr(material, 'LayerSetName'):  # IfcMaterialLayerSet
                print(f"\n  🏗️  MaterialLayerSet: {material.LayerSetName}")
                print(f"     Applied to {len(elements)} elements:")
                for elem in elements[:3]:  # Show first 3 elements
                    elem_type = elem.is_a()
                    elem_name = getattr(elem, 'Name', f'Unnamed_{elem_type}')
                    print(f"       - {elem_type}: {elem_name}")
                if len(elements) > 3:
                    print(f"       ... and {len(elements)-3} more")
                    
            elif hasattr(material, 'Name'):  # IfcMaterial
                print(f"\n  📦 Material: {material.Name}")
                print(f"     Applied to {len(elements)} elements:")
                for elem in elements[:3]:  # Show first 3 elements
                    elem_type = elem.is_a()
                    elem_name = getattr(elem, 'Name', f'Unnamed_{elem_type}')
                    print(f"       - {elem_type}: {elem_name}")
                if len(elements) > 3:
                    print(f"       ... and {len(elements)-3} more")
        
        print(f"\n✅ Inspection complete!")
        
    except Exception as e:
        print(f"❌ Error inspecting {ifc_path}: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        ifc_file = sys.argv[1]
    else:
        # Default to test file
        ifc_file = "test_column_no_trim_from_glb.ifc"
    
    if not Path(ifc_file).exists():
        print(f"❌ File not found: {ifc_file}")
        sys.exit(1)
    
    inspect_ifc_materials(ifc_file)