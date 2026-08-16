"""Compiles .po files to .mo without requiring the GNU gettext `msgfmt`
binary (unavailable in this environment) — a small, standard-library-only
implementation of the well-documented GNU MO binary format. Django's i18n
runtime itself is untouched; this only replaces the build step normally
done by `django-admin compilemessages`.

Usage: python scripts/compile_po.py locale/en/LC_MESSAGES/django.po ...
"""
import re
import struct
import sys


def parse_po(path):
    """Returns {msgid: msgstr} for a simple (non-plural, non-fuzzy) .po
    file using the quoted-string-per-entry style this project writes."""
    with open(path, encoding='utf-8') as f:
        content = f.read()

    entries = {}
    # Each entry: msgid "..." (possibly continued on following quoted
    # lines) then msgstr "..." likewise. Comments (#) are ignored.
    pattern = re.compile(
        r'msgid((?:\s*"(?:[^"\\]|\\.)*")+)\s*msgstr((?:\s*"(?:[^"\\]|\\.)*")+)',
        re.MULTILINE,
    )

    def unquote(raw):
        parts = re.findall(r'"((?:[^"\\]|\\.)*)"', raw)
        text = ''.join(parts)
        return (
            text.replace('\\n', '\n').replace('\\t', '\t')
            .replace('\\"', '"').replace('\\\\', '\\')
        )

    for match in pattern.finditer(content):
        msgid = unquote(match.group(1))
        msgstr = unquote(match.group(2))
        entries[msgid] = msgstr
    # Python's gettext module reads charset/metadata from the header entry
    # (empty msgid) to know how to decode everything else — it must be
    # present, or it defaults to ASCII and crashes on non-ASCII msgstrs.
    if '' not in entries:
        entries[''] = 'Content-Type: text/plain; charset=UTF-8\n'
    return entries


def write_mo(entries, path):
    """Standard GNU MO format: a hash-table-free simple implementation
    (linear string tables) — fully supported by Django/gettext readers."""
    keys = sorted(entries.keys())
    offsets = []
    ids = b''
    strs = b''
    for key in keys:
        value = entries[key]
        key_b = key.encode('utf-8')
        value_b = value.encode('utf-8')
        offsets.append((len(ids), len(key_b), len(strs), len(value_b)))
        ids += key_b + b'\x00'
        strs += value_b + b'\x00'

    keystart = 7 * 4 + 16 * len(keys)
    valuestart = keystart + len(ids)
    koffsets = []
    voffsets = []
    for o1, l1, o2, l2 in offsets:
        koffsets += [l1, o1 + keystart]
        voffsets += [l2, o2 + valuestart]
    offsets_data = koffsets + voffsets

    output = struct.pack(
        'Iiiiiii',
        0x950412de,        # magic
        0,                  # version
        len(keys),          # number of entries
        7 * 4,              # offset of table with original strings
        7 * 4 + len(keys) * 8,  # offset of table with translation strings
        0, 0,                # size and offset of hash table (unused)
    )
    output += struct.pack(f'{len(offsets_data)}i', *offsets_data)
    output += ids
    output += strs

    with open(path, 'wb') as f:
        f.write(output)


def main():
    for po_path in sys.argv[1:]:
        entries = parse_po(po_path)
        mo_path = po_path.rsplit('.po', 1)[0] + '.mo'
        write_mo(entries, mo_path)
        print(f'{po_path} -> {mo_path} ({len(entries)} entries)')


if __name__ == '__main__':
    main()
