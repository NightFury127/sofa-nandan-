#!/usr/bin/env python
"""Test extended schema and export JSON."""

import sys
sys.path.insert(0, 'src')

from component_schema_extended import (
    COMPONENT_SCHEMA_EXTENDED, FUSION_FOLDER_STRUCTURE, 
    export_schema_to_json, validate_folder_coverage
)
from pathlib import Path

# Validate coverage
unmapped, empty = validate_folder_coverage()
print('=== SCHEMA VALIDATION ===')
print(f'Total components: {len(COMPONENT_SCHEMA_EXTENDED)}')
print(f'Total Fusion folders: {len(FUSION_FOLDER_STRUCTURE)}')
print(f'Unmapped components: {len(unmapped)}')
if unmapped: 
    print(f'  Missing fusion_folder: {unmapped}')
else: 
    print('  OK - All components mapped')
print(f'Empty folders: {len(empty)}')
if empty: 
    print(f'  Empty: {empty}')
else: 
    print('  OK - All folders populated')

# Count components per folder
print()
print('=== COMPONENT DISTRIBUTION ===')
total_comps = 0
for folder_key, folder_data in FUSION_FOLDER_STRUCTURE.items():
    comp_count = len(folder_data.get('component_ids', []))
    print(f"{folder_data['folder_name']}: {comp_count} components")
    total_comps += comp_count
print(f'Total in folders: {total_comps}')

# Export JSON
print()
print('=== EXPORTING JSON ===')
json_str = export_schema_to_json(Path('data/component_schema.json'))
print(f'JSON exported: {len(json_str)} characters')
print('File: data/component_schema.json')

# List some components with their mappings
print()
print('=== SAMPLE COMPONENT MAPPINGS ===')
for comp_id in ['seat_rail_front', 'spring_unit', 'fabric_seat', 'handle_foam', 'adhesive']:
    comp = COMPONENT_SCHEMA_EXTENDED.get(comp_id)
    if comp:
        folder = comp.get('fusion_folder', 'UNMAPPED')
        print(f'{comp_id:20} -> {folder}')
