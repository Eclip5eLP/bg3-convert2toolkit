import re
import shutil
import uuid
from pathlib import Path

import xmltodict
from colorama import Fore

from helpers.LSXtoTBL import LSXconvert, as_list, strip_suffixes
from helpers.Renamer import rewrite_text, find_names

# Folders of the base game and its built-in modules, references to them must never be renamed
VANILLA_FOLDERS = {'Shared', 'SharedDev', 'Gustav', 'GustavDev', 'GustavX', 'Honour', 'HonourX', 'Engine', 'Game',
                   'MainUI', 'ModBrowser', 'PhotoMode', 'CrossplayUI', 'DiceSet_01', 'DiceSet_02', 'DiceSet_03',
                   'DiceSet_04', 'DiceSet_05', 'DiceSet_06'}
BINARY_SUFFIXES = ['.lsf', '.lsb', '.lsbs', '.lsbc', '.lsfx']
TEXT_SUFFIXES = ['.lsx', '.lsj']
EDITOR_SUFFIXES = ['.tbl', '.stats', '.mei']
SCAN_SUFFIXES = ['.lsx', '.lsj', '.txt', '.khn', '.xml', '.json', '.lua']
# Files in which references to renamed spells are replaced: (folder run, suffixes), "*" matches any folder.
# References anywhere else are only reported, they need a decision case by case.
RENAME_RULES = [
    (('public', '*', 'roottemplates'), ('.lsx',)),
    (('public', '*', 'lists'), ('.lsx',)),
    (('public', '*', 'progressions'), ('.lsx',)),
    (('public', '*', 'shapeshift'), ('.lsx',)),
    (('public', '*', 'stats', 'generated'), ('.txt',)),
    (('scripts', 'thoth', 'helpers'), ('.khn',)),
    (('story', 'rawfiles', 'goals'), ('.txt',)),
    (('localization',), ('.xml',)),
]


def is_intermediate(file: Path) -> bool:
    """lsx created while unpacking a binary (e.g. _merged.lsf.lsx)"""
    return file.suffix == '.lsx' and Path(file.stem).suffix in BINARY_SUFFIXES


def sanitize(name: str) -> str:
    return ''.join(x for x in name if x.isalnum() or x in ['_', '-', '(', ')'])


