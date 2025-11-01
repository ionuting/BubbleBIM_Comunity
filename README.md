# BubbleBIM - DXF to 3D Viewer

A Godot-based CAD viewer for converting and visualizing DXF files in 3D with IFC export capabilities.

## Features

- 🏗️ **DXF to GLB Conversion**: Convert AutoCAD DXF files to 3D GLB meshes
- 🔍 **3D Viewer**: Interactive CAD viewer with zoom, pan, and navigation
- 📐 **Grid & Axes**: Professional CAD-style grid and coordinate system
- ✂️ **Cut Shader Integration**: Advanced sectioning and cutting planes
- 🏢 **IFC Export**: Export spaces and geometry to Industry Foundation Classes format
- 📁 **File Monitoring**: Automatic reload when DXF files change
- 🎯 **Multi-Level Support**: Handle complex architectural drawings

## Requirements

- **Godot 4.4.1+** (recommended 4.4.1)
- **Python 3.8+** with packages:
  - `ezdxf` - DXF file parsing
  - `trimesh` - 3D mesh processing
  - `shapely` - 2D geometry operations
  - `watchdog` - File monitoring
  - `ifcopenshell` - IFC processing (optional)

## Quick Start

1. **Clone the repository**
    Download or clone the BubbleBIM repository to your local machine.

2. **Install Python dependencies**
   ```bash
   python python/setup_dependencies.py
   ```

3. **Open in Godot**
   - Launch Godot Engine
   - Import project by selecting `project.godot`
   - Run the main scene `dxf_to_3D.tscn`

4. **Load DXF files**
   - Click "Selecteaza folder dxf"
   - Choose a folder containing `.dxf` files
   - Files will be automatically converted and displayed

## Usage

### DXF Conversion
```bash
# Manual conversion
python python/dxf_to_glb_trimesh.py input.dxf output.glb

# Automatic monitoring
python python/dxf_watchdog.py
```

### IFC Export
- Use "Export IFC Spaces" for single-level export
- Use "Export Multi-Level IFC" for complex buildings

## Project Structure

```
BubbleBIM/
├── dxf_to_3D.tscn              # Main 3D viewer scene
├── cad_viewer_3d.gd            # Core CAD viewer logic
├── CutShaderIntegration3D.gd   # Cut shader functionality
├── python/                     # Python conversion scripts
│   ├── dxf_to_glb_trimesh.py  # DXF to GLB converter
│   ├── setup_dependencies.py   # Dependency installer
│   └── requirements.txt        # Python packages
└── layer_materials.json       # Material configuration
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the **GNU Lesser General Public License v3.0 or later (LGPL-3.0-or-later)** - see the [LICENSE](LICENSE) file for details.

**Important**: Due to the dependency on **IfcOpenShell** (LGPL-3.0), this project must be licensed under LGPL-3.0 to maintain license compatibility. While other dependencies use more permissive licenses (MIT, BSD, Apache 2.0), the most restrictive license (LGPL) governs the combined work.

## Acknowledgments

- Built with [Godot Engine](https://godotengine.org/)
- DXF parsing by [ezdxf](https://ezdxf.readthedocs.io/)
- 3D processing by [Trimesh](https://trimsh.org/)
- IFC support by [IfcOpenShell](http://ifcopenshell.org/)