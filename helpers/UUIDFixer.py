import re
import uuid
from pathlib import Path

from colorama import Fore

# Something shaped like a UUID (8-4-4-4-12 letters/digits), possibly with a typo in it
UUID_SHAPE = re.compile(r'(?<![0-9A-Za-z-])[0-9A-Za-z]{8}-[0-9A-Za-z]{4}-[0-9A-Za-z]{4}-[0-9A-Za-z]{4}-[0-9A-Za-z]{12}(?![0-9A-Za-z-])')
# Five groups of hex digits that are about as long as a UUID but not 8-4-4-4-12
UUID_GROUPS = re.compile(r'(?<![0-9A-Za-z-])[0-9A-Fa-f]+(?:-[0-9A-Fa-f]+){4}(?![0-9A-Za-z-])')
VALID_UUID = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
GUID_ATTRIBUTE = re.compile(r'type="guid" value="([^"]+)"')
NODE_OPEN = re.compile(r'<node id="([^"]*)"(\s*/)?>')
ATTRIBUTE = re.compile(r'<attribute id="([^"]*)"[^>]*\bvalue="([^"]*)"')
# Localization handles look like UUIDs (h5e2a77b-5dad-...) but aren't
HANDLE_CONTEXT = re.compile(r'(handle|contentuid)="$')

TEXT_SUFFIXES = {'.lsx', '.lsj', '.txt', '.khn', '.json', '.xml'}
NAMESPACE = uuid.UUID('6f1b3c2e-6a77-4b4f-9d61-3f0c8b3f7e10')
GROUP_LENGTHS = (8, 4, 4, 4, 12)


def is_valid(value: str) -> bool:
    return VALID_UUID.match(value) is not None


class UUIDFixer:
    """
        The toolkit crashes while loading a project that contains a malformed UUID, the game doesn't care.
        Malformed UUIDs are replaced in every text file of a mod (binaries are rebuilt from their lsx):
        - by the UUID the author most likely meant, if the same node/attribute uses it elsewhere in the mod
        - otherwise by a new UUID that is derived from the malformed one, so all its references stay linked
    """
    def __init__(self, lslib_util=None):
        self.lslib_util = lslib_util

    def fix(self, root: Path) -> list[str]:
        files = [f for f in root.rglob('*') if f.is_file() and f.suffix.lower() in TEXT_SUFFIXES]
        texts = {}
        for f in files:
            try:
                texts[f] = f.read_text(encoding='utf-8')
            except (UnicodeDecodeError, OSError):
                continue

        invalid = {}  # value -> set of slots (node id, attribute id) it was found in
        slots = {}  # (node id, attribute id) -> set of valid values used there
        for f, text in texts.items():
            for value, slot in self.find_uuids(text, f.suffix.lower() == '.lsx'):
                if is_valid(value):
                    if slot is not None:
                        slots.setdefault(slot, set()).add(value)
                else:
                    invalid.setdefault(value, set()).add(slot)

        if not invalid:
            return []

        report = []
        replacements = {}
        for value, found_in in invalid.items():
            recovered = self.recover(value, found_in, slots)
            if recovered:
                replacements[value] = recovered
                report.append(f'Malformed UUID "{value}" replaced by "{recovered}" (used by the same {self.slot_name(found_in)} elsewhere in the mod)')
            else:
                replacements[value] = str(uuid.uuid5(NAMESPACE, value))
                report.append(f'Malformed UUID "{value}" replaced by new UUID "{replacements[value]}" (in {self.slot_name(found_in)}, check if it should reference something)')

        for f, text in texts.items():
            new_text = self.replace(text, replacements)
            if new_text == text:
                continue
            f.write_text(new_text, encoding='utf-8')
            # Keep the binary in sync with its edited lsx
            binary = f.with_suffix('')
            if self.lslib_util is not None and f.suffix == '.lsx' and binary.exists() and binary.suffix in ['.lsf', '.lsfx', '.lsb', '.lsbs', '.lsbc']:
                self.lslib_util.convert_file(f, binary)

        for line in report:
            print(f'{Fore.YELLOW}[uuid] {line}{Fore.RESET}')
        return report

    @staticmethod
    def slot_name(found_in: set) -> str:
        named = sorted(f'{node}/{attr}' for node, attr in (s for s in found_in if s is not None))
        return ', '.join(named) if named else 'text'

    @staticmethod
    def find_uuids(text: str, is_lsx: bool):
        """Yields (value, slot) of everything that is or looks like a UUID"""
        nodes = []
        for line in text.splitlines():
            if is_lsx:
                for m in NODE_OPEN.finditer(line):
                    if not m.group(2):
                        nodes.append(m.group(1))
                if '</node>' in line and nodes:
                    nodes.pop()
            attr = ATTRIBUTE.search(line) if is_lsx else None
            slot = (nodes[-1] if nodes else '', attr.group(1)) if attr else None
            for m in GUID_ATTRIBUTE.finditer(line):
                if not is_valid(m.group(1)) and not UUID_SHAPE.fullmatch(m.group(1)):
                    yield m.group(1), slot
            for m in UUID_SHAPE.finditer(line):
                if not HANDLE_CONTEXT.search(line[max(0, m.start() - 12):m.start()]):
                    yield m.group(0), slot
            for m in UUID_GROUPS.finditer(line):
                lengths = tuple(len(g) for g in m.group(0).split('-'))
                if lengths != GROUP_LENGTHS and 28 <= sum(lengths) <= 36:
                    yield m.group(0), slot

    @staticmethod
    def recover(value: str, found_in: set, slots: dict) -> str | None:
        """A valid UUID used in the same slot that only differs in the broken groups"""
        groups = value.split('-')
        if len(groups) != 5:
            return None
        intact = [i for i, g in enumerate(groups) if re.fullmatch(f'[0-9a-fA-F]{{{GROUP_LENGTHS[i]}}}', g)]
        if len(intact) < 3:
            return None
        candidates = set()
        for slot in found_in:
            if slot is None:
                continue
            for valid in slots.get(slot, ()):
                vg = valid.split('-')
                if all(vg[i].lower() == groups[i].lower() for i in intact):
                    candidates.add(valid)
        return candidates.pop() if len(candidates) == 1 else None

    @staticmethod
    def replace(text: str, replacements: dict) -> str:
        if not any(v in text for v in replacements):
            return text
        pattern = re.compile(r'(?<![0-9A-Za-z-])(' + '|'.join(re.escape(v) for v in replacements) + r')(?![0-9A-Za-z-])')

        def sub(m):
            if HANDLE_CONTEXT.search(text[max(0, m.start() - 12):m.start()]):
                return m.group(0)
            return replacements[m.group(0)]
        return pattern.sub(sub, text)
