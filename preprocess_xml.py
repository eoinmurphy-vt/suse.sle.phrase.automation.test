"""Prepare one DocBook XML or entity (.ent) file for Phrase TMS.

Usage: python preprocess_xml.py source/<client-id>/path/to/file.xml

Phrase TMS reads the DocBook files with the XML file import settings in the
project template. This step makes sure the files are UTF-8 with Unix newlines,
leaves out files that must not be translated, warns about files Phrase TMS
would import incorrectly, and protects entity references inside attribute
values (version="&productnumber;" becomes version="{{ent:productnumber}}"),
because Phrase TMS would otherwise drop them. postprocess_xml.py restores them.
"""
import datetime
import os
import sys

import l10n_common as common

SRC_DIR = os.getenv("SRC_DIR", "source")
DST_DIR = os.getenv("DST_DIR", "processed")
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
run_id = os.getenv("GITHUB_RUN_ID", "local")
LOG_FILE = f"{LOG_DIR}/preprocess_log_{timestamp}_{run_id}.txt"


def log(msg: str):
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as logf:
        logf.write(msg + "\n")


def main():
    if len(sys.argv) < 2:
        log("ERROR: No input file provided.")
        sys.exit(1)

    src_file = sys.argv[1]
    if not os.path.isfile(src_file):
        log(f"ERROR: File does not exist: {src_file}")
        sys.exit(1)

    kind = common.file_kind(src_file)
    if kind is None:
        log(f"⏭ Skipped (not sent for translation): {src_file}")
        return

    log(f"Starting preprocess: {src_file}")

    text, reencoded = common.read_text(src_file, log)
    text = common.to_lf(text)

    if kind == "xml":
        if reencoded:
            text = common.declare_utf8(text)
        error = common.check_wellformed(text)
        if error:
            log(f"⚠ Warning: XML is not well-formed, Phrase TMS may reject it: {error}")
        # Phrase TMS drops entity references from attribute values; postprocess_xml.py restores them
        text, protected = common.protect_attr_entities(text)
        if protected:
            log(f"Protected {protected} entity reference(s) in attribute values")
    else:
        for line in common.check_ent(text):
            log(f"⚠ Warning: line will NOT be imported by Phrase TMS (not a single-line <!ENTITY name \"value\">): {line}")

    # Compute output path (mirror directory structure)
    rel_path = os.path.relpath(src_file, SRC_DIR)
    out_path = os.path.join(DST_DIR, rel_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

    log(f"Saved processed file → {out_path}")
    log(f"Completed at {datetime.datetime.now()}\n")


if __name__ == "__main__":
    main()
