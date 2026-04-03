#!/usr/bin/env python3
"""Unit tests for check_blurb.py."""

from __future__ import annotations

import importlib.util
import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[0;33m"
RESET = "\033[0m"

SCRIPT_DIR = Path(__file__).resolve().parent

# ── Minimal valid XML fixtures ────────────────────────────────────────────────

VALID_BBF2 = """\
<?xml version="1.0" encoding="utf-8"?>
<book>
  <info>
    <title><![CDATA[Test Title]]></title>
    <author><![CDATA[Test Author]]></author>
  </info>
  <masterpage>
    <page number="-1" color="#ffffff"/>
    <page number="-1" color="#ffffff"/>
  </masterpage>
  <cover type="softcover">
    <spine><container role="spineText"><text><![CDATA[<p><span style="color:#000000;">Test Title</span></p>]]></text></container></spine>
  </cover>
  <cover type="imagewrap">
    <spine><container role="spineText"><text><![CDATA[<p><span style="color:#000000;">Test Title</span></p>]]></text></container></spine>
  </cover>
  <cover type="dustjacket">
    <spine><container role="spineText"><text><![CDATA[<p><span style="color:#000000;">Test Title</span></p>]]></text></container></spine>
  </cover>
  <section name="">
    <page number="1" color="#ffffff"/>
    <page number="2" color="#ffffff"/>
  </section>
</book>
"""

VALID_MEDIA_REGISTRY = """\
<?xml version="1.0" encoding="utf-8"?>
<medialist><images/></medialist>
"""

VALID_PROJECT_SETTINGS = "{}"


def _make_blurb(path, bbf2=VALID_BBF2, media_registry=VALID_MEDIA_REGISTRY,
                project_settings=VALID_PROJECT_SETTINGS, version=4,
                extra_files=None, skip_tables=False, skip_files=None):
    """
    Create a minimal valid .blurb SQLite file at *path*.
    Override individual components via keyword arguments.
    skip_files: set of filepath strings to omit from insertion.
    """
    if os.path.exists(path):
        os.remove(path)

    conn = sqlite3.connect(path)

    if not skip_tables:
        conn.execute(
            "CREATE TABLE Files "
            "(filepath TEXT UNIQUE, filecontent BLOB, filesize NUM, filedate TEXT)"
        )
        conn.execute("CREATE TABLE ArchiveVersion (version NUM)")
        conn.execute("INSERT INTO ArchiveVersion VALUES (?)", (version,))

    skip = skip_files or set()

    def insert(filepath, content):
        if filepath not in skip:
            data = content.encode("utf-8") if isinstance(content, str) else content
            conn.execute(
                "INSERT OR REPLACE INTO Files (filepath, filecontent, filesize, filedate) "
                "VALUES (?, ?, ?, datetime('now'))",
                (filepath, data, len(data)),
            )

    if bbf2 is not None:
        insert("bbf2.xml", bbf2)
    if media_registry is not None:
        insert("media_registry.xml", media_registry)
    if project_settings is not None:
        insert("project_settings.json", project_settings)

    for fp, content in (extra_files or {}).items():
        insert(fp, content)

    conn.commit()
    conn.close()


# ── Test harness ──────────────────────────────────────────────────────────────

class TestHarness:
    def __init__(self) -> None:
        self.pass_count = 0
        self.fail_count = 0
        self.skip_count = 0
        self.skill = self._load_module()

    def _load_module(self):
        spec = importlib.util.spec_from_file_location(
            "check_blurb", SCRIPT_DIR / "check_blurb.py"
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("Failed to load check_blurb module")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def run_test(self, name: str, fn) -> None:
        try:
            fn()
        except Exception as exc:
            print(f"  {name:<60} {RED}FAIL{RESET}")
            for line in str(exc).splitlines():
                print(f"    {line}")
            self.fail_count += 1
            return
        print(f"  {name:<60} {GREEN}PASS{RESET}")
        self.pass_count += 1

    def assert_no_errors(self, errors, warnings, context=""):
        if errors:
            raise AssertionError(
                f"Expected no errors{' (' + context + ')' if context else ''}, got: {errors}"
            )

    def assert_has_error(self, errors, fragment, context=""):
        matching = [e for e in errors if fragment.lower() in e.lower()]
        if not matching:
            raise AssertionError(
                f"Expected error containing '{fragment}'"
                f"{' (' + context + ')' if context else ''}.\nActual errors: {errors}"
            )

    def assert_has_warning(self, warnings, fragment, context=""):
        matching = [w for w in warnings if fragment.lower() in w.lower()]
        if not matching:
            raise AssertionError(
                f"Expected warning containing '{fragment}'"
                f"{' (' + context + ')' if context else ''}.\nActual warnings: {warnings}"
            )

    def assert_no_warnings(self, warnings, context=""):
        if warnings:
            raise AssertionError(
                f"Expected no warnings{' (' + context + ')' if context else ''}, got: {warnings}"
            )

    # ── Individual tests ──────────────────────────────────────────────────────

    def test_valid_blurb_passes(self):
        with tempfile.NamedTemporaryFile(suffix=".blurb", delete=False) as f:
            path = f.name
        try:
            _make_blurb(path)
            errors, warnings = self.skill.check_blurb(path)
            self.assert_no_errors(errors, warnings, "valid blurb")
        finally:
            os.unlink(path)

    def test_missing_files_table(self):
        with tempfile.NamedTemporaryFile(suffix=".blurb", delete=False) as f:
            path = f.name
        try:
            conn = sqlite3.connect(path)
            conn.execute("CREATE TABLE ArchiveVersion (version NUM)")
            conn.execute("INSERT INTO ArchiveVersion VALUES (4)")
            conn.commit()
            conn.close()
            errors, _ = self.skill.check_blurb(path)
            self.assert_has_error(errors, "Files", "missing Files table")
        finally:
            os.unlink(path)

    def test_missing_archive_version_table(self):
        with tempfile.NamedTemporaryFile(suffix=".blurb", delete=False) as f:
            path = f.name
        try:
            conn = sqlite3.connect(path)
            conn.execute(
                "CREATE TABLE Files "
                "(filepath TEXT UNIQUE, filecontent BLOB, filesize NUM, filedate TEXT)"
            )
            conn.commit()
            conn.close()
            errors, _ = self.skill.check_blurb(path)
            self.assert_has_error(errors, "ArchiveVersion", "missing ArchiveVersion table")
        finally:
            os.unlink(path)

    def test_wrong_archive_version_is_warning(self):
        with tempfile.NamedTemporaryFile(suffix=".blurb", delete=False) as f:
            path = f.name
        try:
            _make_blurb(path, version=3)
            errors, warnings = self.skill.check_blurb(path)
            self.assert_no_errors(errors, warnings, "wrong version should only warn")
            self.assert_has_warning(warnings, "version", "wrong version warning")
        finally:
            os.unlink(path)

    def test_missing_required_file(self):
        with tempfile.NamedTemporaryFile(suffix=".blurb", delete=False) as f:
            path = f.name
        try:
            _make_blurb(path, skip_files={"project_settings.json"})
            errors, _ = self.skill.check_blurb(path)
            self.assert_has_error(errors, "project_settings.json", "missing required file")
        finally:
            os.unlink(path)

    def test_invalid_bbf2_xml(self):
        with tempfile.NamedTemporaryFile(suffix=".blurb", delete=False) as f:
            path = f.name
        try:
            _make_blurb(path, bbf2="<this is not valid xml")
            errors, _ = self.skill.check_blurb(path)
            self.assert_has_error(errors, "not valid XML", "invalid bbf2.xml")
        finally:
            os.unlink(path)

    def test_empty_title_is_warning(self):
        with tempfile.NamedTemporaryFile(suffix=".blurb", delete=False) as f:
            path = f.name
        try:
            bbf2 = VALID_BBF2.replace(
                "<title><![CDATA[Test Title]]></title>",
                "<title><![CDATA[]]></title>",
            )
            _make_blurb(path, bbf2=bbf2)
            errors, warnings = self.skill.check_blurb(path)
            self.assert_no_errors(errors, warnings, "empty title should only warn")
            self.assert_has_warning(warnings, "title", "empty title warning")
        finally:
            os.unlink(path)

    def test_missing_masterpage_is_error(self):
        with tempfile.NamedTemporaryFile(suffix=".blurb", delete=False) as f:
            path = f.name
        try:
            bbf2 = re.sub(r"<masterpage>.*?</masterpage>", "", VALID_BBF2, flags=re.DOTALL)
            _make_blurb(path, bbf2=bbf2)
            errors, _ = self.skill.check_blurb(path)
            self.assert_has_error(errors, "masterpage", "missing masterpage")
        finally:
            os.unlink(path)

    def test_missing_cover_is_error(self):
        with tempfile.NamedTemporaryFile(suffix=".blurb", delete=False) as f:
            path = f.name
        try:
            bbf2 = re.sub(
                r'<cover type="softcover">.*?</cover>', "", VALID_BBF2, flags=re.DOTALL
            )
            _make_blurb(path, bbf2=bbf2)
            errors, _ = self.skill.check_blurb(path)
            self.assert_has_error(errors, "softcover", "missing softcover")
        finally:
            os.unlink(path)

    def test_image_src_with_path_is_error(self):
        with tempfile.NamedTemporaryFile(suffix=".blurb", delete=False) as f:
            path = f.name
        try:
            bbf2 = VALID_BBF2.replace(
                '<section name="">',
                '<section name=""><page number="1"><container type="image">'
                '<image src="images/GUID-123.jpg" autolayout="fill"/></container></page>',
            ).replace('<page number="1" color="#ffffff"/>', "")
            _make_blurb(
                path, bbf2=bbf2,
                extra_files={"images/GUID-123.jpg": b"fake"},
            )
            errors, _ = self.skill.check_blurb(path)
            self.assert_has_error(errors, "path separator", "image src with path")
        finally:
            os.unlink(path)

    def test_image_not_in_archive_is_error(self):
        with tempfile.NamedTemporaryFile(suffix=".blurb", delete=False) as f:
            path = f.name
        try:
            bbf2 = VALID_BBF2.replace(
                '<section name="">',
                '<section name=""><page number="1"><container type="image">'
                '<image src="MISSING.jpg" autolayout="fill"/></container></page>',
            ).replace('<page number="1" color="#ffffff"/>', "")
            _make_blurb(path, bbf2=bbf2)
            errors, _ = self.skill.check_blurb(path)
            self.assert_has_error(errors, "not in archive", "image not in archive")
        finally:
            os.unlink(path)

    def test_missing_autolayout_is_warning(self):
        with tempfile.NamedTemporaryFile(suffix=".blurb", delete=False) as f:
            path = f.name
        try:
            bbf2 = VALID_BBF2.replace(
                '<section name="">',
                '<section name=""><page number="1"><container type="image">'
                '<image src="GUID-abc.jpg"/></container></page>',
            ).replace('<page number="1" color="#ffffff"/>', "")
            _make_blurb(
                path, bbf2=bbf2,
                extra_files={"images/GUID-abc.jpg": b"fake"},
            )
            errors, warnings = self.skill.check_blurb(path)
            self.assert_no_errors(errors, warnings, "missing autolayout should only warn")
            self.assert_has_warning(warnings, "autolayout", "autolayout warning")
        finally:
            os.unlink(path)

    def test_non_sequential_pages_is_warning(self):
        with tempfile.NamedTemporaryFile(suffix=".blurb", delete=False) as f:
            path = f.name
        try:
            bbf2 = VALID_BBF2.replace(
                '<page number="2" color="#ffffff"/>',
                '<page number="5" color="#ffffff"/>',
            )
            _make_blurb(path, bbf2=bbf2)
            errors, warnings = self.skill.check_blurb(path)
            self.assert_no_errors(errors, warnings, "non-sequential pages should only warn")
            self.assert_has_warning(warnings, "sequential", "non-sequential warning")
        finally:
            os.unlink(path)

    def test_duplicate_page_numbers_is_error(self):
        with tempfile.NamedTemporaryFile(suffix=".blurb", delete=False) as f:
            path = f.name
        try:
            bbf2 = VALID_BBF2.replace(
                '<page number="2" color="#ffffff"/>',
                '<page number="1" color="#ffffff"/>',
            )
            _make_blurb(path, bbf2=bbf2)
            errors, _ = self.skill.check_blurb(path)
            self.assert_has_error(errors, "duplicate", "duplicate page numbers")
        finally:
            os.unlink(path)

    def test_forbidden_file_type_is_error(self):
        with tempfile.NamedTemporaryFile(suffix=".blurb", delete=False) as f:
            path = f.name
        try:
            _make_blurb(path, extra_files={"images/clip.mp4": b"fake video"})
            errors, _ = self.skill.check_blurb(path)
            self.assert_has_error(errors, "forbidden", "forbidden file type")
        finally:
            os.unlink(path)

    def test_invalid_media_registry_xml_is_error(self):
        with tempfile.NamedTemporaryFile(suffix=".blurb", delete=False) as f:
            path = f.name
        try:
            # Must have an image with a guid in the section so the registry is parsed
            bbf2 = VALID_BBF2.replace(
                '<section name="">',
                '<section name=""><page number="1"><container type="image">'
                '<image src="GUID-mr.jpg" guid="GUID-MR-001" autolayout="fill"/>'
                '</container></page>',
            ).replace('<page number="1" color="#ffffff"/>', "")
            _make_blurb(
                path, bbf2=bbf2,
                media_registry="<not valid xml",
                extra_files={"images/GUID-mr.jpg": b"fake"},
            )
            errors, _ = self.skill.check_blurb(path)
            self.assert_has_error(errors, "media_registry.xml", "invalid media registry")
        finally:
            os.unlink(path)

    def test_spine_mismatch_is_warning(self):
        with tempfile.NamedTemporaryFile(suffix=".blurb", delete=False) as f:
            path = f.name
        try:
            bbf2 = VALID_BBF2.replace(
                "Test Title</span>", "Wrong Title</span>"
            )
            _make_blurb(path, bbf2=bbf2)
            errors, warnings = self.skill.check_blurb(path)
            self.assert_no_errors(errors, warnings, "spine mismatch should only warn")
            self.assert_has_warning(warnings, "spine", "spine mismatch warning")
        finally:
            os.unlink(path)

    # ── Runner ────────────────────────────────────────────────────────────────

    def run(self) -> int:
        tests = [
            ("Valid blurb passes all checks",               self.test_valid_blurb_passes),
            ("Missing Files table → error",                 self.test_missing_files_table),
            ("Missing ArchiveVersion table → error",        self.test_missing_archive_version_table),
            ("Wrong archive version → warning only",        self.test_wrong_archive_version_is_warning),
            ("Missing required file → error",               self.test_missing_required_file),
            ("Invalid bbf2.xml → error",                    self.test_invalid_bbf2_xml),
            ("Empty title → warning only",                  self.test_empty_title_is_warning),
            ("Missing masterpage → error",                  self.test_missing_masterpage_is_error),
            ("Missing cover type → error",                  self.test_missing_cover_is_error),
            ("Image src with path → error",                 self.test_image_src_with_path_is_error),
            ("Image not in archive → error",                self.test_image_not_in_archive_is_error),
            ("Missing autolayout → warning only",           self.test_missing_autolayout_is_warning),
            ("Non-sequential pages → warning only",         self.test_non_sequential_pages_is_warning),
            ("Duplicate page numbers → error",              self.test_duplicate_page_numbers_is_error),
            ("Forbidden file type → error",                 self.test_forbidden_file_type_is_error),
            ("Invalid media_registry.xml → error",          self.test_invalid_media_registry_xml_is_error),
            ("Spine title mismatch → warning only",         self.test_spine_mismatch_is_warning),
        ]
        for name, fn in tests:
            self.run_test(name, fn)

        print()
        print(
            f"Test summary: "
            f"pass={self.pass_count} fail={self.fail_count} skip={self.skip_count}"
        )
        return 0 if self.fail_count == 0 else 1


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Run check_blurb unit tests")
    parser.parse_args(argv)
    return TestHarness().run()


if __name__ == "__main__":
    raise SystemExit(main())
