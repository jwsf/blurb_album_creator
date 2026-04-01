#!/usr/bin/env python3
"""Python test harness for the blurb-to-pdf skill."""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path


GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[0;33m"
RESET = "\033[0m"


class TestHarness:
    def __init__(self) -> None:
        self.pass_count = 0
        self.fail_count = 0
        self.skip_count = 0
        self.script_dir = Path(__file__).resolve().parent
        self.skill_script = self.script_dir / "blurb_to_pdf.py"
        self.test_root = Path(tempfile.mkdtemp())

    def cleanup(self) -> None:
        shutil.rmtree(self.test_root, ignore_errors=True)

    def run_test(self, name: str, fn) -> None:
        try:
            fn()
        except Exception as exc:
            print(f"  {name:<52} {RED}FAIL{RESET}")
            for line in str(exc).splitlines():
                print(f"    {line}")
            self.fail_count += 1
            return
        print(f"  {name:<52} {GREEN}PASS{RESET}")
        self.pass_count += 1

    def skip(self, name: str, reason: str) -> None:
        print(f"  {name:<52} {YELLOW}SKIP{RESET}")
        print(f"    {reason}")
        self.skip_count += 1

    def assert_contains(self, haystack: str, needle: str, message: str) -> None:
        if needle not in haystack:
            raise AssertionError(f"missing:  {needle}\n{message}")

    def run_skill(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        command = [sys.executable, str(self.skill_script), *args]
        return subprocess.run(command, capture_output=True, text=True, check=check)

    def check_sqlite3(self) -> bool:
        return shutil.which("sqlite3") is not None

    def check_pdf_stack(self) -> bool:
        result = subprocess.run(
            [sys.executable, "-c", "import reportlab, PIL"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0

    def create_minimal_blurb(self, target: Path) -> None:
        conn = sqlite3.connect(str(target))
        try:
            cur = conn.cursor()
            cur.execute("CREATE TABLE ArchiveVersion(version NUM)")
            cur.execute("INSERT INTO ArchiveVersion(version) VALUES (4)")
            cur.execute(
                "CREATE TABLE Files(filepath TEXT UNIQUE, filecontent BLOB, filesize NUM, filedate TEXT)"
            )
            bbf2 = (
                '<book width="576" height="576">'
                '<info><title><![CDATA[Test Book]]></title><author><![CDATA[Test Author]]></author></info>'
                '<masterpage><page number="-1" color="#ffffff"/><page number="-1" color="#ffffff"/></masterpage>'
                '<cover type="softcover">'
                '<front width="576" height="576" color="#eeeeee"/>'
                '<back width="576" height="576" color="#dddddd"/>'
                '</cover>'
                '<section name="">'
                '<page number="1" color="#ffffff"/>'
                '</section>'
                '</book>'
            )
            cur.execute(
                "INSERT INTO Files(filepath, filecontent, filesize, filedate) VALUES (?, ?, ?, datetime('now'))",
                ("bbf2.xml", bbf2.encode("utf-8"), len(bbf2)),
            )
            conn.commit()
        finally:
            conn.close()

    def test_usage_requires_argument(self) -> None:
        result = self.run_skill(check=False)
        if result.returncode == 0:
            raise AssertionError("Expected non-zero exit without arguments")
        self.assert_contains(result.stdout + result.stderr, "Usage:", "Expected usage output")

    def test_rejects_non_blurb_extension(self) -> None:
        invalid = self.test_root / "not-a-blurb.txt"
        invalid.write_text("x", encoding="utf-8")
        result = self.run_skill(str(invalid), check=False)
        if result.returncode == 0:
            raise AssertionError("Expected non-zero exit for non-.blurb path")
        self.assert_contains(result.stdout + result.stderr, "ERROR: File must have .blurb extension", "Expected extension guard")

    def test_minimal_conversion_creates_pdf(self) -> None:
        source = self.test_root / "minimal.blurb"
        self.create_minimal_blurb(source)

        result = self.run_skill(str(source), check=False)
        if result.returncode != 0:
            raise AssertionError(f"Expected successful conversion\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")

        output_pdf = source.with_suffix(".pdf")
        if not output_pdf.exists():
            raise AssertionError("Expected output PDF to be created")
        if output_pdf.stat().st_size <= 0:
            raise AssertionError("Expected output PDF to be non-empty")

    def run(self) -> int:
        if not self.check_sqlite3():
            print("ERROR: sqlite3 is required but not installed.")
            return 1

        self.run_test("Usage requires argument", self.test_usage_requires_argument)
        self.run_test("Reject non-blurb extension", self.test_rejects_non_blurb_extension)

        if self.check_pdf_stack():
            self.run_test("Minimal conversion creates PDF", self.test_minimal_conversion_creates_pdf)
        else:
            self.skip("Minimal conversion creates PDF", "reportlab and pillow are not installed")

        print()
        print(f"Test summary: pass={self.pass_count} fail={self.fail_count} skip={self.skip_count}")
        return 0 if self.fail_count == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run blurb-to-pdf skill tests")
    parser.parse_args(argv)

    harness = TestHarness()
    try:
        return harness.run()
    finally:
        harness.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
