#!/usr/bin/env python3
"""
Door and Window Block Processor
Procesează blocurile de doors și windows conform logicii TOV/FOV
"""

import ezdxf
import os
import json
from typing import Dict, List, Tuple, Optional, Any
import logging
import traceback

class DoorWindowProcessor:
    """Procesează blocurile de doors și windows cu logica TOV/FOV"""
    
    def __init__(self):
        # Căile relative la biblioteci
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.library_paths = {
            'doors': os.path.join(base_dir, "dxf_library", "doors_lib.dxf"),
            'windows': os.path.join(base_dir, "dxf_library", "windows_lib.dxf")
        }
        self.default_thickness = 0.15  # Thickness mai mare pentru vizibilitate
        self.library_blocks = {}  # Cache pentru blocuri din biblioteci
        self.loaded_libraries = set()
        
        # Layer mapping pentru solid/cut logic (original mapping for fallback)
        self.layer_solid_map = {
            '0': 1,  # solid
            'glass': 0,  # cut - sticla
            'IfcDoor': 1,  # solid - cadru
            'IfcWindow': 1,  # solid - cadru
            'window': 0,  # cut - sticla
            'wood': 1,  # solid - material (va fi override în funcție de context)
            'wall': 1,  # solid
            'walls': 1,  # solid
        }
        
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
    
    def _get_solid_flag_for_layer(self, layer_name: str, lib_type: str) -> int:
        """
        Determină solid flag-ul pentru un layer în funcție de context (doors vs windows)
        
        Pentru uși (doors):
        - wood = void (0) - deschidere în perete  
        - glass = void (0) - transparent
        - door_frame = solid (1) - cadrul ușii
        
        Pentru ferestre (windows):
        - wood = solid (1) - cadrul ferestrei
        - glass = void (0) - transparent, dar poate fi și solid pentru vizualizare
        - window_frame = solid (1) - cadrul ferestrei
        """
        # Pentru uși, majoritatea componentelor sunt void-uri (taie pereții)
        if lib_type == 'doors':
            door_mapping = {
                'wood': 0,  # Deschidere ușă
                'glass': 0,  # Sticla ușii (dacă există)
                'IfcDoor': 0,  # Deschidere ușă
                'door_frame': 1,  # Doar cadrul rămâne solid
                'frame': 1,  # Cadrul
                'wall': 1,  # Ziduri rămân solide
            }
            return door_mapping.get(layer_name, self.layer_solid_map.get(layer_name, 0))  # Default void pentru uși
        
        # Pentru ferestre, cadrele sunt solide, sticla e transparentă
        elif lib_type == 'windows':
            window_mapping = {
                'wood': 1,  # Cadrul ferestrei solid
                'glass': 0,  # Sticla transparentă (void)
                'IfcWindow': 1,  # Cadrul ferestrei solid
                'window_frame': 1,  # Cadrul
                'frame': 1,  # Cadrul
                'wall': 1,  # Ziduri rămân solide
            }
            return window_mapping.get(layer_name, self.layer_solid_map.get(layer_name, 1))  # Default solid pentru ferestre
        
        # Fallback la mapping-ul original
        return self.layer_solid_map.get(layer_name, 1)
    
    def load_library(self, lib_type: str) -> bool:
        """Încarcă biblioteca de blocuri (doors/windows)"""
        if lib_type in self.loaded_libraries:
            return True
            
        lib_path = self.library_paths.get(lib_type)
        if not lib_path or not os.path.exists(lib_path):
            self.logger.warning(f"Library {lib_type} not found at {lib_path}")
            return False
            
        try:
            doc = ezdxf.readfile(lib_path)
            blocks = {}
            
            for block in doc.blocks:
                if not block.name.startswith('*'):  # Skip system blocks
                    blocks[block.name] = {
                        'block': block,
                        'doc': doc,
                        'type': self._get_block_type(block.name)
                    }
            
            self.library_blocks[lib_type] = blocks
            self.loaded_libraries.add(lib_type)
            self.logger.info(f"Loaded {lib_type} library: {len(blocks)} blocks")
            return True
            
        except Exception as e:
            self.logger.error(f"Error loading {lib_type} library: {e}")
            return False
    
    def _get_block_type(self, block_name: str) -> str:
        """Determină tipul blocului (TOV/FOV/OTHER)"""
        if block_name.endswith('_TOV'):
            return 'TOV'
        elif block_name.endswith('_FOV'):
            return 'FOV'
        else:
            return 'OTHER'
    
    def _get_base_name(self, block_name: str) -> str:
        """Extrage numele de bază (fără _TOV/_FOV)"""
        if block_name.endswith('_TOV') or block_name.endswith('_FOV'):
            return block_name[:-4]
        return block_name
    
    def find_matching_pairs(self, lib_type: str) -> List[Tuple[str, str]]:
        """Găsește perechile TOV/FOV valide în bibliotecă"""
        if not self.load_library(lib_type):
            return []
            
        blocks = self.library_blocks[lib_type]
        pairs = []
        
        # Find TOV blocks and look for matching FOV
        for block_name, block_info in blocks.items():
            if block_info['type'] == 'TOV':
                base_name = self._get_base_name(block_name)
                fov_name = base_name + '_FOV'
                
                if fov_name in blocks:
                    pairs.append((block_name, fov_name))
                    self.logger.info(f"Found valid pair: {base_name}")
                else:
                    self.logger.warning(f"TOV without FOV: {block_name}")
        
        return pairs
    
    def extract_tov_data(self, tov_insert, plan_doc) -> Optional[Dict]:
        """Extrage datele de poziționare din blocul TOV din plan"""
        try:
            # Poziție din INSERT
            position = (
                tov_insert.dxf.insert.x,
                tov_insert.dxf.insert.y,
                getattr(tov_insert.dxf, 'insert_z', 0.0)  # Z din TOV
            )
            
            # Rotație din INSERT sau xDATA
            rotation = getattr(tov_insert.dxf, 'rotation', 0.0)
            
            # Caută xDATA pentru informații suplimentare
            angle_from_xdata = None
            if hasattr(tov_insert, 'xdata') and tov_insert.xdata:
                try:
                    for appid in tov_insert.xdata:
                        xdata_list = tov_insert.xdata[appid]
                        for i, xdata in enumerate(xdata_list):
                            if hasattr(xdata, 'value'):
                                val = xdata.value
                                if isinstance(val, str) and 'angle' in val.lower():
                                    # Următorul item ar putea fi valoarea
                                    if i + 1 < len(xdata_list):
                                        next_xdata = xdata_list[i + 1]
                                        if hasattr(next_xdata, 'value') and isinstance(next_xdata.value, (int, float)):
                                            angle_from_xdata = float(next_xdata.value)
                except Exception as e:
                    self.logger.debug(f"Error reading xDATA: {e}")
            
            # Use angle from xDATA if available, otherwise use rotation
            final_angle = angle_from_xdata if angle_from_xdata is not None else rotation
            
            return {
                'position': position,
                'rotation': final_angle,
                'scale': (
                    getattr(tov_insert.dxf, 'xscale', 1.0),
                    getattr(tov_insert.dxf, 'yscale', 1.0),
                    getattr(tov_insert.dxf, 'zscale', 1.0)
                )
            }
            
        except Exception as e:
            self.logger.error(f"Error extracting TOV data: {e}")
            return None
    
    def extract_fov_geometry(self, fov_block, lib_doc, lib_type: str = 'windows') -> Dict:
        """Extrage geometria din blocul FOV cu layere separate"""
        try:
            layers_data = {}
            thickness_data = {}
            
            entities = list(fov_block)
            
            for entity in entities:
                layer_name = entity.dxf.layer
                
                if layer_name not in layers_data:
                    layers_data[layer_name] = {
                        'entities': [],
                        'solid': self._get_solid_flag_for_layer(layer_name, lib_type),  # Context-aware solid/void
                        'thickness': self.default_thickness
                    }
                
                layers_data[layer_name]['entities'].append(entity)
                
                # Look for thickness in xDATA
                if hasattr(entity, 'xdata') and entity.xdata:
                    try:
                        for appid in entity.xdata:
                            xdata_list = entity.xdata[appid]
                            for i, xdata in enumerate(xdata_list):
                                if hasattr(xdata, 'value'):
                                    val = str(xdata.value).lower()
                                    if 'height' in val or 'thickness' in val:
                                        # Look for numeric value
                                        if i + 1 < len(xdata_list):
                                            next_xdata = xdata_list[i + 1]
                                            if hasattr(next_xdata, 'value') and isinstance(next_xdata.value, (int, float)):
                                                layers_data[layer_name]['thickness'] = float(next_xdata.value)
                    except Exception as e:
                        self.logger.debug(f"Error reading thickness xDATA: {e}")
            
            return layers_data
            
        except Exception as e:
            self.logger.error(f"Error extracting FOV geometry: {e}")
            return {}
    
    def determine_rotation_axis(self, angle: float) -> str:
        """Determină axa de rotație bazată pe unghi"""
        # Normalize angle to 0-360
        angle = angle % 360
        
        if angle in [0, 180]:
            return 'x'  # Rotație în jurul axei X
        elif angle in [90, 270]:
            return 'y'  # Rotație în jurul axei Y
        else:
            # Pentru alte unghiuri, folosește logica cea mai apropiată
            if 45 <= angle <= 135 or 225 <= angle <= 315:
                return 'y'
            else:
                return 'x'
    
    def process_door_window_blocks(self, dxf_file_path: str) -> Dict:
        """Procesează toate blocurile door/window dintr-un fișier DXF"""
        try:
            doc = ezdxf.readfile(dxf_file_path)
            
            # Load libraries
            self.load_library('doors')
            self.load_library('windows')
            
            processed_blocks = {
                'doors': [],
                'windows': [],
                'errors': []
            }
            
            # Find all INSERT entities in model space
            msp = doc.modelspace()
            
            for entity in msp:
                if entity.dxftype() != 'INSERT':
                    continue
                    
                block_name = entity.dxf.name
                
                # Check if it's a TOV block
                if not block_name.endswith('_TOV'):
                    continue
                
                base_name = self._get_base_name(block_name)
                fov_name = base_name + '_FOV'
                
                # Determine library type
                lib_type = 'doors' if base_name.lower().startswith('door') else 'windows'
                
                # Check if FOV exists in library
                if lib_type not in self.library_blocks:
                    self.logger.warning(f"Library {lib_type} not loaded")
                    continue
                
                if fov_name not in self.library_blocks[lib_type]:
                    self.logger.warning(f"FOV block {fov_name} not found in {lib_type} library")
                    processed_blocks['errors'].append(f"Missing FOV: {fov_name}")
                    continue
                
                # Extract TOV positioning data
                tov_data = self.extract_tov_data(entity, doc)
                if not tov_data:
                    self.logger.error(f"Failed to extract TOV data for {block_name}")
                    processed_blocks['errors'].append(f"Invalid TOV data: {block_name}")
                    continue
                
                # Extract FOV geometry
                fov_block = self.library_blocks[lib_type][fov_name]['block']
                fov_doc = self.library_blocks[lib_type][fov_name]['doc']
                fov_geometry = self.extract_fov_geometry(fov_block, fov_doc, lib_type)
                
                if not fov_geometry:
                    self.logger.error(f"Failed to extract FOV geometry for {fov_name}")
                    processed_blocks['errors'].append(f"Invalid FOV geometry: {fov_name}")
                    continue
                
                # Combine data
                processed_block = {
                    'base_name': base_name,
                    'tov_name': block_name,
                    'fov_name': fov_name,
                    'position': tov_data['position'],
                    'rotation': tov_data['rotation'],
                    'rotation_axis': self.determine_rotation_axis(tov_data['rotation']),
                    'scale': tov_data['scale'],
                    'layers': fov_geometry
                }
                
                processed_blocks[lib_type].append(processed_block)
                self.logger.info(f"Processed {lib_type[:-1]}: {base_name}")
            
            return processed_blocks
            
        except Exception as e:
            self.logger.error(f"Error processing {dxf_file_path}: {e}")
            self.logger.error(traceback.format_exc())
            return {'doors': [], 'windows': [], 'errors': [str(e)]}

def main():
    """Test the door/window processor"""
    processor = DoorWindowProcessor()
    
    # Test library loading
    print("=== Testing Library Loading ===")
    doors_pairs = processor.find_matching_pairs('doors')
    windows_pairs = processor.find_matching_pairs('windows')
    
    print(f"Doors pairs found: {len(doors_pairs)}")
    for tov, fov in doors_pairs:
        print(f"  {tov} <-> {fov}")
    
    print(f"Windows pairs found: {len(windows_pairs)}")
    for tov, fov in windows_pairs:
        print(f"  {tov} <-> {fov}")
    
    # Test processing a DXF file (if exists)
    test_dxf = "test.dxf"  # Replace with actual test file
    if os.path.exists(test_dxf):
        print(f"\n=== Testing DXF Processing: {test_dxf} ===")
        result = processor.process_door_window_blocks(test_dxf)
        print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()