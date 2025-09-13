import sys
from pathlib import Path


LSX_SUFFIX_FAMILY: list[str] = [".lsf", ".lsb", ".lsbs", ".lsbc", ".lsfx"]
LOCA_TYPE = ".loca"


class LSLibUtil:
    def __init__(self, path_to_lslib: Path):
        divine = Path(path_to_lslib)
        self._lslib_dll = divine.is_dir() and divine.joinpath("LSLib.dll") or divine.parent.joinpath("LSLib.dll")

        # Setting up lslib dll for use
        import pythonnet
        pythonnet.load('coreclr')
        import clr
        if not str(self._lslib_dll.parent.absolute()) in sys.path:
            sys.path.append(str(self._lslib_dll.parent.absolute()))

        # set up LSLib types for local use
        clr.AddReference("LSLib")  # type: ignore
        from LSLib.LS import LocaFormat, LocaUtils, Packager, ResourceUtils, ResourceConversionParameters, ResourceLoadParameters  # type: ignore
        from LSLib.LS.Enums import Game  # type: ignore

        self.load_params = ResourceLoadParameters.FromGameVersion(Game.BaldursGate3)
        self.conversion_params = ResourceConversionParameters.FromGameVersion(Game.BaldursGate3)
        self.packager = Packager()
        self.resource_utils = ResourceUtils
        self.loca_utils = LocaUtils
        self.loca_format = LocaFormat

        # setup System types for file conversion
        clr.AddReference('System')  # type: ignore
        from System.IO import File, FileStream, FileMode  # type: ignore

        self.file = File
        self.file_stream = FileStream
        self.file_mode = FileMode

    def uncompress_package(self, source_file: Path, output_path: Path):
        if source_file is None or output_path is None:
            return
        self.packager.UncompressPackage(str(source_file.resolve()), str(output_path.resolve()))

    def convert_file(self, source_file: Path, output_path: Path):
        if source_file is None or output_path is None:
            return

        input_str = str(source_file.resolve())
        output_str = str(output_path.resolve())

        out_format = self.resource_utils.ExtensionToResourceFormat(output_str)
        resource = self.resource_utils.LoadResource(input_str, self.load_params)
        self.resource_utils.SaveResource(resource, output_str, out_format, self.conversion_params)

    def convert_loca_file(self, source_file: Path, output_path: Path):
        file = None
        try:
            file = self.file.Open(str(source_file.resolve()), self.file_mode.Open)
            resource = self.loca_utils.Load(file, self.loca_format.Loca)
            self.loca_utils.Save(resource, str(output_path.resolve()), self.loca_format.Xml)
        finally:
            if file is not None:
                file.Close()

    @staticmethod
    def is_lsx_family(suffix: str):
        return suffix in LSX_SUFFIX_FAMILY

    @staticmethod
    def is_loca_type(suffix: str):
        return LOCA_TYPE == suffix