class ProjectBuilder:
    path_to_templates = None

    # Init
    def __init__(self, path_to_templates: Path, conv_lsx: LSXconvert = None, stats_categories: dict = None):
        self.conv_lsx = conv_lsx
        self.path_to_templates = path_to_templates
        self.stats_categories = stats_categories or {}

    # Check if path is a workspace resembling a mod
    @staticmethod
    def is_project(dirs) -> bool:
        pdir = Path(dirs)
        if not pdir.is_dir() or not pdir.joinpath('Mods').is_dir():
            return False
        # Already converted toolkit projects are skipped (e.g. output of a previous run)
        if pdir.joinpath('Projects').is_dir() and pdir.joinpath('Editor').is_dir():
            return False
        return any(pdir.glob('Mods/*/meta.lsx')) or pdir.joinpath('Public').is_dir()

    # Build all saved projects
    def build_all(self, projects: list[Path], output_dir: Path, prompt: bool = False, skip_files: set = None):
        for x in projects:
            self.build(x, output_dir, prompt, skip_files)

    # Build a projects for use with Toolkit
    def build(self, source_path: Path, output_dir: Path, prompt: bool = False, skip_files: set = None,
              renames: dict = None, report: list = None):
        skip_files = skip_files or set()
        renames = renames or {}
        unchanged = {}  # file -> [(line, old name)] references to renamed spells that were left as they are
        replaced = {}  # file -> number of replaced references
        if not self.is_project(source_path):
            print(f'{Fore.YELLOW}[Project] {source_path.name} is not a valid project{Fore.RESET}')
            return False

        meta = self.read_meta(source_path)
        project_root_name = sanitize(meta.get('Name', '')) or self.strip_uuid(source_path.name)
        project_uuid = self.gen_uuid()

        # Prompt user for input
        if prompt:
            print(f'{Fore.CYAN}[Project] Attempting to create Project \'{project_root_name}\'\nEnter Project name (type X to skip or leave empty to use default): {Fore.RESET}')
            name = input()
            if name == 'X' or name == 'x':  # Skip
                return False
            name = sanitize(name)
            if not name == '':
                project_root_name = name
        project_name = f'{project_root_name}_{project_uuid}'
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
            self.createMeta(project_output_path, project_name, project_root_name, project_uuid, meta)

            own_folders = self.own_folders(source_path)
            vanilla = sorted({f for root in ['Public', 'Mods', 'Generated/Public'] for f in self.folders(source_path / root)} & VANILLA_FOLDERS)
            if vanilla:
                print(f'{Fore.YELLOW}[Project] Overrides of base game folders kept as-is: {", ".join(vanilla)}{Fore.RESET}')

            sources = {}
            for file in sorted(source_path.rglob('*')):
                if not file.is_file() or file in skip_files or file.name == 'meta.lsx' and file.parent.parent.name == 'Mods':
                    continue
                rel = file.relative_to(source_path).as_posix()
                dest_rel = self.map_path(rel, file, own_folders, project_name)
                if dest_rel is None:
                    continue
                if dest_rel in sources:
                    print(f'{Fore.YELLOW}[Project] {rel} collides with {sources[dest_rel]}, skipped{Fore.RESET}')
                    continue
                sources[dest_rel] = rel
                self.place_file(file, project_output_path / dest_rel, own_folders, project_name, rel, renames, unchanged, replaced)

            report = list(report or []) + self.dedupe_localization(project_output_path / 'Mods' / project_name / 'Localization')
            self.write_report(output_dir / f'{project_name}_Report.txt', report, renames, replaced, unchanged)
            print(f'{Fore.GREEN}[Project] Project {project_name} successfully created{Fore.RESET}')
            return True
        except Exception as e:
            # Failed (failsafe catch)
            print(f'{Fore.RED}[Project] Failed to create project {project_root_name}\n\tReason: {e}{Fore.RESET}')
            if Path(project_output_path).exists():
                shutil.rmtree(project_output_path)
            return False

    # region Paths
    @staticmethod
    def folders(path: Path) -> list[str]:
        return [p.name for p in path.iterdir() if p.is_dir()] if path.is_dir() else []

    def own_folders(self, source_path: Path) -> list[str]:
        names = set()
        for root in ['Public', 'Mods', 'Generated/Public', 'Editor/Mods']:
            names.update(self.folders(source_path / root))
        # Longest first so nested names never replace a shorter prefix first
        return sorted(names - VANILLA_FOLDERS, key=len, reverse=True)

    def map_path(self, rel: str, file: Path, own: list[str], project_name: str) -> str | None:
        parts = rel.split('/')

        # Localization: keep the fixed file under the original name
        if file.name.endswith('_fix.xml'):
            parts[-1] = file.name[:-len('_fix.xml')] + '.xml'
        elif file.suffix == '.xml' and file.with_name(file.stem + '_fix.xml').exists():
            return None  # replaced by its _fix.xml
        if parts[0] == 'Localization':
            parts = ['Mods', project_name] + parts

        # Binaries are produced from (or copied next to) their intermediate lsx
        if is_intermediate(file):
            parts[-1] = file.stem
        elif file.suffix in BINARY_SUFFIXES and file.with_name(file.name + '.lsx').exists():
            return None

        if len(parts) > 2 and parts[0] in ('Public', 'Mods') and parts[1] in own:
            parts[1] = project_name
        elif len(parts) > 3 and parts[0] == 'Generated' and parts[1] == 'Public' and parts[2] in own:
            parts[2] = project_name
        elif len(parts) > 3 and parts[0] == 'Editor' and parts[1] == 'Mods' and parts[2] in own:
            parts[2] = project_name
        elif len(parts) > 1 and parts[0] == 'Generated' and parts[1] != 'Public':
            parts = ['Generated', 'Public', project_name] + parts[1:]

        # Editor files of the toolkit
        if file.suffix in EDITOR_SUFFIXES and len(parts) > 2 and parts[0] == 'Public':
            parts = ['Editor', 'Mods'] + parts[1:]
            if file.suffix == '.stats':
                # Stats/Generated[/Data]/X.stats -> Stats/<category>/X.stats
                category = self.stats_categories.get(file.stem, 'Stats')
                stats_index = parts.index('Stats') if 'Stats' in parts else 3
                parts = parts[:stats_index] + ['Stats', category, parts[-1]]
        return '/'.join(parts)

    def rewrite_paths(self, text: str, own: list[str], project_name: str) -> str:
        for folder in own:
            if folder == project_name:
                continue
            text = text.replace(f'Public/{folder}/', f'Public/{project_name}/')
            text = text.replace(f'Mods/{folder}/', f'Mods/{project_name}/')
        # Old style assets directly in Generated/
        return re.sub(r'(value="|")Generated/(?!Public/)', rf'\1Generated/Public/{project_name}/', text)
    # endregion

    @staticmethod
    def rename_allowed(rel: str) -> bool:
        parts = [p.lower() for p in rel.split('/')]
        dirs, suffix = parts[:-1], Path(parts[-1]).suffix
        for run, suffixes in RENAME_RULES:
            if suffix not in suffixes:
                continue
            for i in range(len(dirs) - len(run) + 1):
                if all(r == '*' or dirs[i + j] == r for j, r in enumerate(run)):
                    return True
        return False

    def update_text(self, data: str, file: Path, own, project_name, rel, renames, unchanged, replaced) -> str:
        if file.suffix in TEXT_SUFFIXES:
            data = self.rewrite_paths(data, own, project_name)
        if renames:
            if self.rename_allowed(rel):
                data, count = rewrite_text(data, renames)
                if count:
                    replaced[rel] = count
            else:
                hits = find_names(data, renames.keys())
                if hits:
                    unchanged[rel] = hits
        return data

    def place_file(self, file: Path, dest: Path, own: list[str], project_name: str, rel: str = None,
                   renames: dict = None, unchanged: dict = None, replaced: dict = None):
        dest.parent.mkdir(parents=True, exist_ok=True)
        rel = rel or file.name
        renames = renames or {}
        unchanged = unchanged if unchanged is not None else {}
        replaced = replaced if replaced is not None else {}
        if is_intermediate(file):
            data = file.read_text(encoding='utf-8')
            rewritten = self.update_text(data, file, own, project_name, rel, renames, unchanged, replaced)
            binary = file.with_suffix('')
            if rewritten == data and binary.exists():
                shutil.copy(binary, dest)  # untouched original binary
                return
            tmp = dest.with_name(dest.name + '.tmp.lsx')
            tmp.write_text(rewritten, encoding='utf-8')
            try:
                self.conv_lsx.lsx2lsf(tmp, verbose=False, output=dest)
            finally:
                tmp.unlink(missing_ok=True)
            return

        if file.suffix in TEXT_SUFFIXES or renames and file.suffix.lower() in SCAN_SUFFIXES:
            data = file.read_text(encoding='utf-8', errors='surrogateescape')
            dest.write_text(self.update_text(data, file, own, project_name, rel, renames, unchanged, replaced),
                            encoding='utf-8', errors='surrogateescape')
            return
        if renames and file.suffix.lower() in ('.osi', '.div'):
            # Compiled Osiris can't be edited, only reported
            content = file.read_bytes().decode('latin-1')
            hits = [(0, name) for name in renames if re.search(rf'(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])', content)]
            if hits:
                unchanged[rel] = hits
        shutil.copy(file, dest)

    @staticmethod
    def dedupe_localization(localization: Path) -> list[str]:
        """
            Paks often ship leftover xml copies next to the .loca the game actually loads, the toolkit compiles
            every xml of a language. Strings are kept once, preferring the ones that came from a .loca file.
        """
        report = []
        if not localization.is_dir():
            return report
        for language in [d for d in localization.iterdir() if d.is_dir()]:
            files = sorted(language.glob('*.xml'), key=lambda f: (not f.name.endswith('.loca.xml'), f.name.lower()))
            seen = set()
            for file in files:
                try:
                    with open(file, 'rb') as f:
                        data = xmltodict.parse(f.read())
                    content_list = data.get('contentList') or {}
                    contents = as_list(content_list.get('content'))
                except Exception:
                    continue
                kept = [c for c in contents if c.get('@contentuid') not in seen]
                seen.update(c.get('@contentuid') for c in contents)
                if len(kept) == len(contents):
                    continue
                if not kept:
                    file.unlink()
                    report.append(f'Localization {language.name}/{file.name} removed, all its strings already exist in other files')
                    continue
                data['contentList']['content'] = kept
                with open(file, 'w', encoding='utf-8') as f:
                    f.write(xmltodict.unparse(data, pretty=True, indent='  '))
                report.append(f'Localization {language.name}/{file.name}: {len(contents) - len(kept)} strings that exist in other files removed')
        return report

    @staticmethod
    def write_report(out: Path, report: list, renames: dict, replaced: dict, unchanged: dict):
        lines = list(report)
        if replaced:
            lines += ['', 'References to renamed spells updated:'] + [f'  {rel}: {n}' for rel, n in sorted(replaced.items())]
        if unchanged:
            lines += ['', 'References to renamed spells that were NOT updated (check and update manually):']
            for rel, hits in sorted(unchanged.items()):
                for line, name in hits[:25]:
                    where = f'{rel}:{line}' if line else f'{rel} (compiled)'
                    lines.append(f'  {where}: "{name}" -> "{renames[name]}"')
                if len(hits) > 25:
                    lines.append(f'  {rel}: ... and {len(hits) - 25} more')
        if not lines:
            return
        out.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        print(f'{Fore.YELLOW}[Project] Review the conversion report: {out}{Fore.RESET}')

    # region Metadata
    @staticmethod
    def read_meta(source_path: Path) -> dict:
        """Read ModuleInfo and dependencies of the source mod"""
        info = {'dependencies': []}
        metas = sorted(source_path.glob('Mods/*/meta.lsx'))
        if not metas:
            return info
        try:
            with open(metas[0], 'rb') as f:
                data = xmltodict.parse(f.read())
            root = as_list(data['save']['region'])[0]['node']
            for child in as_list((root.get('children') or {}).get('node')):
                if child['@id'] == 'ModuleInfo':
                    for a in as_list(child.get('attribute')):
                        info[a['@id']] = a.get('@value', '')
                elif child['@id'] == 'Dependencies':
                    for dep in as_list((child.get('children') or {}).get('node')):
                        info['dependencies'].append({a['@id']: a for a in as_list(dep.get('attribute'))})
        except Exception as e:
            print(f'{Fore.YELLOW}[Project] Could not read {metas[0]}: {e}{Fore.RESET}')
        return info

    # Create metadata
    def createMeta(self, pdir, pname, pname_raw, pguid, meta: dict = None):
        meta = meta or {}

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

        # Base game dependencies are managed by the toolkit, only carry over other mods
        dependencies = ''
        for dep in meta.get('dependencies', []):
            folder = dep.get('Folder', {}).get('@value', '')
            if folder in VANILLA_FOLDERS:
                continue
            dependencies += '\n                        <node id="ModuleShortDesc">'
            for key in ['Folder', 'MD5', 'Name', 'PublishHandle', 'UUID', 'Version64']:
                if key in dep:
                    a = dep[key]
                    dependencies += f'\n                            <attribute id="{key}" type="{a.get("@type", "LSString")}" value="{self.xmlesc(a.get("@value", ""))}"/>'
            dependencies += '\n                        </node>'

        data = data.replace('$DEPENDENCIES', dependencies)
        data = data.replace('$MOD_FOLDER', self.xmlesc(pname))
        data = data.replace('$MOD_NAME', self.xmlesc(pname_raw))
        data = data.replace('$MOD_UUID', pguid)
        data = data.replace('$MOD_AUTHOR', self.xmlesc(meta.get('Author', '') or 'ConversionAuthor'))
        data = data.replace('$MOD_DESCRIPTION', self.xmlesc(meta.get('Description', '') or 'Conversion Description'))
        data = data.replace('$MOD_VERSION', meta.get('Version64', '') or '36028797018963968')

        with open(f'{pdir}/Mods/{pname}/meta.lsx', 'w', encoding="utf-8") as f:
            f.write(data)

        return True
    # endregion

    # Generate a new UUID
    def gen_uuid(self) -> str:
        return str(uuid.uuid4())

    @staticmethod
    def strip_uuid(name: str) -> str:
        # ModName_<uuid> or mod.io style modname_<partial uuid>-<id>
        stripped = re.sub(r'_[0-9a-fA-F]{8}-[0-9a-zA-Z-]*$', '', name)
        return sanitize(stripped) or sanitize(name)

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
