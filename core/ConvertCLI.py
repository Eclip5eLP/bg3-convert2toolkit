import shutil
import subprocess
import zipfile
from pathlib import Path

from colorama import Fore

from core.ConvertAPI import ConvertAPI

ARCHIVE_SUFFIXES = ['.zip', '.rar', '.7z']


# Seems tad overkill, but if CLI options are expanded this will control that flow
class ConvertCLI:
    def __init__(self,
                 convert_api: ConvertAPI,
                 path_to_root: Path):
        self.convert_api = convert_api
        self.path_to_root = path_to_root

    def run(self):
        """
            Might have more logic in the future, for now this is hard-coded to run
            conversion logic on local "convert" folder and output result to the same
        """
        cli_path = self.path_to_root / 'convert'
        if not cli_path.exists():
            cli_path.mkdir(parents=True, exist_ok=True)

        # Downloaded mods usually come as archive (pak + info.json), extract them once
        for archive in [f for f in cli_path.iterdir() if f.suffix.lower() in ARCHIVE_SUFFIXES]:
            target = cli_path / archive.stem
            if not target.exists():
                self.extract(archive, target)

        # Unpack pak files into a folder of the same name (once)
        for pak in list(cli_path.glob('*.pak')) + list(cli_path.glob('*/*.pak')):
            unpack_dir = cli_path / pak.stem
            if unpack_dir.exists():
                continue
            unpack_dir.mkdir(parents=True)
            self.convert_api.unpack_file(pak, unpack_dir)

        self.convert_api.convert(cli_path, cli_path, True)

    @staticmethod
    def extract(archive: Path, target: Path):
        target.mkdir(parents=True)
        try:
            if archive.suffix.lower() == '.zip':
                with zipfile.ZipFile(archive) as z:
                    z.extractall(target)
            else:
                # Windows 10+ ships a tar that reads rar and 7z
                windows_tar = Path(r'C:\Windows\System32\tar.exe')
                tar = str(windows_tar) if windows_tar.exists() else shutil.which('tar')
                subprocess.run([tar, '-xf', str(archive), '-C', str(target)], check=True, capture_output=True)
            print(f'{Fore.GREEN}[archive] Extracted {archive.name}{Fore.RESET}')
        except Exception as e:
            shutil.rmtree(target, ignore_errors=True)
            print(f'{Fore.RED}[archive] Could not extract {archive.name} ({e}), extract it manually{Fore.RESET}')
