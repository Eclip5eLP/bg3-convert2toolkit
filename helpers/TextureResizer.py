import math
import re
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

from colorama import Fore

# texconv names of DDS formats, by FourCC and by DXGI format of the DX10 header
FOURCC_FORMATS = {b'DXT1': 'BC1_UNORM', b'DXT2': 'BC2_UNORM', b'DXT3': 'BC2_UNORM', b'DXT4': 'BC3_UNORM', b'DXT5': 'BC3_UNORM',
                  b'ATI1': 'BC4_UNORM', b'BC4U': 'BC4_UNORM', b'ATI2': 'BC5_UNORM', b'BC5U': 'BC5_UNORM'}
DXGI_FORMATS = {28: 'R8G8B8A8_UNORM', 29: 'R8G8B8A8_UNORM_SRGB', 71: 'BC1_UNORM', 72: 'BC1_UNORM_SRGB', 74: 'BC2_UNORM',
                75: 'BC2_UNORM_SRGB', 77: 'BC3_UNORM', 78: 'BC3_UNORM_SRGB', 80: 'BC4_UNORM', 83: 'BC5_UNORM',
                87: 'B8G8R8A8_UNORM', 91: 'B8G8R8A8_UNORM_SRGB', 98: 'BC7_UNORM', 99: 'BC7_UNORM_SRGB'}

ATTRIBUTE = r'(<attribute id="{}" type="[^"]*" value=")([^"]*)(")'


class DDSInfo:
    def __init__(self, file: Path):
        with open(file, 'rb') as f:
            header = f.read(148)
        if header[:4] != b'DDS ':
            raise ValueError('not a DDS file')
        self.height, self.width = struct.unpack_from('<II', header, 12)
        self.mips = struct.unpack_from('<I', header, 28)[0]
        fourcc = header[84:88]
        if fourcc == b'DX10':
            self.format = DXGI_FORMATS.get(struct.unpack_from('<I', header, 128)[0])
        elif fourcc in FOURCC_FORMATS:
            self.format = FOURCC_FORMATS[fourcc]
        else:
            self.format = 'R8G8B8A8_UNORM' if struct.unpack_from('<I', header, 80)[0] & 0x40 else None


def next_power_of_two(value: int) -> int:
    return 1 << max(0, math.ceil(math.log2(max(1, value))))


