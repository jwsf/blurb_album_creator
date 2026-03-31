#!/usr/bin/env python3
"""Python test harness for the image-batcher skill."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[0;33m"
RESET = "\033[0m"
STATE_FILE = Path("/tmp/image_batcher_state.json")


class TestHarness:
    def __init__(self) -> None:
        self.pass_count = 0
        self.fail_count = 0
        self.skip_count = 0
        self.script_dir = Path(__file__).resolve().parent
        self.batcher_script = self.script_dir / "batcher.py"
        self.test_root = Path(tempfile.mkdtemp())
        self._state_backup: str | None = None
        self._state_exists_before = STATE_FILE.exists()

    def setup(self) -> None:
        if self._state_exists_before:
            self._state_backup = STATE_FILE.read_text(encoding="utf-8")
        else:
            self._state_backup = None

    def cleanup(self) -> None:
        shutil.rmtree(self.test_root, ignore_errors=True)
        if self._state_exists_before:
            if self._state_backup is not None:
                STATE_FILE.write_text(self._state_backup, encoding="utf-8")
        else:
            try:
                STATE_FILE.unlink()
            except FileNotFoundError:
                pass

    def info(self, message: str) -> None:
        print(f"[INFO] {message}")

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

    def assert_contains(self, haystack: str, needle: str, message: str) -> None:
        if needle not in haystack:
            raise AssertionError(f"missing:  {needle}\n{message}")

    def assert_eq(self, expected: str, actual: str, message: str) -> None:
        if expected != actual:
            raise AssertionError(f"expected: {expected}\nactual:   {actual}\n{message}")

    def check_exiftool(self) -> bool:
        return shutil.which("exiftool") is not None

    def check_sips(self) -> bool:
        return shutil.which("sips") is not None

    def run_batcher(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        command = [sys.executable, str(self.batcher_script), *args]
        return subprocess.run(command, capture_output=True, text=True, check=check)

    def make_jpeg(self, output: Path) -> None:
        ppm = output.with_suffix(".ppm")
        ppm.write_text("P3\n1 1\n255\n255 255 255\n", encoding="utf-8")
        subprocess.run(
            ["sips", "-s", "format", "jpeg", str(ppm), "--out", str(output)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        ppm.unlink()

    def load_state(self) -> dict:
        if not STATE_FILE.exists():
            raise AssertionError("Expected state file to exist")
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))

    def setup_fixtures(self) -> None:
        # Date-folder mode fixtures
        (self.test_root / "dated/2026-01-01 Event").mkdir(parents=True, exist_ok=True)
        (self.test_root / "dated/2026-01-02").mkdir(parents=True, exist_ok=True)
        self.make_jpeg(self.test_root / "dated/2026-01-01 Event/a.jpg")
        self.make_jpeg(self.test_root / "dated/2026-01-01 Event/b.jpg")
        self.make_jpeg(self.test_root / "dated/2026-01-02/c.jpg")

        # Flat-directory fallback fixtures
        (self.test_root / "flat/sub").mkdir(parents=True, exist_ok=True)
        self.make_jpeg(self.test_root / "flat/cat_001.jpg")
        self.make_jpeg(self.test_root / "flat/cat_002.jpg")
        self.make_jpeg(self.test_root / "flat/sub/dog_001.jpg")

    def test_prereq_exiftool_present(self) -> None:
        if not self.check_exiftool():
            raise AssertionError("Expected exiftool to be present")

    def test_prereq_sips_present(self) -> None:
        if not self.check_sips():
            raise AssertionError("Expected sips to be present")

    def test_init_date_mode_creates_batches(self) -> None:
        result = self.run_batcher("init", str(self.test_root / "dated"), "--max-batch", "2")
        self.assert_contains(result.stdout, "Found 2 date folders", "Date mode should detect date folders")
        state = self.load_state()
        self.assert_eq("2", str(state["total_batches"]), "Expected 2 batches in date-folder mode")

    def test_get_batch_returns_current(self) -> None:
        result = self.run_batcher("get_batch")
        self.assert_contains(result.stdout, "Batch #1:", "Expected first batch details")

    def test_get_next_batch_advances(self) -> None:
        self.run_batcher("get_next_batch")
        state = self.load_state()
        self.assert_eq("1", str(state["current_batch_index"]), "Expected current_batch_index to advance")

    def test_reset_returns_to_first(self) -> None:
        self.run_batcher("reset")
        state = self.load_state()
        self.assert_eq("0", str(state["current_batch_index"]), "Reset should return to first batch")

    def test_flat_fallback_mode(self) -> None:
        result = self.run_batcher("init", str(self.test_root / "flat"), "--max-batch", "2")
        self.assert_contains(
            result.stdout,
            "Falling back to flat-directory mode",
            "Expected fallback mode when no date folders are present",
        )
        state = self.load_state()
        self.assert_eq("2", str(state["total_batches"]), "Expected 2 batches in flat-directory fallback")

    def test_init_missing_directory_fails(self) -> None:
        result = self.run_batcher("init", str(self.test_root / "does-not-exist"), check=False)
        if result.returncode == 0:
            raise AssertionError("Expected non-zero exit for missing directory")

    def run(self) -> int:
        self.info(f"Using test root: {self.test_root}")

        if not self.check_exiftool():
            print("ERROR: exiftool is required but not installed.")
            print("  macOS: brew install exiftool")
            print("  Linux: apt-get install libimage-exiftool-perl")
            return 1
        if not self.check_sips():
            print("ERROR: sips is required but not available (macOS only).")
            return 1

        self.setup_fixtures()

        self.run_test("Prereq exiftool present", self.test_prereq_exiftool_present)
        self.run_test("Prereq sips present", self.test_prereq_sips_present)
        self.run_test("Init date mode creates batches", self.test_init_date_mode_creates_batches)
        self.run_test("Get batch returns current", self.test_get_batch_returns_current)
        self.run_test("Get next batch advances", self.test_get_next_batch_advances)
        self.run_test("Reset returns to first", self.test_reset_returns_to_first)
        self.run_test("Flat fallback mode", self.test_flat_fallback_mode)
        self.run_test("Init missing directory fails", self.test_init_missing_directory_fails)

        print()
        print(f"Test summary: pass={self.pass_count} fail={self.fail_count} skip={self.skip_count}")
        return 0 if self.fail_count == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run image-batcher skill tests")
    parser.parse_args(argv)

    harness = TestHarness()
    harness.setup()
    try:
        return harness.run()
    finally:
        harness.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())