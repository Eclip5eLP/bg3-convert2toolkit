import os
import re
import uuid
from pathlib import Path

import xmltodict
from colorama import Fore

from helpers.LSLibUtil import LSLibUtil


def map_modifier_type(attribute_type: str) -> str:
    if attribute_type == "1":
        return "Add"
    elif attribute_type == "2":
        return "Multiply"
    elif attribute_type == "3":
        return "Override"
    elif attribute_type == "4":
        return "Template"
    else:
        print(f'{Fore.YELLOW}[info] Unknown modifier type in Rulebook [{attribute_type}] {Fore.RESET}')
        return attribute_type


def as_list(val) -> list:
    if val is None:
        return []
    return val if isinstance(val, list) else [val]


def strip_suffixes(name: str) -> str:
    # Due to unpacking some files get multiple suffixes (e.g. Progressions.lsf.lsx)
    while Path(name).suffix.lower() in {'.lsx', '.lsf', '.lsb', '.lsbs', '.lsbc', '.lsfx'}:
        name = Path(name).stem
    return name


def is_guid(val: str) -> bool:
    return re.fullmatch(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', val or '') is not None


class LSXconvert:
    lslib_util: LSLibUtil = None

    # Region ids of resources that the toolkit keeps as binary .lsf files
    lsf_types = ['Templates', 'SkeletonBank', 'MaterialBank', 'TextureBank', 'VisualBank', 'EffectBank', 'Tags',
                 'MultiEffectInfos', 'CharacterVisualBank', 'Material', 'MaterialPresetBank', 'PhysicsBank']
    atlas_types = ['IconUVList', 'TextureAtlasInfo']
    vfx_types = ['Effect', 'Dependencies']

    # Init
    def __init__(self, db=None, lslib_util: LSLibUtil = None, root_path: Path = None):
        self.file_type = None
        self.file = None
        self.data = None
        self.uuid = None
        self.db = db
        self.schema = (db or {}).get('Schema', {})
        self.root_path = root_path
        self.lslib_util = lslib_util
        self.pending = {}  # out path -> {definition, objects (uuid -> stat_object)}
        self.non_canonical = set()  # converted sources that don't live where the toolkit writes them

    def setUUID(self, uuid=None):
        self.uuid = uuid

    # Main call convert function
    def convert(self, file):
        self.file = str(file)
        self.readxml(self.file)
        self.file_type = self.getDataType()

        # Ignore Texture Atlas
        if self.file_type in self.atlas_types:
            print(f'{Fore.YELLOW}[info] Skipped file: {os.path.basename(self.file)} (Reason: Texture atlas doesnt need conversion){Fore.RESET}')
            return False

        # Convert VFX (lsfx.lsx to lsfx)
        if self.file_type in self.vfx_types:
            if self._needs_binary():
                self.lsx2lsf(lsfx=True, verbose=False)
            print(f'{Fore.YELLOW}[info] Kept {os.path.basename(self.file)} as lsfx (Reason: VFX to lsefx not yet supported){Fore.RESET}')
            return False

        # MultiEffectInfos get an additional .mei file for the toolkit editor
        if self.file_type == 'MultiEffectInfos':
            if self._needs_binary():
                self.lsx2lsf(verbose=False)
            out = Path(self.file).with_name(strip_suffixes(Path(self.file).name) + '.mei')
            self._write(self.build_mei_file(), out)
            print(f'{Fore.GREEN}[info] Converted {os.path.basename(self.file)} (Built .mei){Fore.RESET}')
            return True

        # Visual resources and templates stay binary
        if self.file_type in self.lsf_types:
            if self._needs_binary():
                self.lsx2lsf(verbose=False)
                print(f'{Fore.GREEN}[info] Converted {os.path.basename(self.file)} (Converted to LSF){Fore.RESET}')
            return False

        definition_key = self.get_definition_key()
        if definition_key is None:
            print(f'{Fore.YELLOW}[info] Skipped file: {os.path.basename(self.file)} (Reason: {self.file_type} is not a toolkit table){Fore.RESET}')
            return False

        self.convert_table(definition_key)
        return True

    # Read data from xml file
    def readxml(self, file):
        self.file = str(file)
        with open(file, 'r+b') as f:
            self.data = xmltodict.parse(f.read())
        return self.data

    # Write data to xml file
    def writexml(self, data, file=None, source_ext='.lsx', dest_ext='.tbl'):
        if data is None:
            return False
        file = Path(file if file is not None else self.file)
        if file.suffix == source_ext:
            file = file.with_suffix(dest_ext)
        self._write(data, file)
        return True

    @staticmethod
    def _write(data, out: Path):
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, 'w', encoding="utf-8") as f:
            f.write(xmltodict.unparse(data, pretty=True, indent='  '))

    # A binary only needs to be generated if the original binary wasn't kept next to its lsx
    def _needs_binary(self) -> bool:
        stem = strip_suffixes(Path(self.file).name)
        return not any(Path(self.file).with_name(stem + ext).exists() for ext in ['.lsf', '.lsfx'])

    def getDataType(self, file=None):
        if file is not None:
            self.readxml(file)
        else:
            file = self.file
        fname = strip_suffixes(os.path.basename(file))
        regions = as_list(self.data['save'].get('region'))
        if not regions:
            return fname
        return regions[0].get('@id', fname)

    # region Table conversion
    def get_definition_key(self, file_type=None, file=None):
        file_type = file_type or self.file_type
        file = file or self.file
        candidates = self.schema.get('TablesByRegion', {}).get(file_type, [])
        if len(candidates) == 1:
            return candidates[0]
        stem = strip_suffixes(os.path.basename(file))
        # Multiple definitions share a region (DefaultValues), pick by file name
        for key in candidates:
            if key.split('/')[-1] == stem:
                return key
        for key in candidates:
            if stem.startswith(key.split('/')[-1]):
                return key
        return None

    def output_path(self, definition: dict, file=None) -> Path:
        """Canonical location of the tbl, relative to the Public/<mod>/ folder the source lives in"""
        file = Path(file or self.file)
        parts = file.parts
        root = file.parent
        for i in range(len(parts) - 3, -1, -1):
            if parts[i] == 'Public':
                root = Path(*parts[:i + 2])
                break
        return root / definition['category'] / f"{definition['name']}.tbl"

    def convert_table(self, definition_key: str):
        definition = self.schema['Tables'][definition_key]
        objects = self.build_table_objects(definition)
        out = self.output_path(definition)

        # The toolkit regenerates the lsx at its canonical location, others would load the same data twice
        source = Path(self.file)
        canonical_dir = out.with_suffix('') if definition.get('split') else out.parent
        if source.parent != canonical_dir or not definition.get('split') and strip_suffixes(source.name) != definition['name']:
            self.non_canonical.add(source)

        if definition.get('split'):
            # One file per object (e.g. ApprovalRatings/Reactions/<uuid>.tbl)
            for obj in objects:
                obj_uuid = self._field_value(obj, 'UUID')
                self._add_pending(out.with_suffix('') / f'{obj_uuid}.tbl', definition, [obj])
        else:
            self._add_pending(out, definition, objects)
        print(f"{Fore.GREEN}[info] Converted {os.path.basename(self.file)} ({definition_key}, {len(objects)} entries){Fore.RESET}")

    def _add_pending(self, out: Path, definition: dict, objects: list):
        entry = self.pending.setdefault(str(out), {'definition': definition, 'objects': {}})
        for obj in objects:
            key = self._field_value(obj, 'UUID') or self.gen_uuid()
            if key in entry['objects']:
                print(f'{Fore.YELLOW}[lsx] Duplicate UUID {key} in {definition["name"]}, keeping the last definition{Fore.RESET}')
            entry['objects'][key] = obj

    def flush(self) -> list[str]:
        """Write all collected tables. Returns written paths"""
        written = []
        for out, entry in self.pending.items():
            construct = {'stats': {'@stat_object_definition_id': entry['definition']['id'],
                                   'stat_objects': {'stat_object': list(entry['objects'].values())}}}
            self._write(construct, Path(out))
            written.append(out)
        self.pending = {}
        return written

    @staticmethod
    def _field_value(obj, name):
        for f in obj['fields']['field']:
            if f['@name'] == name:
                return f.get('@value')
        return None

    def build_table_objects(self, definition: dict) -> list:
        regions = as_list(self.data['save'].get('region'))
        region = next((r for r in regions if r.get('@id') == self.file_type), regions[0])
        roots = as_list(region.get('node'))
        nodes = []
        for root in roots:
            children = as_list((root.get('children') or {}).get('node'))
            nodes.extend(n for n in children if n.get('@id') == definition['export_name'])
            if not children and root.get('@id') == definition['export_name']:
                nodes.append(root)

        objects = []
        used_names = set()
        for i, node in enumerate(nodes):
            fields = self.build_fields(definition, node, i, used_names)
            objects.append({'@is_substat': 'false', 'fields': {'field': fields}})
        return objects

    def build_fields(self, definition: dict, node: dict, index: int, used_names: set) -> list:
        attributes = {a['@id']: a for a in as_list(node.get('attribute'))}
        children = {}
        for child in as_list((node.get('children') or {}).get('node')):
            children.setdefault(child['@id'], []).append(child)

        fields = []
        for fd in definition['fields']:
            typ = fd['type']
            if typ == 'NameTableFieldDefinition':
                fields.append(self.build_name(fd, attributes, index, used_names))
                continue
            if typ == 'IdTableFieldDefinition':
                value = attributes.get(fd['export_name'], {}).get('@value') or self.gen_uuid()
                fields.append({'@name': fd['name'], '@type': typ, '@value': value})
                continue
            if typ == 'ModifierTableFieldDefinition':
                field = self.build_modifier(fd, children)
            elif typ == 'ModifierListTableFieldDefinition':
                field = self.build_modifier_list(fd, children)
            elif fd.get('item') or fd.get('category'):
                field = self.build_list(fd, children)
            else:
                field = self.build_attribute(fd, attributes.get(fd['export_name']))
            if field is not None:
                fields.append(field)
        return fields

    def build_name(self, fd, attributes, index, used_names):
        value = attributes.get(fd['export_name'], {}).get('@value', '')
        # Internal names are only used by the editor and need to be unique
        if fd.get('internal') == 'true' or not value:
            base = value or 'New_Stat'
            value = base if base not in used_names else f'{base}_{index}'
            while value in used_names:
                value = f'{value}_{index}'
        used_names.add(value)
        return {'@name': fd['name'], '@type': fd['type'], '@value': value}

    def build_attribute(self, fd: dict, attribute: dict):
        if attribute is None:
            return None
        typ = fd['type']
        field = {'@name': fd['name'], '@type': typ}
        if typ == 'TranslatedStringTableFieldDefinition':
            handle = attribute.get('@handle')
            if handle is None:
                return None
            field['@handle'] = handle
            # Locale versions are reset to 1 by FixLocale
            field['@version'] = '1'
            return field
        value = attribute.get('@value', '')
        if typ in ('EnumerationTableFieldDefinition', 'EnumerationListTableFieldDefinition'):
            return self.build_enum(fd, value)
        if typ == 'FloatTableFieldDefinition' and attribute.get('@type') in ('double', 'float'):
            value = self.format_float(value, attribute.get('@type'))
        field['@value'] = value
        return field

    def build_enum(self, fd: dict, values):
        enum_name = fd.get('enum', fd['name'])
        # Tables store enumerations by index (the toolkit also reads labels), lsx files may use either
        labels = {label: index for index, label in self.schema.get('Enums', {}).get(enum_name, {}).items()}
        mapped = [labels.get(v, v) for value in as_list(values) for v in str(value).split(';') if v != '']
        return {'@name': fd['name'], '@type': fd['type'], '@value': ';'.join(mapped),
                '@enumeration_type_name': enum_name, '@version': '1'}

    def build_list(self, fd: dict, children: dict):
        nodes = []
        if fd.get('category'):
            for cat in children.get(fd['category'], []):
                for child in as_list((cat.get('children') or {}).get('node')):
                    if not fd.get('item') or child['@id'] == fd['item']:
                        nodes.append(child)
        else:
            nodes = children.get(fd['item'], [])

        values = []
        for n in nodes:
            attributes = {a['@id']: a.get('@value', '') for a in as_list(n.get('attribute'))}
            if fd['type'] == 'ReactionObjectListTableFieldDefinition':
                values.append(f"{attributes.get('id', '')},{attributes.get('value', '')}")
            elif fd['export_name'] in attributes:
                values.append(attributes[fd['export_name']])
            elif 'Name' in attributes:
                # Enumeration lists are stored as <node><attribute id="Name"/></node>
                values.append(attributes['Name'])
        if not values:
            return None
        if fd['type'] in ('EnumerationTableFieldDefinition', 'EnumerationListTableFieldDefinition'):
            return self.build_enum(fd, values)
        return {'@name': fd['name'], '@type': fd['type'], '@value': ';'.join(values)}

    @staticmethod
    def format_float(value: str, lsx_type: str) -> str:
        # lsx floats carry precision noise (0.40000000000000002, -0.30000001)
        try:
            return ('%.7g' if lsx_type == 'float' else '%.15g') % float(value)
        except ValueError:
            return value

    @staticmethod
    def _modifier(node):
        attribute_type, attribute_value = '', ''
        for a in as_list(node.get('attribute')):
            if a['@id'] == 'type':
                attribute_type = a['@value']
            elif a['@id'] in ['Name', 'Object', 'value']:
                attribute_value = a['@value']
        return {'@value': attribute_value, '@type': map_modifier_type(attribute_type)}

    def build_modifier(self, fd, children):
        nodes = children.get(fd['export_name'], [])
        if not nodes:
            return None
        return {'@name': fd['name'], '@type': fd['type'], 'modifier': self._modifier(nodes[0])}

    def build_modifier_list(self, fd, children):
        nodes = children.get(fd.get('item') or fd['export_name'], [])
        if not nodes:
            return None
        return {'@name': fd['name'], '@type': fd['type'], 'value': {'modifier': [self._modifier(n) for n in nodes]}}
    # endregion

    def build_mei_file(self):
        root = as_list(self.data['save']['region'])[0]['node']
        uuid = ""
        name = ""
        for attribute in as_list(root.get('attribute')):
            if attribute['@id'] == "UUID":
                uuid = attribute['@value']
            elif attribute['@id'] == "Name":
                name = attribute['@value']

        # Same layout the toolkit writes: EffectInfo elements directly below MultiEffectInfos
        effects = [self.build_mei_effect(e) for e in as_list((root.get('children') or {}).get('node'))]
        construct = {'MultiEffectInfos': {'@UUID': uuid, '@OwnerUUID': "00000000-0000-0000-0000-000000000000",
                                          '@Name': name}}
        if effects:
            construct['MultiEffectInfos']['EffectInfo'] = effects
        return construct

    def build_mei_effect(self, effect_info):
        mei_effect = {}
        for attribute in as_list(effect_info.get('attribute')):
            value = attribute.get('@value', '')
            if attribute['@type'] == "bool":
                value = str(value).lower()
            mei_effect[f'@{attribute["@id"]}'] = value
        for node in as_list((effect_info.get('children') or {}).get('node')):
            multi_id = f'@{node["@id"]}'
            value = as_list(node.get('attribute'))[0].get('@value', '') if node.get('attribute') else ''
            if multi_id not in mei_effect:
                mei_effect[multi_id] = value
            else:
                mei_effect[multi_id] = ", ".join([mei_effect[multi_id], value])
        return mei_effect

    # Check if name or file is of guid type
    def is_file_guid(self, file):
        return is_guid(file)

    def gen_uuid(self) -> str:
        return str(uuid.uuid4())

    # Convert to LSF (Modified from BG3ModdingTools)
    def lsx2lsf(self, file=None, verbose=True, lsfx=False, output=None):
        if file is None:
            file = self.file

        file_path = Path(file)
        if output is None:
            output = file_path.with_name(strip_suffixes(file_path.name) + ('.lsfx' if lsfx else '.lsf'))
        output = Path(output)
        if output.exists():
            os.remove(output)

        self.lslib_util.convert_file(file_path, output)

        if verbose:
            print(f'{Fore.GREEN}[info] Converted {os.path.basename(file)} (Converted to LSF){Fore.RESET}')
        return True
