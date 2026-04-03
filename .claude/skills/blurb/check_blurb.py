#!/usr/bin/env python3
"""
Validate .blurb files against the 13 integrity checks defined in
check_blurb_validation_steps.md.

Usage: python3 check_blurb.py <blurb_file> [blurb_file2 ...]
Exit:  0 if all files pass (zero errors), 1 if any file has errors.
Warnings are reported but do not affect the exit code.
"""

import os
import re
import sys
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[0;33m"
RESET = "\033[0m"

FORBIDDEN_EXTS = {
    ".mp4", ".mov", ".avi", ".m4v", ".mkv", ".webm", ".flv", ".wmv", ".mpeg", ".mpg",
    ".raw", ".cr2", ".nef", ".arw", ".dng", ".orf", ".rw2", ".pef", ".raf", ".crw",
    ".sr2", ".mrw", ".dcr", ".x3f", ".erf", ".kdc", ".nrw", ".srf",
    ".gif", ".heic",
}

SKU_TO_COVER = {"-IW-": "imagewrap", "-SC-": "softcover", "-DJ-": "dustjacket"}
REQUIRED_COVERS = {"softcover", "imagewrap", "dustjacket"}


def _detect_cover_types(root):
    """Return set of cover type names found in the XML (by type= attr or SKU pattern)."""
    found = set()
    for c in root.findall("cover"):
        ct = c.get("type", "")
        if ct:
            found.add(ct)
        for pat, name in SKU_TO_COVER.items():
            if pat in c.get("sku", ""):
                found.add(name)
    return found


def check_blurb(path):
    """
    Run all 13 integrity checks on the given .blurb file.
    Returns (errors: list[str], warnings: list[str]).
    Errors indicate invalid files; warnings indicate possible issues.
    Checks 6 (metadata) and 13 (spine text) are warnings, not errors,
    because template files legitimately have empty/placeholder values.
    """
    errors = []
    warnings = []

    def err(msg):
        errors.append(msg)

    def warn(msg):
        warnings.append(msg)

    # ── 1. SQLite validity ────────────────────────────────────────────────────
    try:
        conn = sqlite3.connect(path)
        result = conn.execute("PRAGMA integrity_check").fetchone()
        if result[0] != "ok":
            err(f"SQLite integrity_check failed: {result[0]}")
            conn.close()
            return errors, warnings
    except Exception as e:
        err(f"Cannot open as SQLite database: {e}")
        return errors, warnings

    # ── 2. Required tables ────────────────────────────────────────────────────
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    for t in ("Files", "ArchiveVersion"):
        if t not in tables:
            err(f"Required table '{t}' is missing")

    if "Files" not in tables or "ArchiveVersion" not in tables:
        conn.close()
        return errors, warnings

    # ── 3. Archive version ────────────────────────────────────────────────────
    row = conn.execute("SELECT version FROM ArchiveVersion LIMIT 1").fetchone()
    if not row:
        err("ArchiveVersion table is empty")
    elif int(row[0]) != 4:
        warn(f"Archive version is {row[0]} (expected 4)")

    # ── 4. Required files ─────────────────────────────────────────────────────
    filepaths = {r[0] for r in conn.execute("SELECT filepath FROM Files")}
    for req in ("bbf2.xml", "project_settings.json", "media_registry.xml"):
        if req not in filepaths:
            err(f"Required file '{req}' is missing from archive")

    if "bbf2.xml" not in filepaths:
        conn.close()
        return errors, warnings

    # ── 5. bbf2.xml structure ─────────────────────────────────────────────────
    bbf2_blob = conn.execute(
        "SELECT filecontent FROM Files WHERE filepath='bbf2.xml'"
    ).fetchone()
    raw = bbf2_blob[0]
    bbf2_text = raw if isinstance(raw, str) else raw.decode("utf-8")

    try:
        root = ET.fromstring(bbf2_text)
    except ET.ParseError as e:
        err(f"bbf2.xml is not valid XML: {e}")
        conn.close()
        return errors, warnings

    if root.tag != "book":
        err(f"bbf2.xml root element is <{root.tag}> (expected <book>)")

    # ── 6. Metadata (WARN — templates have empty/placeholder values) ──────────
    info = root.find("info")
    title = ""
    if info is not None:
        title = (info.findtext("title") or "").strip()
        author = (info.findtext("author") or "").strip()
        if not title:
            warn("Book title is empty")
        if not author:
            warn("Book author is empty")
    else:
        warn("<info> section is missing")

    # ── 7. Protected elements ─────────────────────────────────────────────────
    masterpage = root.find("masterpage")
    if masterpage is None:
        err("<masterpage> section is missing")
    else:
        mp_pages = masterpage.findall("page")
        if len(mp_pages) < 2:
            err(f"<masterpage> has {len(mp_pages)} page(s) (expected >= 2)")

    found_covers = _detect_cover_types(root)
    for ct in REQUIRED_COVERS:
        if ct not in found_covers:
            err(f'<cover type="{ct}"> is missing')

    # ── 8. Page numbering ─────────────────────────────────────────────────────
    section = root.find('.//section[@name=""]') or root.find("section")
    if section is None:
        err("<section> element is missing")
    else:
        pages = section.findall("page")
        positive_nums = []
        for p in pages:
            n = p.get("number", "")
            if n.lstrip("-").isdigit() and int(n) > 0:
                positive_nums.append(int(n))

        if positive_nums:
            expected = list(range(1, len(positive_nums) + 1))
            dupes = [n for n in positive_nums if positive_nums.count(n) > 1]
            if dupes:
                err(f"Duplicate page numbers: {sorted(set(dupes))}")
            elif sorted(positive_nums) != expected:
                warn(f"Page numbers are not sequential 1–{len(positive_nums)}")

    # ── 9. Image references ───────────────────────────────────────────────────
    image_elements = root.findall('.//section//container[@type="image"]/image')
    archive_images = {f for f in filepaths if f.startswith("images/")}

    for img in image_elements:
        src = img.get("src", "")
        if not src:
            continue
        if "/" in src:
            err(f"Image src contains path separator: '{src}' (must be filename only)")
        else:
            if f"images/{src}" not in archive_images:
                err(f"Image '{src}' referenced in XML but not in archive")
        al = img.get("autolayout", "")
        if al != "fill":
            warn(f"Image '{src}' has autolayout='{al}' (expected 'fill')")

    # ── 10. Media registry ────────────────────────────────────────────────────
    # Only parse when images are actually present in pages — if there are no
    # image GUIDs in the section there is nothing to cross-check.
    page_guids = {img.get("guid") for img in image_elements if img.get("guid")}
    if page_guids and "media_registry.xml" in filepaths:
        mr_blob = conn.execute(
            "SELECT filecontent FROM Files WHERE filepath='media_registry.xml'"
        ).fetchone()
        mr_raw = mr_blob[0]
        mr_text = mr_raw if isinstance(mr_raw, str) else mr_raw.decode("utf-8")
        try:
            mr_root = ET.fromstring(mr_text)
            registry_guids = {
                m.get("guid") for m in mr_root.findall(".//media") if m.get("guid")
            }
            for g in page_guids - registry_guids:
                err(f"Image GUID '{g}' used in pages but missing from media registry")
        except ET.ParseError as e:
            err(f"media_registry.xml is not valid XML: {e}")

    # ── 11. File sizes ────────────────────────────────────────────────────────
    for row in conn.execute(
        "SELECT filepath, filesize, length(filecontent) FROM Files"
    ):
        fpath, declared, actual = row
        if declared is not None and declared != -1 and declared != actual:
            warn(f"'{fpath}': declared size {declared} != actual {actual}")

    # ── 12. Forbidden file types ──────────────────────────────────────────────
    for fp in filepaths:
        ext = Path(fp).suffix.lower()
        if ext in FORBIDDEN_EXTS:
            err(f"Forbidden file type in archive: '{fp}'")

    # ── 13. Spine text (WARN — templates use zero-width space placeholder) ────
    if title:
        for cover in root.findall("cover"):
            ct = cover.get("type", "")
            if not ct:
                for pat, name in SKU_TO_COVER.items():
                    if pat in cover.get("sku", ""):
                        ct = name
            if ct not in REQUIRED_COVERS:
                continue
            spine_parents = [
                x for x in (cover.find("spine"), cover.find("coversheet"))
                if x is not None
            ]
            for parent in spine_parents:
                for cont in parent.findall('.//container[@role="spineText"]'):
                    text_el = cont.find("text")
                    if text_el is not None and text_el.text:
                        raw_text = re.sub(r"<[^>]+>", "", text_el.text).strip()
                        if title.lower() not in raw_text.lower():
                            warn(f"{ct} spine does not contain title '{title}'")

    conn.close()
    return errors, warnings


def print_result(label, errors, warnings):
    """Print coloured check result for one file."""
    status = f"{RED}FAIL{RESET}" if errors else f"{GREEN}PASS{RESET}"
    print(f"\n[{status}] {label}")
    for e in errors:
        print(f"  {RED}ERROR{RESET}: {e}")
    for w in warnings:
        print(f"  {YELLOW}WARN{RESET}:  {w}")
    print(f"  {len(errors)} error(s), {len(warnings)} warning(s)")


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate .blurb files against the 13 integrity checks."
    )
    parser.add_argument("blurb_files", nargs="+", metavar="blurb_file",
                        help=".blurb file(s) to validate")
    args = parser.parse_args(argv)

    total_errors = 0
    for path in args.blurb_files:
        if not os.path.exists(path):
            print(f"{RED}ERROR{RESET}: File not found: {path}")
            total_errors += 1
            continue
        errors, warnings = check_blurb(path)
        print_result(os.path.basename(path), errors, warnings)
        total_errors += len(errors)

    print()
    if total_errors == 0:
        print(f"{GREEN}All files passed integrity check.{RESET}")
    else:
        print(f"{RED}{total_errors} total error(s) across all files.{RESET}")
    return 1 if total_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
