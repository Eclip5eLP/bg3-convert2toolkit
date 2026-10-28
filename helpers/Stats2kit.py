import os
import re
import uuid
from pathlib import Path

import xmltodict
from colorama import Fore

SPELL_TYPES = ['Projectile', 'ProjectileStrike', 'Rush', 'Shout', 'Target', 'Teleportation', 'Throw', 'Wall', 'Zone']

# `type "..."` of entries mapped to their stats definition
ENTRY_TYPES = {
    'PassiveData': 'Passive',
    'InterruptData': 'Interrupt',
    'Armor': 'Armor',
    'Weapon': 'Weapon',
    'Character': 'Character',
    'Object': 'Object',
    'CriticalHitTypeData': 'CriticalHitTypes',
    'ObjectCategories': 'ObjectCategoriesItemComboPreviewData',
    'CraftingStations': 'CraftingStationsItemComboPreviewData',
}

# Data fields implied by the stats file the entry ends up in
IMPLIED_FIELDS = ['SpellType', 'StatusType']

LINE_NEW = re.compile(r'^new\s+(\w+)\s+"([^"]*)"')
LINE_QUOTED = re.compile(r'"([^"]*)"', re.S)
LINE_DATA = re.compile(r'^data\s+"([^"]*)"\s*(?:"(.*?)"?)?\s*$', re.S)
LINE_KEYWORD = re.compile(r'^\s*(new|data|type|using|add|key)\s')
STATS_HINT = re.compile(r'^\s*(new\s+(entry|equipment|treasuretable|spellset|ItemCombination|CraftingPreviewData)\b|key\s+")', re.M | re.I)


class StatEntry:
    def __init__(self, kind: str, name: str, file: Path):
        self.kind = kind
        self.name = name
        self.file = file
        self.type = None
        self.using = None
        self.data = {}  # last definition wins, like in game
        self.items = []  # equipment entries / spellset spells
        self.weapon_set = None
        self.lines = []  # raw lines (treasure tables)


def is_stats_file(file: Path) -> bool:
    """Sniff content, mods put stats in arbitrarily named txt files (and other txt files next to them)"""
    try:
        with open(file, encoding="utf-8-sig", errors="ignore") as f:
            return STATS_HINT.search(f.read()) is not None
    except OSError:
        return False


def stats_root(file: Path) -> Path:
    """Directory converted .stats files are written to (Public/<mod>/Stats/Generated or the file's own folder)"""
    parts = file.parts
    # All stats of a mod end up in the same files, wherever the txt files were placed
    for i in range(len(parts) - 3, -1, -1):
        if parts[i] in ('Public', 'Mods'):
            # Stats placed in Mods/<mod>/ are moved next to the ones in Public/<mod>/
            return Path(*parts[:i]) / 'Public' / parts[i + 1] / 'Stats' / 'Generated'
    for i in range(len(parts) - 1, 0, -1):
        if parts[i] == 'Generated' and parts[i - 1] == 'Stats':
            return Path(*parts[:i + 1])
    return file.parent