def fit(width: int, height: int, max_size: int) -> tuple[int, int]:
    """Scale down to max_size keeping the aspect ratio, dimensions stay multiples of 4 (block size)"""
    scale = max_size / max(width, height)
    return max(4, int(width * scale) // 4 * 4), max(4, int(height * scale) // 4 * 4)


def find_texconv(bg3_path: str, configured: str = '') -> Path | None:
    candidates = [Path(configured)] if configured else []
    if bg3_path:
        candidates += [Path(bg3_path).parent / 'Baldurs Gate 3 Toolkit' / 'texconv.exe', Path(bg3_path) / 'texconv.exe']
    found = shutil.which('texconv')
    if found:
        candidates.append(Path(found))
    return next((c for c in candidates if c.is_file()), None)


class TextureResizer:
    """
        Huge textures waste VRAM and inflate the mod size. Textures above max_size are scaled down,
        icon atlases are first cropped to the area their icons actually use (no quality loss).
        The size information in atlases and texture banks is updated to match.
    """
    def __init__(self, texconv: Path | None, max_size: int = 2048, lslib_util=None):
        self.texconv = texconv
        self.max_size = max_size
        self.lslib_util = lslib_util

    def process(self, root: Path) -> list[str]:
        if not self.max_size:
            return []
        textures = {f.relative_to(root).as_posix().lower(): f for f in root.rglob('*') if f.suffix.lower() == '.dds'}
        oversized = {}
        for rel, f in textures.items():
            try:
                info = DDSInfo(f)
            except (ValueError, OSError):
                continue
            if max(info.width, info.height) > self.max_size:
                oversized[rel] = info
        if not oversized:
            return []
        if self.texconv is None:
            message = f'{len(oversized)} textures are larger than {self.max_size}px, but texconv.exe was not found (set texconvPath in settings.json)'
            print(f'{Fore.YELLOW}[texture] {message}{Fore.RESET}')
            return [message]

        lsx_files = {f: f.read_text(encoding='utf-8', errors='surrogateescape') for f in root.rglob('*.lsx')}
        atlases = self.find_atlases(lsx_files)
        changed = {}
        report = []
        for rel, info in oversized.items():
            file = textures[rel]
            try:
                if rel in atlases:
                    new_size, line = self.shrink_atlas(file, info, atlases[rel], lsx_files, changed)
                else:
                    new_size = fit(info.width, info.height, self.max_size)
                    self.run_texconv(file, file, new_size, info)
                    line = f'Texture {file.relative_to(root).as_posix()} scaled down from {info.width}x{info.height} to {new_size[0]}x{new_size[1]}'
            except Exception as e:
                report.append(f'Texture {file.relative_to(root).as_posix()} ({info.width}x{info.height}) could not be resized: {e}')
                continue
            self.update_texture_banks(rel, new_size, lsx_files, changed)
            report.append(line)

        for f, text in changed.items():
            f.write_text(text, encoding='utf-8', errors='surrogateescape')
            binary = f.with_suffix('')
            # Keep the binary in sync with its edited lsx
            if self.lslib_util is not None and binary.exists() and binary.suffix.lower() in ['.lsf', '.lsb', '.lsbs', '.lsbc']:
                self.lslib_util.convert_file(f, binary)

        for line in report:
            print(f'{Fore.YELLOW}[texture] {line}{Fore.RESET}')
        return report

    # region Atlases
    @staticmethod
    def find_atlases(lsx_files: dict) -> dict:
        """texture path (lower case) -> atlas lsx files that use it"""
        atlases = {}
        for f, text in lsx_files.items():
            if 'TextureAtlasPath' not in text:
                continue
            for path in re.findall(r'<node id="TextureAtlasPath">.*?id="Path"[^>]*value="([^"]+)"', text, re.S):
                atlases.setdefault(path.replace('\\', '/').lower(), []).append(f)
        return atlases

    def shrink_atlas(self, file: Path, info: DDSInfo, atlas_files: list, lsx_files: dict, changed: dict):
        texts = {f: changed.get(f, lsx_files[f]) for f in atlas_files}
        max_u = max([float(m[1]) for t in texts.values() for m in re.findall(ATTRIBUTE.format('U2'), t)] or [1.0])
        max_v = max([float(m[1]) for t in texts.values() for m in re.findall(ATTRIBUTE.format('V2'), t)] or [1.0])

        # Crop to the used area (icons start at the top left), then scale if it's still too large
        crop_w = min(info.width, next_power_of_two(math.ceil(max_u * info.width)))
        crop_h = min(info.height, next_power_of_two(math.ceil(max_v * info.height)))
        new_w, new_h = (crop_w, crop_h) if max(crop_w, crop_h) <= self.max_size else fit(crop_w, crop_h, self.max_size)
        scale = new_w / crop_w

        from PIL import Image
        with Image.open(file) as image:
            image = image.convert('RGBA').crop((0, 0, crop_w, crop_h))
            if (new_w, new_h) != (crop_w, crop_h):
                image = image.resize((new_w, new_h), Image.LANCZOS)
            with tempfile.TemporaryDirectory() as tmp:
                png = Path(tmp) / (file.stem + '.png')
                image.save(png)
                self.run_texconv(png, file, None, info)

        # UVs are relative to the texture size
        for f, text in texts.items():
            for key, factor in [('U1', info.width / crop_w), ('U2', info.width / crop_w), ('V1', info.height / crop_h), ('V2', info.height / crop_h)]:
                text = re.sub(ATTRIBUTE.format(key), lambda m: f'{m[1]}{float(m[2]) * factor:.9g}{m[3]}', text)
            text = self.set_size(text, 'TextureAtlasTextureSize', new_w, new_h)
            if scale < 1:
                icon = re.search(r'<node id="TextureAtlasIconSize">.*?id="Height"[^>]*value="(\d+)".*?id="Width"[^>]*value="(\d+)"', text, re.S)
                if icon:
                    text = self.set_size(text, 'TextureAtlasIconSize', round(int(icon[2]) * scale), round(int(icon[1]) * scale))
            changed[f] = text

        line = f'Icon atlas {file.name} reduced from {info.width}x{info.height} to {new_w}x{new_h}'
        line += ' (cropped to the used area)' if scale == 1 else f' (cropped and scaled, icons are now {scale:.0%} of their size)'
        return (new_w, new_h), line

    @staticmethod
    def set_size(text: str, node: str, width: int, height: int) -> str:
        def sub(m):
            block = re.sub(ATTRIBUTE.format('Width'), lambda a: f'{a[1]}{width}{a[3]}', m[0])
            return re.sub(ATTRIBUTE.format('Height'), lambda a: f'{a[1]}{height}{a[3]}', block)
        return re.sub(rf'<node id="{node}">.*?</node>', sub, text, flags=re.S)
    # endregion

    def update_texture_banks(self, rel: str, size: tuple, lsx_files: dict, changed: dict):
        """Texture resources store the size of their texture"""
        for f, original in lsx_files.items():
            text = changed.get(f, original)
            if 'SourceFile' not in text:
                continue

            def sub(m):
                block = m[0]
                source = re.search(r'id="SourceFile"[^>]*value="([^"]+)"', block)
                if not source or not rel.endswith(source[1].replace('\\', '/').lower()):
                    return block
                block = re.sub(ATTRIBUTE.format('Width'), lambda a: f'{a[1]}{size[0]}{a[3]}', block)
                return re.sub(ATTRIBUTE.format('Height'), lambda a: f'{a[1]}{size[1]}{a[3]}', block)
            new_text = re.sub(r'<node id="Resource">.*?</node>', sub, text, flags=re.S)
            if new_text != text:
                changed[f] = new_text

    def run_texconv(self, source: Path, target: Path, size: tuple | None, info: DDSInfo):
        """Writes source as DDS to target, in the format and with the mip mapping of the original texture"""
        with tempfile.TemporaryDirectory() as tmp:
            # texconv can't handle paths longer than MAX_PATH, work on a short copy
            out_dir = Path(tmp) / 'out'
            out_dir.mkdir()
            source = Path(shutil.copy(source, Path(tmp) / ('in' + source.suffix.lower())))
            args = [str(self.texconv), '-nologo', '-y', '-o', str(out_dir), '-m', '0' if info.mips > 1 else '1']
            if size is not None:
                args += ['-w', str(size[0]), '-h', str(size[1])]
            if info.format:
                args += ['-f', info.format]
            if source.suffix.lower() == '.png':
                # Keep the stored values as they are, no gamma conversion
                args += ['-srgbi', '-srgbo'] if info.format and info.format.endswith('SRGB') else []
            args.append(str(source))
            result = subprocess.run(args, capture_output=True, text=True)
            produced = list(out_dir.glob('*.dds')) + list(out_dir.glob('*.DDS'))
            if result.returncode != 0 or not produced:
                raise RuntimeError((result.stdout + result.stderr).strip().splitlines()[-1] if (result.stdout + result.stderr).strip() else 'texconv failed')
            shutil.move(str(produced[0]), str(target))
