import json
from pathlib import Path

from colorama import Fore

from helpers.CompileDB import CompileDB
from helpers.FixLocale import FixLocale
from helpers.LSLibUtil import LSLibUtil
from helpers.LSXtoTBL import LSXconvert, strip_suffixes
from helpers.ProjectBuilder import ProjectBuilder, is_intermediate
from helpers.Stats2kit import StatsConvert, is_stats_file, stats_root, SPELL_TYPES

EXCLUSIONS = ['meta.lsx', 'metadata.lsf.lsx']


# Primary object for clients to call for conversion logic
class ConvertAPI:
    def __init__(self,
                 src_bg3_path: str,
                 path_to_root: Path,
                 path_to_templates: Path,
                 lslib_util: LSLibUtil,
                 compile_aux_db: bool = False):
        self.path_to_root = path_to_root
        self.lslib_util = lslib_util
        self.src_bg3_path = src_bg3_path
        self._aux_db = self._get_auxiliary_db(src_bg3_path, compile_aux_db)
        self._db = self._get_db()
        self._stats_converter = StatsConvert(self._db, self._aux_db, self.path_to_root)
        self._lsx_converter = LSXconvert(self._db, self.lslib_util, self.path_to_root)
        self._locale_fixer = FixLocale()
        stats_categories = {name: d['category'] for name, d in self._db.get('Schema', {}).get('Stats', {}).items()}
        self._proj_builder = ProjectBuilder(path_to_templates, self._lsx_converter, stats_categories)
        self._skip_files = set()

    #region Public functions
    def convert(self, source_path: Path, output_dir: Path, is_cli: bool = True):
        """
            Main entry point for basic conversion.
            1. Converts Stat txt files to .stats
            2. Converts lsx files to .tbl
            3. Checks for issues in locale files
            4. If source path conforms to project structure, re-structure to tk folders

        :param source_path: Location of files to convert
        :param output_dir: Location to output converted files
        :param is_cli: Flag to indicate if caller is command line or GUI
        """
        self._skip_files = set()
        self.prepare_binaries(source_path)
        self.convert_stat_files(source_path)
        self.convert_lsx_files(source_path)
        self.fix_locales(source_path)
        self.build_tk_project(source_path, output_dir, is_cli)

    @staticmethod
    def is_project_dir(source_path: Path) -> bool:
        return ProjectBuilder.is_project(source_path)

    def is_valid_source(self, source_path: Path) -> bool:
        return (source_path is not None
                and source_path.exists()
                and (source_path.is_dir() or self.is_pak(source_path)))

    @staticmethod
    def is_pak(source_path: Path) -> bool:
        return (source_path is not None
                and source_path.exists()
                and source_path.suffix.lower() == '.pak')

    def unpack_file(self, source_path: Path, output_path: Path):
        if not self.is_pak(source_path):
            print(f'{Fore.RED}[pak] Can\'t unpack {str(source_path)} (Not valid Pak file){Fore.RESET}')
            return

        if output_path is None or not output_path.is_dir():
            print(f'{Fore.RED}[pak] Can\'t unpack output to {str(output_path)} (Not valid dir){Fore.RESET}')
            return

        self._unpack_internal(source_path, output_path)

    def prepare_binaries(self, source_path: Path):
        """Create an editable lsx next to every binary resource that doesn't have one yet"""
        for file in list(source_path.rglob('*')):
            if (file.is_file() and self.lslib_util.is_lsx_family(file.suffix)
                    and not file.with_name(file.name + '.lsx').exists() and not self._in_output_project(file, source_path)):
                try:
                    self.lslib_util.convert_file(file, file.with_name(file.name + '.lsx'))
                except Exception as e:
                    print(f'{Fore.YELLOW}[info] Could not read binary {file.name}: {e}{Fore.RESET}')

    def convert_stat_files(self, source_path: Path):
        print(f'{Fore.CYAN}[main] Converting Stats files:{Fore.RESET}')
        groups = {}
        for file in source_path.rglob('*.txt'):
            if self._in_output_project(file, source_path):
                continue
            if 'Story' in file.relative_to(source_path).parts:
                print(f'{Fore.YELLOW}[info] Skipped file: {file.name} (Reason: Osiris Script){Fore.RESET}')
                continue
            if not is_stats_file(file):
                continue
            groups.setdefault(stats_root(file), []).append(file)

        for out_dir, files in groups.items():
            try:
                _, converted = self._stats_converter.convert_group(sorted(files), out_dir)
                # Content of oddly named files now lives in the canonical .stats files
                self._skip_files.update(f for f in converted if not self._is_canonical_stats_file(f))
            except Exception as e:
                print(f'{Fore.RED}[info] Failed to convert stats in {out_dir}:\n\tError: {e}{Fore.RESET}')

    def convert_lsx_files(self, source_path: Path):
        print(f'\n{Fore.CYAN}[main] Converting LSX files:{Fore.RESET}')
        for file in source_path.rglob('*.lsx'):
            if self._in_output_project(file, source_path):
                continue
            self._convert_internal(file, self._lsx_converter)
        self._lsx_converter.flush()
        self._skip_files.update(self._lsx_converter.non_canonical)
        self._lsx_converter.non_canonical = set()

    def fix_locales(self, source_path: Path):
        print(f'{Fore.CYAN}[main] Reviewing locale XML files:{Fore.RESET}')
        for file in source_path.rglob('*.xml'):
            if file.name.endswith('_fix.xml') or self._in_output_project(file, source_path):
                continue
            self._locale_fixer.fix(file, self._lsx_converter)

    def build_tk_project(self, source_path: Path, output_dir: Path, is_cli: bool = True):
        print(f'{Fore.CYAN}[main] Checking to construct tk project:{Fore.RESET}')
        projects = []

        if source_path is None or not source_path.is_dir():
            print(f'{Fore.YELLOW}[info] Skipping construct tk project: {source_path} (Reason: Not a valid project dir){Fore.RESET}')
            return

        candidates = [source_path] if self.is_project_dir(source_path) else list(source_path.iterdir())
        for dir_path in candidates:
            if dir_path.is_dir() and not dir_path in projects and self.is_project_dir(dir_path):
                projects.append(dir_path)

        self._proj_builder.build_all(projects, output_dir, is_cli, self._skip_files)

    def refresh_aux_db(self):
        try:
            self._aux_db = self._build_aux_db(self.src_bg3_path)
            self._stats_converter.auxdb = self._aux_db
        except FileNotFoundError:
            print(f'{Fore.RED}[db] Can\'t compile AuxDB: bg3.exe not found in "{self.src_bg3_path}/bin" (check bg3path in settings.json){Fore.RESET}')
    #endregion

    # region Private helper functions
    @staticmethod
    def _in_output_project(file: Path, source_path: Path) -> bool:
        """Files of toolkit projects created by a previous run are never converted again"""
        rel = file.relative_to(source_path).parts
        for i in range(1, len(rel)):
            d = source_path.joinpath(*rel[:i])
            if d.joinpath('Projects').is_dir() and d.joinpath('Editor').is_dir():
                return True
        return False

    @staticmethod
    def _is_canonical_stats_file(file: Path) -> bool:
        # The toolkit writes Public/<mod>/Stats/Generated[/Data]/<file>.txt
        parts = file.parts
        if 'Public' not in parts or 'Generated' not in parts:
            return False
        stem = file.stem
        canonical = (stem in ['Armor', 'Character', 'Interrupt', 'Object', 'Passive', 'Weapon', 'Data', 'XPData',
                              'CriticalHitTypes', 'Equipment', 'TreasureTable', 'SpellSet', 'ItemCombos',
                              'ObjectCategoriesItemComboPreviewData', 'CraftingStationsItemComboPreviewData']
                     or stem.startswith('Status_') or stem.removeprefix('Spell_') in SPELL_TYPES and stem.startswith('Spell_'))
        return canonical

    @staticmethod
    def _is_file_guid(file: str) -> bool:
        return len(file) == 36 and file[8:9:] == "-" and file[13:14:] == "-" and file[18:19:] == "-" and file[23:24:] == "-"

    def _get_auxiliary_db(self, src_bg3_path: str, compile_aux_db: bool) -> dict:
        try:
            if compile_aux_db:
                return self._build_aux_db(src_bg3_path)
            else:
                print(f'{Fore.YELLOW}[db] Loading auxiliary ID Database...{Fore.RESET}')
                with open(self.path_to_root / 'auxdb.json', encoding="utf-8") as aux_db_data:
                    return json.load(aux_db_data)
        except FileNotFoundError:
            print(f'{Fore.YELLOW}[db] No auxiliary ID Database available, parents from other mods can\'t be recovered{Fore.RESET}')
            return {}

    def _build_aux_db(self, src_bg3_path: str):
        # Check if bg3 path valid
        if not Path(f"{src_bg3_path}/bin/bg3.exe").is_file():
            raise FileNotFoundError('')

        compdb = CompileDB(src_bg3_path, self.path_to_root)
        print(f'{Fore.YELLOW}[config] bg3.exe found\n[db] Compiling auxiliary ID Database...{Fore.RESET}')
        return compdb.compileAuxiliaryDB()

    def _get_db(self) -> dict:
        with open(self.path_to_root / 'db.json', encoding="utf-8") as db_data:
            db = json.load(db_data)
        if 'Schema' not in db:
            print(f'{Fore.RED}[db] db.json has no toolkit schema, run CompileDB with your bg3 path to update it{Fore.RESET}')
        return db

    def _convert_internal(self, file: Path, converter) -> None:
        if file.name in EXCLUSIONS:
            return None
        try:
            converter.convert(str(file))
        except Exception as e:
            print(f'{Fore.RED}[info] Failed to convert {file.name}:\n\tError: {e}\n\tFile: {file}{Fore.RESET}')
        return None

    def _unpack_internal(self, source_file: Path, output_path: Path, verbose=True):
        # unpack file
        self.lslib_util.uncompress_package(source_file, output_path)

        # convert binaries to lsx (originals are kept), loca to xml
        file_list = [f for f in output_path.resolve().glob('**/*') if f.is_file()]
        for file in file_list:
            resolved_file = file.resolve()
            if self.lslib_util.is_lsx_family(resolved_file.suffix):
                self.lslib_util.convert_file(resolved_file, resolved_file.with_suffix(resolved_file.suffix + '.lsx'))
            elif self.lslib_util.is_loca_type(resolved_file.suffix):
                self.lslib_util.convert_loca_file(resolved_file, resolved_file.with_suffix(resolved_file.suffix + '.xml'))
                # the toolkit builds .loca files from the xml
                file.unlink(True)

        if verbose:
            print(f'{Fore.GREEN}[info] Unpacked {source_file.name} (Out dir) {str(output_path)}{Fore.RESET}')
    # endregion
