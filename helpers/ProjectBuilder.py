import re
import shutil
import uuid
from pathlib import Path

from colorama import Fore

from helpers.LSXtoTBL import LSXconvert


class ProjectBuilder:
    data = None
    path_to_templates = None

    # Init
    def __init__(self, path_to_templates: Path, conv_lsx: LSXconvert = None):
        self.conv_lsx = conv_lsx
        self.path_to_templates = path_to_templates

    # Check if path is a workspace resembling a project
    def is_project(self, dirs):
        pdir = Path(dirs)
        if not pdir.exists() or not pdir.is_dir():
            return False
        structure = ['Public/','Mods/']
        for s in structure:
            if not Path(f'{dirs}/{s}').exists():
                return False
        return True

    # Build all saved projects
    def build_all(self, projects: list[Path], output_dir: Path, prompt: bool = False):
        for x in projects:
            self.build(x, output_dir, prompt)

    # Build a projects for use with Toolkit
    def build(self, source_path: Path, output_dir: Path, prompt: bool = False):
        project_root_name = source_path.name
        if not self.is_project(source_path):
            print(f'{Fore.YELLOW}[Project] {project_root_name} is not a valid project{Fore.RESET}')
            return False

        # Vars
        project_uuid = self.gen_uuid()
        project_name = ''.join(x for x in f'{project_root_name}_{project_uuid}' if x.isalnum() or x in ['_','-','(',')'])

        # Prompt user for input
        if prompt:
            print(f'{Fore.CYAN}[Project] Attempting to create Project \'{project_root_name}\'\nEnter Project name (type X to skip or leave empty to use default): {Fore.RESET}')
            name = input()
            if name == 'X' or name == 'x': # Skip
                return False
            name = ''.join(x for x in name if x.isalnum() or x in ['_','-','(',')'])
            if not name == '':
                project_name = f'{name}_{project_uuid}'
                project_root_name = name

        project_output_path = output_dir.joinpath(project_name)

        try:
            # Workspace structure and metadata
            structure = [f'Editor/Mods/{project_name}/',
                         f'Generated/Public/{project_name}/',
                         f'Public/{project_name}/RootTemplates/',
                         f'Public/{project_name}/Content/[PAK]_{project_root_name}/',
                         f'Mods/{project_name}/Localization/English/',
                         f'Mods/{project_name}/',
                         f'Mods/{project_name}/Scripts/',
                         f'Mods/{project_name}/GUI/',
                         f'Projects/{project_name}/']

            for sub_dir in structure:
                project_output_path.joinpath(sub_dir).mkdir(parents=True, exist_ok=True)
            self.createMeta(project_output_path, project_name, project_root_name, project_uuid)

            # Copy all files to the correct location
            for file in source_path.rglob('*'):
                if file.is_dir():
                    continue

                output_file_dir = str(file.parent.relative_to(source_path).as_posix() + '/')

                # Series of steps to convert output directory string
                output_file_dir = re.sub(r'^Public/.*?/', f'Public/{project_name}/', output_file_dir)
                output_file_dir = re.sub(r'^Generated/Public/.*?/', f'Generated/Public/{project_name}/', output_file_dir)
                output_file_dir = re.sub(r'^Mods/.*?/', f'Mods/{project_name}/', output_file_dir)

                # Change destination if table, stats, or mei file
                if file.suffix == '.tbl' or file.suffix == '.stats' or file.suffix == '.mei':
                    output_file_dir = re.sub(r'/Stats/Generated/(Data/)?', f'/Stats/', output_file_dir)
                    output_file_dir = output_file_dir.replace(f'Public/{project_name}/', f'Editor/Mods/{project_name}/')
                    output_file_dir = self.translate_structure(output_file_dir, file.name)

                # Fix destination if generated
                if 'Generated/' in output_file_dir and not 'Generated/Public/' in output_file_dir and not '/Stats/Generated/' in output_file_dir:
                    output_file_dir = output_file_dir.replace('Generated/', f'Generated/Public/{project_name}/')

                # Fix localization
                if output_file_dir.startswith('Localization/'):
                    output_file_dir = output_file_dir.replace('Localization/', f'Mods/{project_name}/Localization/')

                new_output_path = project_output_path.joinpath(output_file_dir)
                new_output_path.mkdir(parents=True, exist_ok=True)
                new_output_file = new_output_path.joinpath(file.name)
                new_output_file_str = str(new_output_file.as_posix())

                if not new_output_file.exists() and file.exists():
                    shutil.copy(str(file.as_posix()), new_output_file_str)

                # Edit paths if lsf file and re-convert
                try:
                    file_type = self.conv_lsx.getDataType(new_output_file_str)
                    if not file_type in self.conv_lsx.lsf_types and not file_type in ['IconUVList', 'TextureAtlasInfo']:
                        continue # Ignore all non lsf files

                    with open(new_output_file_str, 'r', encoding="utf-8") as f:
                        data = f.read()

                    # Visual Resource Generated Path
                    if file_type in self.conv_lsx.lsf_types:
                        try:
                            loc = re.search(r'Generated/.*?/', data).group().split('/')
                            if not loc[1] == 'Public':
                                data = data.replace('Generated/', f'Generated/Public/{project_name}/')
                            else:
                                data = data.replace('Generated/Public/', f'Generated/Public/{project_name}/')
                        except Exception as e:
                            pass # Ignore outlier files
                    # UI Resource Public Path
                    data = re.sub(r'(?!.*Public/Shared/Assets/)Public/.*?/Assets/', f'Public/{project_name}/Assets/', data)

                    with open(new_output_file_str, 'w', encoding="utf-8") as f:
                        f.write(data)

                    self.conv_lsx.lsx2lsf(new_output_file_str, False)
                except Exception as e:
                    continue # Failsafe

            # File Cleanup
            #TODO remove duplicate files, conversion leftovers or localization files

            print(f'{Fore.GREEN}[Project] Project {project_name} successfully created{Fore.RESET}')
            #raise Exception('Cleanup')
            return True
        except Exception as e:
            # Failed (failsafe catch)
            print(f'{Fore.RED}[Project] Failed to create project {project_root_name}\n\tReason: {e}{Fore.RESET}')
            if Path(project_output_path).exists():
                shutil.rmtree(project_output_path)
            return False

    # Create metadata
    def createMeta(self, pdir, pname, pname_raw, pguid):

        # Project Metadata
        with open(f'{self.path_to_templates}/project_meta.lsx', 'r', encoding="utf-8") as f:
            data = f.read()

        data = data.replace('$MODULE_ID', pguid)
        data = data.replace('$PROJECT_ID', self.gen_uuid())
        data = data.replace('$PROJECT_NAME', self.xmlesc(pname_raw))

        with open(f'{pdir}/Projects/{pname}/meta.lsx', 'w', encoding="utf-8") as f:
            f.write(data)

        # Mod Metadata
        with open(f'{self.path_to_templates}/mod_meta.lsx', 'r', encoding="utf-8") as f:
            data = f.read()

        data = data.replace('$MOD_FOLDER', self.xmlesc(pname))
        data = data.replace('$MOD_NAME', self.xmlesc(pname_raw))
        data = data.replace('$MOD_UUID', pguid)

        with open(f'{pdir}/Mods/{pname}/meta.lsx', 'w', encoding="utf-8") as f:
            f.write(data)

        return True

    # Generate a new UUID
    def gen_uuid(self) -> str:
        return str(uuid.uuid4())

    # Check if a given string is a valid GUID
    def is_guid(self, val):
        if len(val) == 36 and val[8:9:] == "-" and val[13:14:] == "-" and val[18:19:] == "-" and val[23:24:] == "-":
            return True
        return False

    # Escape string for xml
    def xmlesc(self, txt):
        table = str.maketrans({
            "<": "&lt;",
            ">": "&gt;",
            "&": "&amp;",
            "'": "&apos;",
            '"': "&quot;",
        })
        return txt.translate(table)

    # Translate lsx file structure to tbl
    def translate_structure(self, dirs, file):
        paths = {
            "/Stats/Generated/Data/": "/Stats/",
        }

        files = {
            "BloodTypes.stats": "/BloodTypes/",
            "CriticalHitTypes.stats": "/BloodTypes/",
            "Crimes.stats": "/Crimes/",
            "Equipment.stats": "/Equipment/",
            "Data.stats": "/ExtraData/",
            "Requirements.stats": "/ExtraData/",
            "XPData.stats": "/ExtraData/",
            "ItemColor.stats": "/ItemColor/",
            "CraftingStationsItemComboPreviewData.stats": "/ItemCombos/",
            "ItemComboProperties.stats": "/ItemCombos/",
            "ItemCombos.stats": "/ItemCombos/",
            "ObjectCategoriesItemComboPreviewData.stats": "/ItemCombos/",
            "ItemProgressionNames.stats": "/ItemProgression/",
            "ItemProgressionVisuals.stats": "/ItemProgression/",
            "ItemTypes.stats": "/ItemTypes/",
            "Projectile.stats": "/SpellData/",
            "ProjectileStrike.stats": "/SpellData/",
            "Rush.stats": "/SpellData/",
            "Shout.stats": "/SpellData/",
            "SpellSet.stats": "/SpellData/",
            "Target.stats": "/SpellData/",
            "Teleportation.stats": "/SpellData/",
            "Throw.stats": "/SpellData/",
            "Wall.stats": "/SpellData/",
            "Zone.stats": "/SpellData/",
            "Armor.stats": "/Stats/",
            "Character.stats": "/Stats/",
            "Interrupt.stats": "/Stats/",
            "Object.stats": "/Stats/",
            "Passive.stats": "/Stats/",
            "Weapon.stats": "/Stats/",
            "Status_BOOST.stats": "/StatusData/",
            "Status_DEACTIVATED.stats": "/StatusData/",
            "Status_DOWNED.stats": "/StatusData/",
            "Status_EFFECT.stats": "/StatusData/",
            "Status_FEAR.stats": "/StatusData/",
            "Status_HEAL.stats": "/StatusData/",
            "Status_INCAPACITATED.stats": "/StatusData/",
            "Status_INVISIBLE.stats": "/StatusData/",
            "Status_KNOCKED_DOWN.stats": "/StatusData/",
            "Status_POLYMORPHED.stats": "/StatusData/",
            "Status_SNEAKING.stats": "/StatusData/",
            "TreasureGroups.stats": "/TreasureTable/",
            "TreasureTable.stats": "/TreasureTable/",
        }

        for key, val in paths.items():
            dirs = dirs.replace(key, val)
        for key, val in files.items():
            if file == key:
                dirs = dirs.replace(f'/Stats/', f'/Stats/{val}')
        return dirs
