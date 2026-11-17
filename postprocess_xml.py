"""Finalize translated DocBook XML and entity (.ent) files coming back from Phrase TMS.

Reads   translated/<phrase-locale>/<client-id>/path/to/file.xml
Writes  final/<client-id>/<language>/path/to/file.xml

For every file it:
  * converts to UTF-8 with Unix newlines
  * restores the entity references in attribute values that preprocess_xml.py protected
  * makes the XML declaration match the English source (Phrase TMS adds one to files without)
  * sets xml:lang to the target language (XML only)
  * checks the file is still well-formed; broken files are NOT delivered
  * warns if the DOCTYPE or the entity references differ from the English source
"""
import datetime
import os
import re
import sys
from pathlib import Path

import l10n_common as common

# --- CONFIGURATION ---
TARGET_PRODUCT = os.getenv('SPECIFIC_PRODUCT', '').strip()
SRC_DIR = os.getenv("SRC_DIR", "translated")
DST_DIR = os.getenv("DST_DIR", "final")
# English files as they were sent to Phrase TMS; used for the comparison checks.
REF_DIR = os.getenv("REF_DIR", "processed")
SET_XML_LANG = os.getenv("SET_XML_LANG", "true").lower() != "false"
LOG_DIR = "logs"

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(DST_DIR, exist_ok=True)

timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
run_id = os.getenv("GITHUB_RUN_ID", "local")
LOG_FILE = f"{LOG_DIR}/postprocess_log_{timestamp}_{run_id}.txt"

stats = {"processed": 0, "errors": 0, "skipped": 0, "warnings": 0}

XML_LANG_RE = re.compile(r'(xml:lang\s*=\s*)(["\'])en(?:[-_][A-Za-z]+)?\2')


def log(msg):
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def warn(msg):
    stats["warnings"] += 1
    log(f"⚠ {msg}")


def get_target_lang(phrase_folder):
    """
    Determines the target language code from the Phrase TMS locale folder.
    - Standard: the 2-letter language code SUSE delivers under (de_de -> de, pt_br -> pt, zh_cn -> zh)
    - Exceptions: see below
    """
    folder = phrase_folder.lower().replace("-", "_")

    # EXCEPTIONS: Phrase locales that are delivered under a different code.
    # Needed if two locales of one language are ever translated (for example zh_cn and zh_tw),
    # because both would otherwise be delivered to the same folder.
    exceptions = {}

    if folder in exceptions:
        return exceptions[folder]

    # DEFAULT: the language part of the locale (fr_fr -> fr)
    return folder.split("_")[0]


def split_path(rel: str):
    """
    Input structure from Phrase: translated/fr_fr/suse-repo-b/path/to/file.xml
    Returns (lang_code, repo_id, content_path) or None if the path is too short.
    """
    parts = rel.split(os.sep)
    if len(parts) < 3:
        return None
    return get_target_lang(parts[0]), parts[1], os.path.join(*parts[2:])


def finalize_xml(text, lang_code, reference, rel):
    """Return (text, error). error is set if the file must not be delivered."""
    # Put back the entity references that preprocess_xml.py protected in attribute values
    text, _ = common.restore_attr_entities(text)
    if reference is not None:
        reference, _ = common.restore_attr_entities(reference)
        # Phrase TMS adds an XML declaration to files that have none; follow the English source
        text, action = common.match_xml_declaration(text, reference)
        if action:
            log(f"XML declaration {action} to match the English source: {rel}")

    error = common.check_wellformed(text)
    if error:
        return text, f"not well-formed XML: {error}"

    if SET_XML_LANG:
        text = XML_LANG_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{lang_code}{m.group(2)}", text)

    if reference is not None:
        if common.doctype_of(text) != common.doctype_of(reference):
            warn(f"{rel}: DOCTYPE differs from the English source (entities may be undefined)")
        src_refs, tgt_refs = common.entity_refs(reference), common.entity_refs(text)
        if src_refs != tgt_refs:
            missing = sorted(set(r for r in src_refs if src_refs.count(r) > tgt_refs.count(r)))
            added = sorted(set(r for r in tgt_refs if tgt_refs.count(r) > src_refs.count(r)))
            warn(f"{rel}: entity references differ from the English source. Fewer: {missing or '-'}  More: {added or '-'}")
    return text, None


def finalize_ent(text, reference):
    """Return (text, error). error is set if the file must not be delivered."""
    bad = common.check_ent(text)
    if bad:
        return text, f"{len(bad)} line(s) are no longer valid <!ENTITY name \"value\"> declarations, first: {bad[0]}"
    if reference is not None and common.entity_names(text) != common.entity_names(reference):
        return text, "entity names differ from the English source"
    return text, None


# --- MAIN ---
with open(LOG_FILE, "w", encoding="utf-8") as f:
    f.write(f"Postprocess started: {datetime.datetime.now()}\n\n")

# FAIL-SAFE LOGIC
force_all = os.getenv("FORCE_ALL", "false").lower() == "true"
files_to_process = []

if force_all:
    # Manual override requested: process the whole directory
    files_to_process = [str(p) for p in Path(SRC_DIR).rglob("*") if p.is_file() and common.file_kind(str(p))]
    log("⚠ MANUAL OVERRIDE TRIGGERED: Processing ALL files.")
else:
    # Delta processing: Only read the files modified by Git
    try:
        with open("changed_files.txt", "r") as f:
            for line in f:
                filepath = line.strip()
                # Ensure the changed file is a translatable XML/ENT file inside the translated directory
                if common.file_kind(filepath) and filepath.startswith(SRC_DIR) and os.path.exists(filepath):
                    files_to_process.append(filepath)
    except FileNotFoundError:
        log("No changed_files.txt manifest found. Skipping delta processing.")

for src_path in sorted(files_to_process):
    rel = os.path.relpath(src_path, SRC_DIR)
    location = split_path(rel)

    if not location:
        log(f"⚠ Skipping invalid path depth: {rel}")
        stats["skipped"] += 1
        continue

    lang_code, repo_id, content_path = location

    # If a specific product was typed in, and this file doesn't match it, skip it
    if TARGET_PRODUCT and repo_id != TARGET_PRODUCT:
        stats["skipped"] += 1
        continue

    # Target structure: final / REPO_ID / LANG_CODE / CONTENT
    dst_path = os.path.join(DST_DIR, repo_id, lang_code, content_path)

    text, reencoded = common.read_text(src_path, log)
    text = common.to_lf(text)

    ref_path = os.path.join(REF_DIR, repo_id, content_path)
    reference = common.read_text(ref_path, log)[0] if os.path.isfile(ref_path) else None

    if common.file_kind(src_path) == "xml":
        if reencoded:
            text = common.declare_utf8(text)
        text, error = finalize_xml(text, lang_code, reference, rel)
    else:
        text, error = finalize_ent(text, reference)

    if error:
        stats["errors"] += 1
        log(f"❌ NOT DELIVERED: {rel}: {error}")
        continue

    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    with open(dst_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

    stats["processed"] += 1
    log(f"✓ Processed: {rel} -> {dst_path}")

log(f"\n=== Postprocess Complete ===")
log(f"Summary: Processed={stats['processed']}, Warnings={stats['warnings']}, Errors={stats['errors']}, Skipped={stats['skipped']}")

# A non-zero exit marks the workflow run as failed. The files that passed are still committed.
if stats["errors"]:
    sys.exit(1)
