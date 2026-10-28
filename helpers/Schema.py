import re
from pathlib import Path

import xmltodict

# Field types that don't follow the "<Type>TableFieldDefinition" naming rule
TYPE_EXCEPTIONS = {
    'StatsFunctors': 'FunctorsTableFieldDefinition',
    'StatusIDs': 'StatusIdsTableFieldDefinition',
}

# Larian projects used as reference for field types actually written by the toolkit
REFERENCE_PROJECTS = ['Shared', 'SharedDev', 'Gustav', 'GustavDev', 'GustavX']


def to_table_type(sod_type: str) -> str:
    """Translate a field type from a .sod definition into the type string used in .tbl/.stats files"""
    if sod_type in TYPE_EXCEPTIONS:
        return TYPE_EXCEPTIONS[sod_type]
    if sod_type.endswith('Field'):
        sod_type = sod_type[:-5]
    return f'{sod_type}TableFieldDefinition'


def table_key(definition: dict) -> str:
    return f"{definition['category']}/{definition['name']}"


def _as_list(val) -> list:
    if val is None:
        return []
    return val if isinstance(val, list) else [val]


def _read_xml(file: Path) -> dict:
    with open(file, 'rb') as f:
        return xmltodict.parse(f.read())


def _parse_definitions(file: Path) -> list[dict]:
    data = _read_xml(file)
    definitions = []
    for d in _as_list(data['root']['stat_object_definitions'].get('stat_object_definition')):
        fields = []
        for fd in _as_list((d.get('field_definitions') or {}).get('field_definition')):
            field = {
                'name': fd['@name'],
                'export_name': fd.get('@export_name', fd['@name']),
                'type': to_table_type(fd['@type']),
            }
            for key, attr in [('enum', '@enumeration_type_name'), ('category', '@export_category'),
                              ('item', '@export_containter_item_name'), ('internal', '@is_internal'),
                              ('compile_by', '@compile_by'), ('compilation_type', '@compilation_type')]:
                if fd.get(attr) is not None:
                    field[key] = fd[attr]
            fields.append(field)
        definitions.append({
            'id': d['@id'].lower(),
            'name': d['@name'],
            'export_name': d.get('@export_name', d['@name']),
            'export_type': d.get('@export_type', d['@name']),
            'category': d.get('@category', ''),
            'split': d.get('@split_based_on'),
            'fields': fields,
        })
    return definitions


def _parse_enumerations(file: Path) -> dict:
    enums = {}
    data = _read_xml(file)
    for e in _as_list(data['root']['enumerations'].get('enumeration')):
        items = _as_list((e.get('items') or {}).get('item'))
        index = {}
        for pos, item in enumerate(items):
            index[item.get('@index', str(pos))] = item['@value']
        enums[e['@name']] = index
    return enums


def _observed_types(editor_mods: Path) -> dict:
    """Collect field types written by the toolkit itself, keyed by definition id"""
    observed = {}
    for project in REFERENCE_PROJECTS:
        root = editor_mods / project
        if not root.is_dir():
            continue
        for file in list(root.rglob('*.tbl')) + list((root / 'Stats').rglob('*.stats')):
            text = file.read_text(encoding='utf-8-sig', errors='ignore')
            def_id = re.search(r'stat_object_definition_id="([^"]*)"', text)
            if def_id is None:
                continue
            fields = observed.setdefault(def_id.group(1).lower(), {})
            for name, typ in re.findall(r'<field name="([^"]*)" type="([^"]*)"', text):
                fields.setdefault(name, typ)
    return observed


def compile_schema(bg3_path: str) -> dict:
    """
        Builds the conversion schema from the toolkit's own definitions:
        - Data/Editor/Config/UuidObjects/TableDefinitions.sod (lsx <-> tbl)
        - Data/Editor/Config/Stats/StatObjectDefinitions.sod (txt <-> stats)
    """
    config = Path(bg3_path) / 'Data/Editor/Config'
    table_defs = _parse_definitions(config / 'UuidObjects/TableDefinitions.sod')
    stat_defs = _parse_definitions(config / 'Stats/StatObjectDefinitions.sod')
    observed = _observed_types(Path(bg3_path) / 'Data/Editor/Mods')

    # Prefer the types the toolkit actually writes over the derived ones
    for d in table_defs + stat_defs:
        seen = observed.get(d['id'], {})
        for field in d['fields']:
            if field['name'] in seen and seen[field['name']]:
                field['type'] = seen[field['name']]

    enums = _parse_enumerations(config / 'UuidObjects/Enumerations.toe')
    stat_enums = _parse_enumerations(config / 'Stats/Enumerations.xml')

    # Table names are only unique per category (e.g. Feats/Feats and DefaultValues/Feats)
    by_export = {}
    for d in table_defs:
        by_export.setdefault(d['export_type'], []).append(table_key(d))

    return {
        'Tables': {table_key(d): d for d in table_defs},
        'TablesByRegion': by_export,
        'Stats': {d['name']: d for d in stat_defs},
        'Enums': enums,
        'StatEnums': stat_enums,
    }
