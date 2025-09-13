from pathlib import Path

from core.ConvertAPI import ConvertAPI


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
        self.convert_api.convert(cli_path, cli_path, True)