def is_guid(val) -> bool:
    return re.fullmatch(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', val or '') is not None


class StatsConvert:
    # Init
    def __init__(self, db=None, auxdb=None, root_path: Path = None):
        self.db = db or {}
        self.auxdb = auxdb or {}
        self.root_path = root_path
        self.schema = self.db.get('Schema', {}).get('Stats', {})
        self.enums = self.db.get('Schema', {}).get('StatEnums', {})

    # region Parsing
    def parse_file(self, file: Path) -> tuple[list[StatEntry], list[str]]:
        entries = []
        unsupported = []
        current = None
        with open(file, encoding="utf-8-sig") as f:
            lines = self.join_multiline(f.read().splitlines())

        for raw in lines:
            line = raw.strip()
            if line == '' or line.startswith('//'):
                continue
            quoted = LINE_QUOTED.findall(line)
            new = LINE_NEW.match(line)

            if new:
                kind = new.group(1)
                if kind == 'subtable' and current is not None and current.kind == 'treasuretable':
                    current.lines.append(line)
                    continue
                current = StatEntry(kind, new.group(2), file)
                entries.append(current)
                if kind == 'treasuretable':
                    current.lines.append(line)
                elif kind not in ('entry', 'equipment', 'spellset', 'ItemCombination', 'ItemCombinationResult', 'CraftingPreviewData'):
                    unsupported.append(kind)
                continue

            if line.startswith('key ') and len(quoted) >= 1:
                # Data.txt / XPData.txt: key "Name","Value"
                current = StatEntry('key', quoted[0], file)
                current.data['Value'] = quoted[1] if len(quoted) > 1 else ''
                entries.append(current)
                current = None
                continue

            if current is None:
                if not line.startswith('treasure itemtypes'):
                    unsupported.append(line.split(' ')[0])
                continue

            if current.kind == 'treasuretable':
                current.lines.append(line)
            elif line.startswith('type ') and quoted:
                current.type = quoted[0]
            elif line.startswith('using ') and quoted:
                current.using = quoted[0]
            elif line.startswith('data ') and quoted:
                # Tolerates a missing closing quote, like the game does
                data = LINE_DATA.match(line)
                if data:
                    current.data[data.group(1)] = data.group(2) or ''
                else:
                    current.data[quoted[0]] = quoted[1] if len(quoted) > 1 else ''
            elif line.startswith('add initialweaponset') and quoted:
                current.weapon_set = quoted[0]
            elif line.startswith('add equipmentgroup'):
                current.items.append([])
            elif line.startswith('add equipment entry') and quoted:
                if not current.items:
                    current.items.append([])
                current.items[-1].append(quoted[0])
            elif line.startswith('add spell') and quoted:
                current.items.append(quoted[0])
            else:
                unsupported.append(line.split(' ')[0])
        return entries, unsupported

    @staticmethod
    def join_multiline(lines: list[str]) -> list[str]:
        """Quoted values may span multiple lines, the toolkit keeps the line breaks"""
        joined = []
        buffer = None
        for line in lines:
            if buffer is not None:
                # A missing closing quote must not swallow the following entries
                if line.strip() == '' or LINE_KEYWORD.match(line):
                    joined.append(buffer)
                    buffer = None
                else:
                    buffer += '\r\n' + line
                    if line.count('"') % 2 == 1:
                        joined.append(buffer)
                        buffer = None
                    continue
            if line.strip().startswith('data ') and line.count('"') % 2 == 1 and not line.rstrip().endswith('"'):
                buffer = line
                continue
            joined.append(line)
        if buffer is not None:
            joined.append(buffer)
        return joined

    # region Definition resolution
    def resolve_definition(self, entry: StatEntry, by_name: dict, depth=0) -> str | None:
        file_stem = entry.file.stem
        if entry.kind == 'equipment':
            return 'Equipment'
        if entry.kind == 'spellset':
            return 'SpellSet'
        if entry.kind == 'treasuretable':
            return 'TreasureTable'
        if entry.kind in ('ItemCombination', 'ItemCombinationResult'):
            return 'ItemCombos'
        if entry.kind == 'key':
            return 'XPData' if 'XPData' in file_stem else 'Data'

        if entry.type == 'SpellData':
            spell_type = entry.data.get('SpellType') or self._inherited(entry, 'SpellType', by_name, depth)
            if spell_type is None and entry.using:
                prefix = entry.using.split('_')[0]
                spell_type = prefix if prefix in SPELL_TYPES else None
            if spell_type is None and file_stem.startswith('Spell_'):
                spell_type = file_stem.removeprefix('Spell_')
            if spell_type is None and entry.name.split('_')[0] in SPELL_TYPES:
                spell_type = entry.name.split('_')[0]
            return spell_type if spell_type in self.schema else None
        if entry.type == 'StatusData':
            status_type = entry.data.get('StatusType') or self._inherited(entry, 'StatusType', by_name, depth)
            if status_type is None and file_stem.startswith('Status_'):
                status_type = file_stem.removeprefix('Status_')
            key = f'Status_{status_type}'
            return key if key in self.schema else None
        if entry.type in ENTRY_TYPES:
            return ENTRY_TYPES[entry.type]
        # Unknown or missing type, fall back to the file name
        stem = file_stem.removeprefix('Spell_')
        return stem if stem in self.schema else None

    def _inherited(self, entry, key, by_name, depth):
        parent = by_name.get(entry.using) if entry.using else None
        if parent is None or depth > 32:
            return None
        return parent.data.get(key) or self._inherited(parent, key, by_name, depth + 1)
    # endregion

    # region Conversion
    def convert_group(self, files: list[Path], out_dir: Path) -> tuple[list[Path], list[Path]]:
        """
            Converts all stats txt files of one mod together, so entries are routed to the right
            definition no matter which file they were written in and parents resolve across files.

            :return: (written .stats files, txt files that were fully converted)
        """
        entries = []
        partially = set()
        for file in files:
            parsed, unsupported = self.parse_file(file)
            entries.extend(parsed)
            if unsupported:
                partially.add(file)
                kinds = ', '.join(sorted(set(unsupported)))
                print(f'{Fore.YELLOW}[stats] {file.name}: unsupported content kept as txt only ({kinds}){Fore.RESET}')

        by_name = {e.name: e for e in entries if e.kind == 'entry'}

        grouped = {}
        skipped = set()
        for entry in entries:
            definition = self.resolve_definition(entry, by_name)
            if definition is None:
                print(f'{Fore.YELLOW}[stats] Could not determine stats type of "{entry.name}" in {entry.file.name}{Fore.RESET}')
                skipped.add(entry.file)
                continue
            grouped.setdefault(definition, []).append(entry)

        # Assign IDs first so parents resolve regardless of order and file
        uuids = {}
        for definition, items in grouped.items():
            for entry in items:
                if entry.kind == 'ItemCombinationResult':
                    continue
                uuids[self.game_name(entry, definition)] = str(uuid.uuid4())

        written = []
        for definition, items in grouped.items():
            objects = self.build_objects(definition, items, uuids)
            if not objects:
                continue
            construct = {'stats': {'@stat_object_definition_id': self.db.get('Stats', {}).get(definition, self.schema[definition]['id']),
                                   'stat_objects': {'stat_object': objects}}}
            out = out_dir / f'{definition}.stats'
            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, 'w', encoding='utf-8') as f:
                f.write(xmltodict.unparse(construct, pretty=True, indent='  '))
            written.append(out)
            print(f'{Fore.GREEN}[info] Converted stats {definition} ({len(objects)} entries){Fore.RESET}')

        converted = [f for f in files if f not in partially and f not in skipped]
        return written, converted

    @staticmethod
    def game_name(entry: StatEntry, definition: str) -> str:
        return entry.name

    @staticmethod
    def editor_name(entry: StatEntry, definition: str) -> str:
        # The toolkit prefixes spells with their type when exporting
        if definition in SPELL_TYPES:
            if entry.name.startswith(f'{definition}_'):
                return entry.name.removeprefix(f'{definition}_')
            print(f'{Fore.YELLOW}[stats] Spell "{entry.name}" lacks the "{definition}_" prefix, the toolkit will export it as "{definition}_{entry.name}"{Fore.RESET}')
        return entry.name

    def build_objects(self, definition: str, items: list[StatEntry], uuids: dict) -> list:
        if definition == 'TreasureTable':
            objects = []
            for entry in items:
                objects.extend(self.build_treasure_table(entry))
            return objects

        # Later definitions of the same entry replace earlier ones, like in game
        merged = {}
        results = {}
        for entry in items:
            if entry.kind == 'ItemCombinationResult':
                results[re.sub(r'_\d+$', '', entry.name)] = entry
                continue
            if entry.name in merged:
                print(f'{Fore.YELLOW}[stats] "{entry.name}" is defined multiple times, keeping the last definition{Fore.RESET}')
            merged[entry.name] = entry

        objects = []
        for entry in merged.values():
            fields = [{'@name': 'UUID', '@type': 'IdTableFieldDefinition', '@value': uuids[entry.name]},
                      {'@name': 'Name', '@type': 'NameTableFieldDefinition', '@value': self.editor_name(entry, definition)}]
            if entry.using:
                fields.append(self.build_using(entry, uuids))

            if definition == 'Equipment':
                fields.extend(self.build_equipment(entry))
            elif definition == 'SpellSet':
                objects.extend(self.build_spellset(entry, fields))
                continue
            if entry.kind == 'CraftingPreviewData' and entry.type:
                fields.append({'@name': 'Type', '@type': self.field_type(definition, 'Type') or 'StringTableFieldDefinition', '@value': entry.type})
            data = dict(entry.data)
            if entry.kind == 'ItemCombination' and entry.name in results:
                data.update(results.pop(entry.name).data)
            for key, value in data.items():
                if key in IMPLIED_FIELDS:
                    continue
                field = self.gen_field(definition, key, value)
                if field is not None:
                    fields.append(field)
            objects.append({'@is_substat': 'false', 'fields': {'field': fields}})

        for name in results:
            print(f'{Fore.YELLOW}[stats] ItemCombinationResult for "{name}" has no matching ItemCombination{Fore.RESET}')
        return objects

    def build_using(self, entry: StatEntry, uuids: dict) -> dict:
        parent = uuids.get(entry.using) or self.auxdb.get(entry.using, '')
        if parent == '' and is_guid(entry.using):
            parent = entry.using
        if parent == '':
            print(f'{Fore.YELLOW}[stats] Missing parent "{entry.using}" of "{entry.name}" (compile the AuxDB or add the mod it comes from){Fore.RESET}')
        return {'@name': 'Using', '@type': 'BaseClassTableFieldDefinition', '@value': parent}

    def build_equipment(self, entry: StatEntry) -> list:
        fields = []
        if entry.weapon_set is not None:
            fields.append(self.gen_field('Equipment', 'InitialWeaponSet', entry.weapon_set))
        index = 0
        for group in entry.items:
            if len(group) > 1:
                print(f'{Fore.YELLOW}[stats] Equipment "{entry.name}" has an equipment group with multiple entries, they are added as separate items{Fore.RESET}')
            for item in group:
                index += 1
                fields.append({'@name': str(index), '@type': 'StatReferenceTableFieldDefinition', '@value': item})
        return fields

    def build_spellset(self, entry: StatEntry, fields: list) -> list:
        # First spell lives on the set itself, every other spell is a substat inheriting from it
        set_uuid = fields[0]['@value']
        spell_type = self.field_type('SpellSet', 'Spells')
        objects = []
        for i, spell in enumerate(entry.items or ['']):
            if i == 0:
                obj_fields = fields + ([{'@name': 'Spells', '@type': spell_type, '@value': spell}] if spell else [])
                objects.append({'@is_substat': 'false', 'fields': {'field': obj_fields}})
                continue
            objects.append({'@is_substat': 'true', 'fields': {'field': [
                {'@name': 'UUID', '@type': 'IdTableFieldDefinition', '@value': str(uuid.uuid4())},
                {'@name': 'Name', '@type': 'NameTableFieldDefinition', '@value': f'{entry.name}_substat_{i - 1}'},
                {'@name': 'Using', '@type': 'BaseClassTableFieldDefinition', '@value': set_uuid},
                {'@name': 'Spells', '@type': spell_type, '@value': spell},
            ]}})
        return objects

    def build_treasure_table(self, entry: StatEntry) -> list:
        """
            Treasure tables: the first subtable lives on the table itself, every further subtable and
            every further object category within a subtable becomes a substat inheriting from the table
        """
        base_uuid = str(uuid.uuid4())
        objects = []
        current = [{'@name': 'UUID', '@type': 'IdTableFieldDefinition', '@value': base_uuid},
                   {'@name': 'Name', '@type': 'NameTableFieldDefinition', '@value': entry.name}]
        is_substat = 'false'
        has_subtable = False
        has_category = False
        substat_index = 0

        def flush():
            objects.append({'@is_substat': is_substat, 'fields': {'field': list(current)}})

        def new_substat():
            nonlocal current, is_substat, substat_index
            flush()
            is_substat = 'true'
            current = [{'@name': 'UUID', '@type': 'IdTableFieldDefinition', '@value': str(uuid.uuid4())},
                       {'@name': 'Using', '@type': 'BaseClassTableFieldDefinition', '@value': base_uuid},
                       {'@name': 'Name', '@type': 'NameTableFieldDefinition', '@value': f'{entry.name}_substat_{substat_index}'}]
            substat_index += 1

        for line in entry.lines[1:]:
            quoted = LINE_QUOTED.findall(line)
            if line.startswith('new subtable'):
                if has_subtable:
                    new_substat()
                has_subtable = True
                has_category = False
                current.append(self.gen_field('TreasureTable', 'DropCount', quoted[0] if quoted else ''))
            elif line.startswith('object category'):
                if has_category:
                    new_substat()
                has_category = True
                values = line[len('object category'):].strip().split(',')
                current.append(self.gen_field('TreasureTable', 'ObjectCategory', values[0].strip().strip('"')))
                current.append(self.gen_field('TreasureTable', 'Frequency', values[1].strip() if len(values) > 1 else '1'))
            elif line.startswith('CanMerge'):
                value = (line.split(' ', 1)[1] if ' ' in line else '').strip().strip('"')
                current.append(self.gen_field('TreasureTable', 'CanMerge', 'Yes' if value == '1' else 'No'))
            else:
                key = line.split(' ', 1)[0]
                value = quoted[0] if quoted else (line.split(' ', 1)[1].strip() if ' ' in line else '')
                current.append(self.gen_field('TreasureTable', key, value))
        flush()
        return objects
    # endregion

    # region Fields
    @staticmethod
    def build_mesh_effect(builder: dict, value: str) -> dict:
        # FadeIn:0;FadeOut:0;V:[visuals];VI:[visual index per item];S:[skeleton per item]
        def guid(h):
            return f'{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}' if len(h) == 32 else h
        parts = {}
        for part in value.split(';'):
            if ':' in part:
                k, v = part.split(':', 1)
                parts[k] = v.strip('[]').split(',') if v.startswith('[') else v
        builder['@FadeIn'] = parts.get('FadeIn', '0')
        builder['@FadeOut'] = parts.get('FadeOut', '0')
        visuals, indices, skeletons = parts.get('V', []), parts.get('VI', []), parts.get('S', [])
        items = []
        for i, skeleton in enumerate(skeletons):
            idx = int(indices[i]) if i < len(indices) and indices[i].isdigit() else i
            visual = visuals[idx] if idx < len(visuals) else ''
            items.append({'@SkeletonResourceId': guid(skeleton), '@VisualResourceId': guid(visual)})
        if items:
            builder['MeshEffectItem'] = items
        return builder

    def schema_field(self, definition: str, key: str) -> dict | None:
        """Look up a field by the name used in txt files (export name) or its editor name"""
        fields = self.schema.get(definition, {}).get('fields', [])
        for fd in fields:
            if fd['export_name'] == key:
                return fd
        for fd in fields:
            if fd['name'] == key:
                return fd
        return None

    def field_type(self, definition: str, key: str) -> str:
        fd = self.schema_field(definition, key)
        if fd is not None:
            return fd['type']
        return self.db.get('DataTypes', {}).get(key, '')

    def gen_field(self, definition: str, key: str, value: str) -> dict | None:
        fd = self.schema_field(definition, key)
        if fd is not None:
            name, typ, enum = fd['name'], fd['type'], fd.get('enum')
        else:
            name, typ = key, self.db.get('DataTypes', {}).get(key, '')
            enum = self.db.get('DataTypes', {}).get('EnumTypes', {}).get(key)
            if typ == '':
                print(f'{Fore.YELLOW}[stats] Unknown field "{key}" for {definition}, written as string{Fore.RESET}')
                typ = 'StringTableFieldDefinition'

        builder = {'@name': name, '@type': typ}
        if typ in ('EnumerationTableFieldDefinition', 'EnumerationListTableFieldDefinition'):
            builder['@enumeration_type_name'] = enum or key
            builder['@version'] = '1'
        if value == '':
            if typ != 'TranslatedStringTableFieldDefinition':
                builder['@value'] = ''
            builder['@clear_inherited_value'] = 'true'
            return builder
        if typ == 'TranslatedStringTableFieldDefinition':
            # Locale versions are reset to 1 by FixLocale
            builder['@handle'] = value.split(';')[0]
            builder['@version'] = '1'
            return builder
        if typ == 'MeshEffectTableFieldDefinition':
            return self.build_mesh_effect(builder, value)

        if typ == 'BoolTableFieldDefinition':
            value = {'1': 'True', '0': 'False', 'true': 'True', 'false': 'False', 'Yes': 'True', 'No': 'False'}.get(value, value)
        elif typ == 'ShortNameTableFieldDefinition':
            # txt files append the display name: <uuid>(Name)
            value = re.sub(r'^([0-9a-fA-F-]{36})\(.*\)$', r'\1', value)
        builder['@value'] = value
        return builder
    # endregion
