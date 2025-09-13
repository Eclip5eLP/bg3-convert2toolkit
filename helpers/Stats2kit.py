import json
import os
import uuid
from pathlib import Path

import xmltodict
from colorama import Fore


class StatsConvert():
    data = None
    file = None
    uuid = None
    db = None
    auxdb = None
    root_path = None

    # Init
    def __init__(self, db=None, auxdb=None, root_path: Path = None):
        self.db = db
        self.auxdb = auxdb
        self.root_path = root_path

    def setUUID(self, uuid=None):
        self.uuid = uuid

    # Main call convert function
    def convert(self, file):
        self.file = file
        with open(file, encoding="utf-8-sig") as f:
            self.data = f.read()
        return self.writexml(self.convert_all())

    # Write data to xml file
    def writexml(self, data, file = None):
        if file is None:
            file = self.file
        if data is None:
            return False
        out = file.replace('.txt', '.stats').replace('Spell_', '')
        with open(out, 'w') as f:
            f.write(xmltodict.unparse(data, pretty=True, indent='  '))
        return True

    # Convert function logic
    def convert_all(self):
        if self.uuid is None:
            nodeUUID = ''
        else:
            nodeUUID = self.uuid
        if self.auxdb is None:
            self.auxdb = {}

        construct = {'stats': {'@stat_object_definition_id': nodeUUID, 'stat_objects': {'stat_object': []}}}
        auxIDfix = {}

        # Special handling for awesome treasure tables
        if self.data.startswith(("treasure", "new treasuretable")):
            self.process_treasure_table(construct)
        else: # All other files
            # Read line by line
            t = []
            i = 0
            dupes = []

            for line in self.data.split("\n"):
                i += 1
                raw = line.split('"')[1::2]

                if len(raw) > 0: # Ignore duplicate entries
                    if raw[0] in dupes:
                        continue
                    dupes.append(raw[0])
                if line[:3:] == "new": # Data definition entries
                    if len(t) > 0: # Data seperation
                        if not (not t):
                            construct['stats']['stat_objects']['stat_object'].append({'@is_substat': 'false', 'fields': {'field': t}})
                        t = []
                        i = 0
                    dupes = []
                    newUID = self.gen_uuid()
                    stat_name = raw[0]
                    if os.path.basename(self.file).startswith("Spell_"):
                        stat_name = raw[0].removeprefix(f'{os.path.basename(self.file).split(".")[0].replace("Spell_","")}_')

                    fname, fext = os.path.splitext(os.path.basename(self.file).replace("Spell_",""))
                    if fname == "Projectile" or fname == "Target" or fname == "Zone" or fname == "Shout" or fname == "ProjectileStrike" or fname == "Rush" or fname == "Teleportation" or fname == "Throw":
                        auxIDfix[f'{fname}_{stat_name}'] = newUID
                    else:
                        auxIDfix[stat_name] = newUID

                    t.append({'@name': 'UUID', '@type': 'IdTableFieldDefinition', '@value': newUID})
                    t.append({'@name': 'Name', '@type': 'NameTableFieldDefinition', '@value': stat_name})
                    continue
                if line[:5:] == "using": # Skip parent if IDs not in aux db
                    t.append({'@name': 'Using', '@type': 'BaseClassTableFieldDefinition', '@value': self.auxdb.get(raw[0],raw[0])})
                    continue
                if line[:4:] == "data": # Data entries
                    builder = self.gen_dict(raw)
                    if not builder is None:
                        t.append(builder)
                    continue
                # if line == '': # Data seperator
                #     if not (not t):
                #         construct['stats']['stat_objects']['stat_object'].append({'@is_substat': 'false', 'fields': {'field': t}})
                #     t = []
                #     i = 0
                #     dupes = []
            # Append current construct if file did not end on an empty line
            if i != 0:
                if not (not t):
                    construct['stats']['stat_objects']['stat_object'].append({'@is_substat': 'false', 'fields': {'field': t}})
                t = []
                i = 0
                dupes = []

        # Try fixing parent IDs
        isRecovered = True
        for i, x in enumerate(construct['stats']['stat_objects']['stat_object']):
            for y, val in enumerate(x['fields']['field']):
                if val['@name'] == 'Using' and not self.is_guid(val['@value']):
                    construct['stats']['stat_objects']['stat_object'][i]['fields']['field'][y]['@value'] = auxIDfix.get(val['@value'],'')
                    if construct['stats']['stat_objects']['stat_object'][i]['fields']['field'][y]['@value'] == '':
                        isRecovered = False
        if not isRecovered:
            print(f'{Fore.YELLOW}[stats] Missing parent entries in: {os.path.basename(self.file)}{Fore.WHITE}')
        with open(self.root_path / 'auxdb_self_recovered.temp', 'w') as f:
            f.write(json.dumps(auxIDfix, indent=4))
        return construct

    # Generate xml object to construct entry data
    def gen_dict(self, data, legacy = False):
        fname, fext = os.path.splitext(os.path.basename(self.file).replace("Spell_",""))
        try:
            builder = {'@name': data[0], '@type': self.db['DataTypes'].get(data[0], ''), '@value':''}
            if fname == 'Interrupt': # Hardcoded Properties checks
                if data[0] == 'Properties':
                    builder['@type'] = 'StringTableFieldDefinition'
                if data[0] == 'EnableContext':
                    data[0] = 'EnabledContext'
                    builder['@name'] = data[0]
                if data[0] == 'EnableCondition':
                    data[0] = 'EnabledConditions'
                    builder['@name'] = data[0]
            if self.db['DataTypes'].get(data[0], '') == "TranslatedStringTableFieldDefinition": # Translated entries
                builder['@handle'] = data[1].split(";")[0]
                builder['@version'] = "1"
            else: # All normal entries
                if data[1] == "":
                    builder['@value'] = ""
                    builder['@clear_inherited_value'] = "true"
                if builder['@value'] == '':
                    builder['@value'] = data[1]
            if self.db['DataTypes'].get(data[0], '') == '':
                if not data[0] in ['SpellType', 'StatusType']:
                    print(f'{Fore.YELLOW}[stats] Missing Pre-Configured Data Type: {data[0]}{Fore.WHITE}')
            if self.db['DataTypes'].get(data[0], '') == "EnumerationListTableFieldDefinition" or self.db['DataTypes'].get(data[0], '') == "EnumerationTableFieldDefinition": # Enum types
                # Special handling for status/spell sheathing fields named the same but different enums
                if fname.startswith('Status_') and data[0] == 'Sheathing':
                    enum_type_lookup = f'{data[0]}_Status'
                else:
                    enum_type_lookup = data[0]
                builder['@enumeration_type_name'] = self.db['DataTypes']['EnumTypes'].get(enum_type_lookup, enum_type_lookup)

                builder['@version'] = "1"
                if not builder['@value'] == '':
                    val = self.db['DataTypes']['EnumSubTypes'].get(builder['@enumeration_type_name'], builder['@value'])
                    if isinstance(val, dict):
                        builder['@value'] = val.get(builder['@value'], builder['@value'])
            if self.db['DataTypes'].get(data[0], '') == "BoolTableFieldDefinition":
                if not builder['@value'] == '':
                    val = self.db['DataTypes']['EnumSubTypes'].get('BoolTableFieldDefinition', builder['@value'])
                    if isinstance(val, dict):
                        builder['@value'] = val.get(builder['@value'], builder['@value'])
            return builder
        except Exception as e:
            print(f'[stats] Exception: {e}; Ignored')
            return None

    # Generate a new UUID
    def gen_uuid(self) -> str:
        return str(uuid.uuid4())

    # Check if a given string is a valid GUID
    def is_guid(self, val):
        if len(val) == 36 and val[8:9:] == "-" and val[13:14:] == "-" and val[18:19:] == "-" and val[23:24:] == "-":
            return True
        return False

    # Convert treasure table logic
    def process_treasure_table(self, construct: dict):
        t = []
        has_subtable = False
        base_table_uuid = ""
        base_table_name = ""
        is_substat = 'false'

        for line in self.data.split("\n"):
            tokens = line.split(" ")

            # Skip
            if line == '' or line.startswith("treasure"):
                continue

            # If we have data and a new table or secondary subtable, output field to main dictionary
            if not (not t) and (line.startswith("new treasuretable") or line.startswith("new subtable") and has_subtable):
                construct['stats']['stat_objects']['stat_object'].append({'@is_substat': is_substat, 'fields': {'field': t}})
                t = []
                is_substat = 'false'
                if line.startswith("new subtable"):
                    is_substat = 'true'

            # Initialize new field section for new table
            if line.startswith("new treasuretable"):
                has_subtable = False
                base_table_uuid = self.gen_uuid()
                base_table_name = tokens[2].strip('"')
                t.append({'@name': 'UUID', '@type': 'IdTableFieldDefinition', '@value': base_table_uuid})
                t.append({'@name': 'Name', '@type': 'NameTableFieldDefinition', '@value': base_table_name})
                continue

            if line.startswith("new subtable"):
                if has_subtable:
                    builder = self.gen_dict(["Using", base_table_uuid])
                    if not builder is None:
                        t.append(builder)
                    t.append({'@name': 'UUID', '@type': 'IdTableFieldDefinition', '@value': self.gen_uuid()})
                    t.append({'@name': 'Name', '@type': 'NameTableFieldDefinition', '@value': str(base_table_name + '_substat')})
                else:
                    has_subtable = True

                builder = self.gen_dict(["DropCount", tokens[2].strip('"')])
                if not builder is None:
                    t.append(builder)
                continue

            if line.startswith("object category"):
                fields = tokens[2].strip('"').split(',')
                builder = self.gen_dict(["ObjectCategory", fields[0].strip('"')])
                if not builder is None:
                    t.append(builder)
                builder = self.gen_dict(["Frequency", fields[1].strip('"')])
                if not builder is None:
                    t.append(builder)
                continue

            if line.startswith(("MinLevel", "MaxLevel", "StartLevel", "EndLevel", "CanMerge")):
                field_name = tokens[0]
                field_value = tokens[1].strip('"')
                if field_name == "MinLevel" or field_name == "MaxLevel":
                    field_name = str(field_name + 'Diff')
                elif field_name == "CanMerge":
                    if field_value == '1':
                        field_value = 'Yes'
                    else:
                        field_value = 'No'
                builder = self.gen_dict([field_name, field_value])
                if not builder is None:
                    t.append(builder)
                continue

        if not (not t):
            construct['stats']['stat_objects']['stat_object'].append({'@is_substat': is_substat, 'fields': {'field': t}})
