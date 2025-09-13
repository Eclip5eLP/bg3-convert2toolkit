import json
from pathlib import Path

from colorama import Fore

from helpers.CompileDB import CompileDB
from helpers.FixLocale import FixLocale
from helpers.LSLibUtil import LSLibUtil
from helpers.LSXtoTBL import LSXconvert
from helpers.ProjectBuilder import ProjectBuilder
from helpers.Stats2kit import StatsConvert

EXCLUSIONS = ['meta.lsx', 'metadata.lsf.lsx']
FORCE_FAIL = ['SpellSet.txt']


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
        self._proj_builder = ProjectBuilder(path_to_templates, self._lsx_converter)

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
        self.convert_stat_files(source_path)
        self.convert_lsx_files(source_path)
        self.fix_locales(source_path)
        self.build_tk_project(source_path, output_dir, is_cli)

    @staticmethod
    def is_project_dir(source_path: Path) -> bool:
        if not source_path.exists() or not source_path.is_dir():
            return False
        structure = ['Public/','Mods/']
        for s in structure:
            if not source_path.joinpath(Path(s)).exists():
                return False
        return True

    def is_valid_source(self, source_path: Path) -> bool:
        return (source_path is not None
                and source_path.exists()
                and (source_path.is_dir() or self.is_pak(source_path)))

    @staticmethod
    def is_pak(source_path: Path) -> bool:
        return (source_path is not None
                and source_path.exists()
                and source_path.suffix == '.pak')

    def unpack_file(self, source_path: Path, output_path: Path):
        if not self.is_pak(source_path):
            print(f'{Fore.RED}[pak] Can\'t unpack {str(source_path)} (Not valid Pak file){Fore.RESET}')
            return

        if output_path is None or not output_path.is_dir():
            print(f'{Fore.RED}[pak] Can\'t unpack output to {str(output_path)} (Not valid dir){Fore.RESET}')
            return

        self._unpack_internal(source_path, output_path)

    def convert_stat_files(self, source_path: Path):
        print(f'{Fore.CYAN}[main] Converting Stats files:{Fore.RESET}')
        for file in source_path.rglob('*.txt'):
            if file.name in FORCE_FAIL:
                print(f'{Fore.YELLOW}[info] Skipped file: {file.name} (Reason: Not yet supported){Fore.RESET}')
                continue
            elif file.full_match('**/Mods/*/Story/**'):
                print(f'{Fore.YELLOW}[info] Skipped file: {file.name} (Reason: Osiris Script){Fore.RESET}')
                continue
            self._convert_internal(file, self._db['Stats'], self._stats_converter)

    def convert_lsx_files(self, source_path: Path):
        print(f'\n{Fore.CYAN}[main] Converting LSX files:{Fore.RESET}')
        for file in source_path.rglob('*.lsx'):
            if file.name in FORCE_FAIL:
                print(f'{Fore.YELLOW}[info] Skipped file: {file.name} (Reason: Not yet supported){Fore.RESET}')
                continue
            self._convert_internal(file, self._db['LSX'], self._lsx_converter)

    def fix_locales(self, source_path: Path):
        print(f'{Fore.CYAN}[main] Reviewing locale XML files:{Fore.RESET}')
        for file in source_path.rglob('*.xml'):
            if file.name[-8::] == '_fix.xml':
                continue
            if file.name in FORCE_FAIL:
                print(f'{Fore.YELLOW}[info] Skipped file: {file.name} (Reason: Not yet supported){Fore.RESET}')
                continue
            self._locale_fixer.fix(file, self._lsx_converter)

    def build_tk_project(self, source_path: Path, output_dir: Path, is_cli: bool = True):
        print(f'{Fore.CYAN}[main] Checking to construct tk project:{Fore.RESET}')
        projects = []

        if source_path is None or not source_path.is_dir():
            print(f'{Fore.YELLOW}[info] Skipping construct tk project: {source_path} (Reason: Not a valid project dir){Fore.RESET}')
            return

        for dir_path in source_path.iterdir():
            if dir_path.is_dir() and not dir_path in projects and self.is_project_dir(dir_path):
                projects.append(dir_path)

        self._proj_builder.build_all(projects, output_dir, is_cli)

    def refresh_aux_db(self):
        self._aux_db = self._build_aux_db(self.src_bg3_path)
    #endregion

    # region Private helper functions
    @staticmethod
    def _is_file_guid(file: str) -> bool:
        return len(file) == 36 and file[8:9:] == "-" and file[13:14:] == "-" and file[18:19:] == "-" and file[23:24:] == "-"

    def _get_auxiliary_db(self, src_bg3_path: str, compile_aux_db: bool) -> dict:
        try:
            if compile_aux_db:
                return self._build_aux_db(src_bg3_path)
            else:
                print(f'{Fore.YELLOW}[config] bg3.exe found\n[db] Loading auxiliary ID Database...{Fore.RESET}')
                with open(self.path_to_root / 'auxdb.json', encoding="utf-8") as aux_db_data:
                    return json.load(aux_db_data)
        except FileNotFoundError:
            return {}

    @staticmethod
    def _build_aux_db(src_bg3_path: str):
        # Check if bg3 path valid
        if not Path(f"{src_bg3_path}/bin/bg3.exe").is_file():
            raise FileNotFoundError('')

        compdb = CompileDB(src_bg3_path)
        print(f'{Fore.YELLOW}[config] bg3.exe found\n[db] Compiling auxiliary ID Database...{Fore.RESET}')
        return compdb.compileAuxiliaryDB()

    def _get_db(self) -> dict:
        with open(self.path_to_root / 'db.json', encoding="utf-8") as db_data:
            return json.load(db_data)

    def _convert_internal(self, file: Path, db: dict, converter) -> None:
        if file.name in EXCLUSIONS:
            return None
        try:
            fuuid = db.get(file.name.split('.')[0].replace('Spell_', ''), None)
            converter.setUUID(fuuid)
            chk = converter.convert(str(file))
            if chk:
                if fuuid is None:
                    print(f'{Fore.YELLOW}[info] Converted {file.name} (No UUID found: Incorrect filename){Fore.RESET}')
                else:
                    print(f'{Fore.GREEN}[info] Converted {file.name} (UUID: {fuuid}){Fore.RESET}')
        except Exception as e:
            if self._is_file_guid(file.name.split(".")[0]):
                print(f'{Fore.YELLOW}[info] Skipped file: {file.name} (Reason: Cannot convert binary){Fore.WHITE}')
            else:
                print(f'{Fore.RED}[info] Failed to convert {file.name}:\n\tError: {e}\n\tFile: {file}{Fore.RESET}')
        return None

    def _unpack_internal(self, source_file: Path, output_path: Path, verbose=True):
        # unpack file
        self.lslib_util.uncompress_package(source_file, output_path)

        # convert binaries to lsx, loca to xml
        file_list = [f for f in output_path.resolve().glob('**/*') if f.is_file()]
        for file in file_list:
            converted = False
            resolved_file = file.resolve()
            if self.lslib_util.is_lsx_family(resolved_file.suffix):
                self.lslib_util.convert_file(resolved_file, resolved_file.with_suffix(resolved_file.suffix + '.lsx'))
                converted = True
            elif self.lslib_util.is_loca_type(resolved_file.suffix):
                self.lslib_util.convert_loca_file(resolved_file, resolved_file.with_suffix(resolved_file.suffix + '.xml'))
                converted = True

            # if converted type, remove original file
            if converted:
                file.unlink(True)

        if verbose:
            print(f'{Fore.GREEN}[info] Unpacked {source_file.name} (Out dir) {str(output_path)}{Fore.RESET}')
    # endregion
