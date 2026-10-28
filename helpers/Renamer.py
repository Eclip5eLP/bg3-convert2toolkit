import re

# Whole names only and case-sensitive: "Target_Fireball" never matches inside "Target_Fireball_Trap"
TOKEN = re.compile(r'[A-Za-z0-9_]+')
# Parts that must never be renamed: icons may share a name with an entry, level maps may be base game ones
PROTECTED = [
    re.compile(r'LevelMapValue\(\s*[^()]*\)'),
    re.compile(r'<attribute\b[^>]*\bid="Icon"[^>]*>', re.IGNORECASE),
    re.compile(r'^\s*data\s+"Icon"\s+"[^"]*"', re.MULTILINE),
]


def rewrite_text(text: str, renames: dict) -> tuple[str, int]:
    """Replaces renamed names in text, returns (new text, number of replacements)"""
    if not renames or not (set(TOKEN.findall(text)) & renames.keys()):
        return text, 0
    count = 0

    def sub(m):
        nonlocal count
        new = renames.get(m.group(0))
        if new is None:
            return m.group(0)
        count += 1
        return new

    spans = sorted(m.span() for p in PROTECTED for m in p.finditer(text))
    out, last = [], 0
    for start, end in spans:
        if start < last:
            continue
        out.append(TOKEN.sub(sub, text[last:start]))
        out.append(text[start:end])
        last = end
    out.append(TOKEN.sub(sub, text[last:]))
    return ''.join(out), count


def find_names(text: str, names) -> list[tuple[int, str]]:
    """(line, name) of every occurrence of one of names"""
    names = set(names)
    if not names or not (set(TOKEN.findall(text)) & names):
        return []
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        for token in dict.fromkeys(TOKEN.findall(line)):
            if token in names:
                hits.append((i, token))
    return hits
