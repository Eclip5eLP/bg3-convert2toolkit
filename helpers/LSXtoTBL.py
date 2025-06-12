import json
import os
import sys
import uuid
from pathlib import Path

import xmltodict
from colorama import Fore


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


class LSXconvert():
    data = None
    file = None
    uuid = None
    db = None
    auxIDfix = None
    lslib_path = None
    root_path = None

    lsf_types = ['Templates', 'SkeletonBank', 'MaterialBank', 'TextureBank', 'VisualBank', 'EffectBank', 'Tags',
                 'MultiEffectInfos', 'CharacterVisualBank', 'Material', 'MaterialPresetBank', 'PhysicsBank']

    # with open('db.json', encoding="utf-8") as f:
    #     backup_db = json.load(f)

    lastName = ''

    # Init
    def __init__(self, db = None, lslib_path = None, root_path: Path = None):
        self.file_type = None
        self.db = db
        self.lslib_path = lslib_path
        self.root_path = root_path

    def setUUID(self, uuid = None):
        self.uuid = uuid

    # Main call convert function
    def convert(self, file):
        self.file = file
        self.readxml(file)
        converted_data, file_path, source_ext, dest_ext = self.convert_all()
        return self.writexml(converted_data, file_path, source_ext, dest_ext)
    
    # Read data from xml file
    def readxml(self, file):
        self.file = file
        with open(file, 'r+b') as f:
            self.data = xmltodict.parse(f.read())
        return self.data

    # Write data to xml file
    def writexml(self, data, file = None, source_ext = '.lsx', dest_ext = '.tbl'):
        if file is None:
            file = self.file
        if data is None:
            return False
        if source_ext is None:
            source_ext = '.lsx'
        if dest_ext is None:
            dest_ext = '.tbl'
        out = file.replace(source_ext, dest_ext)
        with open(out, 'w', encoding="utf-8") as f:
            f.write(xmltodict.unparse(data, pretty=True, indent='  '))
        return True

    # Convert function logic
    def convert_all(self):
        # Get data type
        self.file_type = self.getDataType()

        # Ignore Texture Atlas
        if self.file_type in ['IconUVList', 'TextureAtlasInfo']:
            print(f'{Fore.YELLOW}[info] Skipped file: {os.path.basename(self.file)} (Reason: Texture atlas doesnt need conversion){Fore.WHITE}')
            return None, None, None, None

        # Convert VFX (lsfx.lsx to lsfx)
        if self.file_type in ['Effect','Dependencies']:
            print(f'{Fore.YELLOW}[info] Convert file to lsfx: {os.path.basename(self.file)} (Reason: VFX to lsefx not yet supported){Fore.WHITE}')
            self.lsx2lsf(lsfx=True)
            # TODO: add conversion to lsefx and return
            return None, None, None, None

        # Convert Visual Resource or Templates to LSF
        if self.file_type in self.lsf_types:
            self.lsx2lsf()
            # Convert to .mei file
            if self.file_type == 'MultiEffectInfos':
                base_file = self.file.replace('.lsx', '')
                if not base_file.endswith('.lsf'):
                    base_file = base_file + '.lsf'
                return self.build_mei_file(), base_file, '.lsf', '.mei'
            return None, None, None, None

        # Override uuid
        if self.uuid is None:
            nodeUUID = ''
        else:
            nodeUUID = self.db['LSX'].get(self.file_type, self.uuid)
            if nodeUUID != self.uuid:
                print(f"{Fore.YELLOW}[lsx] ID Override for {os.path.basename(self.file)}: {nodeUUID} ({self.data['save']['region'].get('@id', None)}){Fore.WHITE}")

        construct = {'stats': {'@stat_object_definition_id': nodeUUID, 'stat_objects': {'stat_object': []}}}

        try: # Try adding recovered entries to auxiliary db
            with open(self.root_path / 'auxdb_self_recovered.temp', encoding="utf-8") as f:
                self.auxIDfix = json.load(f)
        except Exception as e:
            self.auxIDfix = {}

        root = self.data['save']['region']['node']['children']['node']
        for x in root: # loop every node in root
            if isinstance(x, str): # root only contains 1 node
                t = self.loop_elements(root)
                construct['stats']['stat_objects']['stat_object'].append({'@is_substat': 'false', 'fields': {'field': t}})
                break
            else: # construct xml node
                t = self.loop_elements(x)
            construct['stats']['stat_objects']['stat_object'].append({'@is_substat': 'false', 'fields': {'field': t}})
        return construct, None, None, None

    # Loop all elements in node
    def loop_elements(self, elem):
        t = []
        for akey, aval in elem.items():
            t = self.loop_builder(t, akey, aval)

        if self.lastName == '':
            self.lastName = self.gen_uuid()
        if not self.node_has_entry(t, 'NameFS'):
            t.append({'@name':'NameFS','@type':'FixedStringTableFieldDefinition','@value':self.lastName})
        if not self.node_has_entry(t, 'Name'):
            t.append({'@name':'Name','@type':'NameTableFieldDefinition','@value':self.lastName})
        self.lastName = ''
        return t

    def loop_builder(self, t, akey, aval, lnode=None):
        if akey == 'attribute': # Add attribute to builder
            for node in aval:
                t.append(self.gen_dict(node))
        elif akey == 'children': # Combine children and add to builder
            builder = {}
            if isinstance(aval['node'], list): # 1 layer
                chk_node = aval['node']
            elif not aval['node'].get('children', None) is None: # Multilayer
                for xkey, xval in aval['node']['children'].items():
                    for ax in xval:
                        ax['@id'] = aval['node'].get('@id', None)
                        if builder.get(ax['@id'], None) is None:
                            builder[ax['@id']] = {'@name': ax['@id'], '@type': self.gen_dict_keytype(ax['@id']), '@value': f'{ax["attribute"]["@value"]}'}
                        else:
                            builder[ax['@id']]['@value'] = f'{builder[ax["@id"]]["@value"]};{ax["attribute"]["@value"]}'
                    for ax, bx in builder.items():
                        t.append(bx)
                return t
            else: # 1 layer but only one node
                chk_node = [aval['node']]

            for ax in chk_node:
                if not ax.get('children', None) is None:
                    t = self.loop_builder(t, ax['@id'], 'children', ax['children'])
                    continue
                if builder.get(ax['@id'], None) is None:
                    tbl_type = self.gen_dict_keytype(ax['@id'])
                    attribute_type, attribute_value = self.get_type_value(ax)

                    if tbl_type == "ModifierTableFieldDefinition":
                        attribute_type = map_modifier_type(attribute_type)
                        builder[ax['@id']] = {'@name': ax['@id'], '@type': self.gen_dict_keytype(ax['@id']), 'modifier': {'@value': attribute_value, '@type': attribute_type}}
                    elif tbl_type == "EnumerationListTableFieldDefinition":
                        pass
                    else:
                        builder[ax['@id']] = {'@name': ax['@id'], '@type': self.gen_dict_keytype(ax['@id']), '@value': attribute_value}

                else:
                    builder[ax['@id']]['@value'] = f'{builder[ax["@id"]]["@value"]};{ax["attribute"]["@value"]}'
            for ax, bx in builder.items():
                t.append(bx)
        elif self.file_type == 'Rulebook' and aval == 'children':
            if akey == 'AbilityChanges':
                abilities_data = self.node_get_entry(t, 'Abilities')

                if not abilities_data:
                    abilities_data = {'@name':'Abilities', '@type':self.gen_dict_keytype('Abilities'), 'value': {'modifier': []}}
                    t.append(abilities_data)

                attribute_type, attribute_value = self.get_type_value(lnode['node'])
                attribute_type = map_modifier_type(attribute_type)
                abilities_data['value']['modifier'].append({'@value': attribute_value, '@type': attribute_type})
            else:
                # :-(
                if akey == 'ActionsCapabilities':
                    akey = 'ActionCapabilities'

                node_type = self.gen_dict_keytype(akey)
                if isinstance(lnode['node'], list):
                    items = lnode['node']
                else:
                    items = [lnode['node']]

                value_list = []
                for item in items:
                    value_list.append(item['attribute']['@value'])

                t.append({'@name':akey, '@type':node_type, '@enumeration_type_name':self.db['DataTypes']['EnumTypes'].get(akey), '@version': '1', '@value':";".join(value_list)})

        return t

    def get_type_value(self, attributes):
        if isinstance(attributes["attribute"], list):
            attributes = attributes["attribute"]
        else:
            attributes = [attributes["attribute"]]
        attribute_type = ""
        attribute_value = ""
        for attribute in attributes:
            if attribute['@id'] == "type":
                attribute_type = attribute['@value']
            elif attribute['@id'] in ["Name", "Object", "value"]:
                attribute_value = attribute['@value']
        return attribute_type, attribute_value

    # Generate dict lsx node from xml node
    def gen_dict(self, node):
        fname, fext = os.path.splitext(os.path.basename(self.file))
        try:
            ndict = {}

            # Attach values to keys
            for key, val in node.items():
                if key == '@id':
                    # Hardcoded lsx name fixes
                    if self.file_type == 'DefaultValues':
                        if val == 'TableUUID':
                            val = 'ProgressionUUID'
                        if val == 'OriginUUID':
                            val = 'Origin'
                        if val == 'Add' and fname != 'Spells':
                            val = 'DefaultValues'
                    if fname == 'ClassDescriptions' and val == 'ParentGuid':
                        val = 'ParentUUID'
                    if fname == 'Rulebook':
                        # Larian please, I beg you...
                        if val == 'ChangeScript':
                            val = 'ScriptName'

                    ndict['@name'] = val
                    continue
                if key == '@type':
                    ndict[key] = self.gen_dict_keytype(ndict.get('@name', None), ndict.get('@name', None))
                    continue
                if key == '@value' and ndict.get('@type', None) == 'TranslatedStringTableFieldDefinition':
                    ndict['@handle'] = val
                    ndict['@version'] = '1'
                    continue

                # Enum specific fields
                if ndict.get('@type', None) == 'EnumerationTableFieldDefinition' or ndict.get('@type', None) == 'EnumerationListTableFieldDefinition':
                    ndict['@version'] = '1'
                    ndict['@enumeration_type_name'] = self.db['DataTypes']['EnumTypes'].get(ndict.get('@name', None), ndict.get('@name', None))
                    val = self.db['DataTypes']['EnumSubTypes'].get(ndict.get('@name', None), {})
                    if isinstance(val, dict):
                        ndict['@value'] = val.get(node['@value'], node['@value'])
                    else:
                        ndict['@value'] = node['@value']

                if ndict.get(key, None) is None:
                    if key == '@value' and ndict['@name'] == 'Name':
                        self.lastName = val
                    ndict[key] = val
            return ndict
        except Exception as e:
            print(f'[lsx] Exception: {e}; Ignored')

    # Translate lsx node type to tbl type
    def gen_dict_keytype(self, key = None, val = None):
        fname, fext = os.path.splitext(os.path.basename(self.file))
        dtype = self.db['DataTypes'].get(key, '')

        # Hardcoded lsx type fixes
        if dtype == 'IntegerTableFieldDefinition' and fname == 'Progressions':
            dtype = 'ByteTableFieldDefinition'
        if fname == 'ProgressionDescriptions' and val == 'Type':
            dtype = 'FixedStringTableFieldDefinition'
        if (fname == 'Spells' or fname == 'Abilities' or fname == 'Passives' or fname == 'Skills'):
            if val == 'SelectorId':
                dtype = 'StringTableFieldDefinition'
            if val == 'ClassUUID':
                dtype = 'GuidTableFieldDefinition'
        if self.file_type == 'CompanionPresets' and key == 'RootTemplate':
            dtype = 'GuidTableFieldDefinition'
        if self.file_type == 'Origins':
            if key == 'ClassUUID':
                dtype = 'GuidTableFieldDefinition'
            if key == 'Unique':
                dtype = 'BoolTableFieldDefinition'
        if self.file_type == 'Rulebook' and key in ['Weight', 'Hp', 'TemporaryHp', 'Scale']:
            dtype = 'ModifierTableFieldDefinition'
        if self.file_type == 'Rulebook' and key in ['Abilities']:
            dtype = 'ModifierListTableFieldDefinition'

        return dtype

    def build_mei_file(self):
        root = self.data['save']['region']['node']
        uuid = ""
        name = ""
        for attribute in root['attribute']:
            if attribute['@id'] == "UUID":
                uuid = attribute['@value']
            elif attribute['@id'] == "Name":
                name = attribute['@value']

        construct = {'MultiEffectInfos': {'@UUID': uuid, '@OwnerUUID': "00000000-0000-0000-0000-000000000000",
                                          '@Name': name, 'EffectInfos': {'EffectInfo': []}}}

        if isinstance(root['children']['node'], list):
            for effect_info in root['children']['node']:
                construct['MultiEffectInfos']['EffectInfos']['EffectInfo'].append(self.build_mei_effect(effect_info))
        else:
            construct['MultiEffectInfos']['EffectInfos']['EffectInfo'].append(self.build_mei_effect(root['children']['node']))

        return construct

    def build_mei_effect(self, effect_info):
        mei_effect = {}
        for attribute in effect_info['attribute']:
            value = attribute['@value']
            if attribute['@type'] == "bool":
                value = str(value).lower()
            mei_effect[f'@{attribute["@id"]}'] = value
        if 'children' in effect_info:
            if isinstance(effect_info['children']['node'], list):
                for node in effect_info['children']['node']:
                    multi_id = f'@{node["@id"]}'
                    if multi_id not in mei_effect:
                        mei_effect[multi_id] = node['attribute']['@value']
                    else:
                        mei_effect[multi_id] = ", ".join([mei_effect[multi_id], node['attribute']['@value']])
            else:
                multi_id = f"@{effect_info['children']['node']['@id']}"
                mei_effect[multi_id] = effect_info['children']['node']['attribute']['@value']
        return mei_effect

    # Check if name or file is of guid type
    def is_file_guid(self, file):
        if len(file) == 36 and file[8:9:] == "-" and file[13:14:] == "-" and file[18:19:] == "-" and file[23:24:] == "-":
            return True
        return False

    # Safe list get without crash
    def list_get(self, l, idx, default):
        try:
            return l[idx]
        except IndexError:
            return default

    def gen_uuid(self) -> str:
        return str(uuid.uuid4())

    # Check if node contains element
    def node_has_entry(self, node, entry):
        try:
            for x in node:
                if x.get('@name', None) == entry:
                    return True
            return False
        except Exception:
            return False

    # Get entry from node
    def node_get_entry(self, node, entry):
        try:
            for x in node:
                if x.get('@name', None) == entry:
                    return x
            return None
        except Exception:
            return None

    def getDataType(self, file = None):
        if not file is None:
            self.readxml(file)
        else:
            file = self.file
        fname, fext = os.path.splitext(os.path.basename(file))

        # Get data type
        if isinstance(self.data['save']['region'], list):
            return self.data['save']['region'][0].get('@id', fname)
        else:
            return self.data['save']['region'].get('@id', fname)

    # Convert to LSF (Modified from BG3ModdingTools)
    def lsx2lsf(self, file = None, verbose = True, lsfx = False):
        if file is None:
            file = self.file

        divine = Path(self.lslib_path)
        lslib_dll = divine.is_dir() and divine.joinpath("LSLib.dll") or divine.parent.joinpath("LSLib.dll")

        if not lslib_dll.exists():
            if verbose:
                print(f'{Fore.RED}[lsf] Cant convert {os.path.basename(file)} (LSLib not found){Fore.RESET}')
            return False

        # Setting up lslib dll for use
        import pythonnet
        pythonnet.load('coreclr')
        import clr
        if not str(lslib_dll.parent.absolute()) in sys.path:
            sys.path.append(str(lslib_dll.parent.absolute()))
        clr.AddReference("LSLib")  # type: ignore
        from LSLib.LS import ResourceUtils, ResourceConversionParameters, ResourceLoadParameters  # type: ignore
        from LSLib.LS.Enums import Game  # type: ignore

        load_params = ResourceLoadParameters.FromGameVersion(Game.BaldursGate3)
        conversion_params = ResourceConversionParameters.FromGameVersion(Game.BaldursGate3)

        file_path = Path(file)
        trimmed_file_path = file_path
        # Due to unpacking some files get multiple suffix, so trim duplicates
        while trimmed_file_path.suffix in {'.lsf', '.lsx'}:
            trimmed_file_path = trimmed_file_path.with_suffix('')
        if lsfx:
            output = trimmed_file_path.with_suffix(".lsfx")
        else:
            output = trimmed_file_path.with_suffix(".lsf")
        if output.exists():
            os.remove(output)

        input_str = str(file_path.absolute())
        output_str = str(output.absolute())
        
        out_format = ResourceUtils.ExtensionToResourceFormat(output_str)
        resource = ResourceUtils.LoadResource(input_str, load_params)
        ResourceUtils.SaveResource(resource, output_str, out_format, conversion_params)

        if verbose:
            print(f'{Fore.GREEN}[info] Converted {os.path.basename(self.file)} (Converted to LSF){Fore.RESET}')
        return True

# TODO: can this be removed?  not sure if it fully works
# Convert every lsx file in dir
if __name__ == "__main__":
    conv = LSXconvert()
    for file in Path('.').rglob('*.lsx'):
        try:
            conv.convert(str(file))
            print(f'Converted {file}')
        except Exception as e:
            print(f'Failed to convert {file}:\n\t{e}')
