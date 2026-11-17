"""Shared helpers for the DocBook XML / entity (.ent) localization pipeline.

Used by preprocess_xml.py and postprocess_xml.py.
"""
import fnmatch
import os
import re
import xml.etree.ElementTree as ET

# --- WHICH FILES GO TO PHRASE TMS ---
# XML files that are never translated (editor schema-location files).
SKIP_FILES = [n.strip() for n in os.getenv("SKIP_FILES", "schemas.xml").split(",") if n.strip()]
# Only the localizable entity files are translated. This must stay in line with the
# "Filename and extension (regexp)" of the Phrase TMS custom file type (l10n-.*\.ent).
ENT_PATTERN = os.getenv("ENT_PATTERN", "l10n-*.ent")

# The Phrase TMS custom file type imports the text between the quotes of lines
# that look like this. Anything else in an .ent file is not imported.
ENT_LINE_RE = re.compile(r'^<!ENTITY\s+(\S+)\s+"(.*)">\s*$')

_DOCTYPE_RE = re.compile(r'<!DOCTYPE[^\[>]*(?:\[.*?\]\s*)?>', re.DOTALL)
_ENTITY_REF_RE = re.compile(r'&(?!(?:lt|gt|amp|quot|apos);|#)([A-Za-z_][\w.\-]*);')
_COMMENT_RE = re.compile(r'<!--.*?-->', re.DOTALL)
_XML_DECL_ENCODING_RE = re.compile(r'(<\?xml[^>]*?encoding\s*=\s*)(["\'])[^"\']*\2')


# A start tag with its attributes (comments, CDATA, processing instructions and the
# DOCTYPE never match because the name must start right after "<").
_START_TAG_RE = re.compile(r'<[A-Za-z_][\w:.\-]*(?:\s+[\w:.\-]+\s*=\s*(?:"[^"<]*"|\'[^\'<]*\'))+\s*/?>')
_SKIP_MARKUP_RE = re.compile(r'<!--.*?-->|<!\[CDATA\[.*?\]\]>|<\?.*?\?>', re.DOTALL)
_ATTR_ENTITY_PLACEHOLDER_RE = re.compile(r'\{\{ent:([A-Za-z_][\w.\-]*)\}\}')


def protect_attr_entities(text):
    """Replace &name; inside attribute values by {{ent:name}}.

    Phrase TMS keeps custom entity references in text, but silently drops them
    from attribute values (version="&productnumber;" comes back as version="").
    Returns (text, number_of_replacements).
    """
    count = 0

    def in_tag(m):
        nonlocal count
        tag, n = _ENTITY_REF_RE.subn(lambda e: "{{ent:" + e.group(1) + "}}", m.group(0))
        count += n
        return tag

    # Walk the document so that comments, CDATA sections and the DOCTYPE are left alone.
    out, pos = [], 0
    doctype = _DOCTYPE_RE.search(text)
    skip = [(m.start(), m.end()) for m in _SKIP_MARKUP_RE.finditer(text)]
    if doctype:
        skip.append((doctype.start(), doctype.end()))
    for start, end in sorted(skip):
        if start < pos:
            continue
        out.append(_START_TAG_RE.sub(in_tag, text[pos:start]))
        out.append(text[start:end])
        pos = end
    out.append(_START_TAG_RE.sub(in_tag, text[pos:]))
    return "".join(out), count


def restore_attr_entities(text):
    """Undo protect_attr_entities(). Returns (text, number_of_replacements)."""
    return _ATTR_ENTITY_PLACEHOLDER_RE.subn(r"&\1;", text)


def file_kind(path):
    """Return 'xml', 'ent' or None (None = not sent for translation)."""
    name = os.path.basename(path)
    if name.endswith(".xml"):
        return None if name in SKIP_FILES else "xml"
    if name.endswith(".ent"):
        return "ent" if fnmatch.fnmatch(name, ENT_PATTERN) else None
    return None


def read_text(path, log):
    """Read a file as text. Strict UTF-8 first (prevents mojibake), chardet as fallback.

    Returns (text, used_fallback).
    """
    with open(path, "rb") as f:
        raw = f.read()
    try:
        return raw.decode("utf-8"), False
    except UnicodeDecodeError:
        pass

    import chardet  # only needed for files that are not valid UTF-8

    info = chardet.detect(raw)
    encoding = info.get("encoding") or "utf-8"
    try:
        text = raw.decode(encoding)
        log(f"⚠ Warning: {path} read using fallback encoding {encoding} ({info.get('confidence', 0):.2f})")
    except Exception:
        log(f"⚠ Decode failed ({encoding}), forcing UTF-8 replacement: {path}")
        text = raw.decode("utf-8", errors="replace")
    return text, True


def to_lf(text):
    """Force Unix newlines. Nothing else is touched: tabs, non-breaking spaces and
    trailing spaces can be significant inside <screen> and <programlisting>."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def declare_utf8(text):
    """Make the XML declaration say UTF-8 (used when a file had to be re-encoded)."""
    return _XML_DECL_ENCODING_RE.sub(r"\1\2UTF-8\2", text, count=1)


_XML_DECL_RE = re.compile(r'^(﻿?)(<\?xml\s[^>]*?\?>)?')
_NON_UTF8_DECL_RE = re.compile(r'encoding\s*=\s*["\'](?!utf-?8["\'])', re.IGNORECASE)


def match_xml_declaration(text, reference):
    """Give the translated file the same XML declaration as the English source.

    Phrase TMS adds <?xml version='1.0' encoding='UTF-8'?> to files that have no
    declaration. Returns (text, action) where action is None, 'removed',
    'restored' or 'added'.
    """
    bom, decl = _XML_DECL_RE.match(text).groups()
    rest = text[len(bom) + len(decl or ""):]
    ref_decl = _XML_DECL_RE.match(reference).group(2)
    if decl == ref_decl:
        return text, None
    if ref_decl is None:
        return bom + rest, "removed"
    if _NON_UTF8_DECL_RE.search(ref_decl):
        # The delivered file is UTF-8; do not put back a declaration that says otherwise.
        return text, None
    if decl is None:
        return bom + ref_decl + "\n" + rest, "added"
    return bom + ref_decl + rest, "restored"


def doctype_of(text):
    """Return the DOCTYPE declaration (with internal subset) or None."""
    m = _DOCTYPE_RE.search(text)
    return m.group(0) if m else None


def entity_refs(text):
    """Return the sorted list of custom entity references (&name;) in the body."""
    body = _DOCTYPE_RE.sub("", text, count=1)
    return sorted(_ENTITY_REF_RE.findall(body))


def check_wellformed(text):
    """Return None if the XML is well-formed, otherwise an error message.

    The files load their entities from an external .ent file that the parser
    cannot see, so the DOCTYPE is blanked and custom entity references are
    replaced by filler of the same length. Line and column numbers in the
    error message therefore still point at the right place in the file.
    """
    blank = lambda m: re.sub(r"[^\n]", " ", m.group(0))
    probe = _DOCTYPE_RE.sub(blank, text.lstrip("﻿"), count=1)
    probe = _ENTITY_REF_RE.sub(lambda m: "x" * len(m.group(0)), probe)
    try:
        ET.fromstring(probe.encode("utf-8"))
    except ET.ParseError as e:
        return str(e)
    return None


def check_ent(text):
    """Return the lines of an .ent file that Phrase TMS would not import.

    Every line outside a comment must be a single-line <!ENTITY name "value">.
    """
    bad = []
    for line in _COMMENT_RE.sub("", text).splitlines():
        if line.strip() and not ENT_LINE_RE.match(line):
            bad.append(line.strip())
    return bad


def entity_names(text):
    """Return the entity names declared in an .ent file, in order."""
    names = []
    for line in _COMMENT_RE.sub("", text).splitlines():
        m = ENT_LINE_RE.match(line)
        if m:
            names.append(m.group(1))
    return names
