#!/usr/bin/env python3
"""Python test harness for the image-metadata-utils skill."""

from __future__ import annotations

import argparse
import csv
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


class TestHarness:
    def __init__(self, use_live_geocoder: bool) -> None:
        self.use_live_geocoder = use_live_geocoder
        self.pass_count = 0
        self.fail_count = 0
        self.skip_count = 0
        self.script_dir = Path(__file__).resolve().parent
        self.skill_script = self.script_dir / "image_metadata_utils.py"
        self.test_root = Path(tempfile.mkdtemp())
        self.geocode_call_log = Path(tempfile.mkstemp()[1])

    def cleanup(self) -> None:
        shutil.rmtree(self.test_root, ignore_errors=True)
        try:
            self.geocode_call_log.unlink()
        except FileNotFoundError:
            pass

    def info(self, message: str) -> None:
        print(f"[INFO] {message}")

    def skip(self, name: str) -> None:
        print(f"  {name:<52} {YELLOW}SKIP{RESET}")
        self.skip_count += 1

    def assert_eq(self, expected: str, actual: str, message: str) -> None:
        if expected != actual:
            raise AssertionError(f"expected: {expected}\nactual:   {actual}\n{message}")

    def assert_contains(self, haystack: str, needle: str, message: str) -> None:
        if needle not in haystack:
            raise AssertionError(f"missing:  {needle}\n{message}")

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

    def check_exiftool(self) -> bool:
        return shutil.which("exiftool") is not None

    def check_sips(self) -> bool:
        return shutil.which("sips") is not None

    def run_skill(self, *args: str, stdin: str | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
        command = [sys.executable, str(self.skill_script)]
        if self.use_live_geocoder:
            command.extend(["--geocoder", "live"])
        else:
            command.extend(["--geocoder", "mock", "--geocode-log", str(self.geocode_call_log)])
        command.extend(args)
        return subprocess.run(command, input=stdin, capture_output=True, text=True, check=check)

    def make_image(self, output: Path, fmt: str) -> None:
        ppm = output.with_suffix(".ppm")
        ppm.write_text("P3\n1 1\n255\n255 255 255\n", encoding="utf-8")
        subprocess.run(
            ["sips", "-s", "format", fmt, str(ppm), "--out", str(output)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        ppm.unlink()

    def make_jpeg(self, output: Path) -> None:
        self.make_image(output, "jpeg")

    def make_png(self, output: Path) -> None:
        self.make_image(output, "png")

    def run_exiftool(self, *args: str) -> None:
        subprocess.run(["exiftool", *args], check=True, stdout=subprocess.DEVNULL)

    def set_region_name(self, file_path: Path, value: str) -> None:
        self.run_exiftool("-overwrite_original", f"-RegionName={value}", str(file_path))

    def set_datetime_original(self, file_path: Path, value: str) -> None:
        self.run_exiftool("-overwrite_original", f"-DateTimeOriginal={value}", str(file_path))

    def set_gps(self, file_path: Path, lat: float, lon: float) -> None:
        lat_ref = "S" if lat < 0 else "N"
        lon_ref = "W" if lon < 0 else "E"
        self.run_exiftool(
            "-overwrite_original",
            f"-GPSLatitude={abs(lat)}",
            f"-GPSLatitudeRef={lat_ref}",
            f"-GPSLongitude={abs(lon)}",
            f"-GPSLongitudeRef={lon_ref}",
            str(file_path),
        )

    def setup_fixtures(self) -> None:
        for relative in [
            "gps-city-a",
            "gps-mixed",
            "no-gps",
            "mixed",
            "unknown-gps",
            "nested/day1",
            "nested/day2",
            "people",
        ]:
            (self.test_root / relative).mkdir(parents=True, exist_ok=True)

        self.make_jpeg(self.test_root / "gps-city-a/sf_1.jpg")
        self.make_jpeg(self.test_root / "gps-city-a/sf_2.jpg")
        self.make_jpeg(self.test_root / "gps-city-a/sf_3.jpg")
        self.make_jpeg(self.test_root / "gps-mixed/sf_4.jpg")
        self.make_jpeg(self.test_root / "gps-mixed/oak_1.jpg")
        self.make_jpeg(self.test_root / "gps-mixed/oak_2.jpg")
        self.make_jpeg(self.test_root / "no-gps/no_1.jpg")
        self.make_jpeg(self.test_root / "no-gps/no_2.jpg")
        self.make_jpeg(self.test_root / "mixed/m_1.jpg")
        self.make_jpeg(self.test_root / "mixed/m_2.jpg")
        self.make_jpeg(self.test_root / "unknown-gps/u_1.jpg")
        self.make_jpeg(self.test_root / "nested/day1/n1.jpg")
        self.make_jpeg(self.test_root / "nested/day2/n2.jpg")
        self.make_png(self.test_root / "people/p_1.png")
        self.make_jpeg(self.test_root / "people/p_2.jpg")

        self.set_gps(self.test_root / "gps-city-a/sf_1.jpg", 37.7749, -122.4194)
        self.set_gps(self.test_root / "gps-city-a/sf_2.jpg", 37.7749, -122.4194)
        self.set_gps(self.test_root / "gps-city-a/sf_3.jpg", 37.7749, -122.4194)
        self.set_gps(self.test_root / "gps-mixed/sf_4.jpg", 37.7749, -122.4194)
        self.set_gps(self.test_root / "gps-mixed/oak_1.jpg", 37.8044, -122.2712)
        self.set_gps(self.test_root / "gps-mixed/oak_2.jpg", 37.8044, -122.2712)
        self.set_gps(self.test_root / "mixed/m_1.jpg", 40.748817, -73.985428)
        self.set_gps(self.test_root / "unknown-gps/u_1.jpg", 0.12345, 0.54321)
        self.set_gps(self.test_root / "nested/day1/n1.jpg", 37.7749, -122.4194)
        self.set_gps(self.test_root / "nested/day2/n2.jpg", 37.7749, -122.4194)
        self.set_region_name(self.test_root / "people/p_1.png", "John Doe")
        self.set_region_name(self.test_root / "people/p_2.jpg", "John Doe, Jane Smith; Bob Jones")
        self.set_datetime_original(self.test_root / "people/p_2.jpg", "2025:10:14 13:30:00")

    def geocode_calls(self) -> int:
        return len(self.geocode_call_log.read_text(encoding="utf-8").splitlines())

    def reset_geocode_calls(self) -> None:
        self.geocode_call_log.write_text("", encoding="utf-8")

    def test_prereq_exiftool_present(self) -> None:
        result = self.run_skill("check-exiftool", check=False)
        if result.returncode != 0:
            raise AssertionError("Expected exiftool check to succeed")

    def test_prereq_exiftool_missing_path(self) -> None:
        command = [sys.executable, str(self.skill_script), "check-exiftool"]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            env={**os.environ, "PATH": "/nonexistent"},
            check=False,
        )
        if result.returncode == 0:
            raise AssertionError("Expected exiftool check to fail with empty PATH")

    def test_location_cache_write_read_clear(self) -> None:
        image = self.test_root / "no-gps/no_1.jpg"
        self.run_skill("write-location", str(image), "Testville")
        got = self.run_skill("read-cached-location", str(image)).stdout.strip()
        self.assert_eq("Testville", got, "Cache read should match write")
        if self.run_skill("has-cached-location", str(image), check=False).returncode != 0:
            raise AssertionError("Expected cached location to exist")
        self.run_skill("clear-location-cache", str(image))
        if self.run_skill("has-cached-location", str(image), check=False).returncode == 0:
            raise AssertionError("Expected cached location to be cleared")

    def test_place_priority_parser(self) -> None:
        payload = (
            '{"address":{"country":"USA","state":"California","county":"San Francisco County",'
            '"city":"San Francisco","town":"TownX","village":"VillageY"}}'
        )
        place = self.run_skill("pick-place-from-json", stdin=payload).stdout.strip()
        self.assert_eq("VillageY", place, "Village should win in priority order")

    def test_get_location_cache_first(self) -> None:
        image = self.test_root / "no-gps/no_2.jpg"
        self.reset_geocode_calls()
        self.run_skill("write-location", str(image), "CachedPlace")
        loc = self.run_skill("get-location", str(image)).stdout.strip()
        self.assert_eq("CachedPlace", loc, "Cache-first lookup should return IPTC city")
        self.assert_eq("0", str(self.geocode_calls()), "Cache hit should avoid geocoding")

    def test_get_location_geocode_and_cache(self) -> None:
        image = self.test_root / "gps-city-a/sf_1.jpg"
        self.reset_geocode_calls()
        self.run_skill("clear-location-cache", str(image))
        loc = self.run_skill("get-location", str(image)).stdout.strip()
        cached = self.run_skill("read-cached-location", str(image)).stdout.strip()
        self.assert_eq("San Francisco", loc, "GPS geocode should resolve to San Francisco")
        self.assert_eq("San Francisco", cached, "Location should be cached to IPTC:City")
        if self.geocode_calls() < 1:
            raise AssertionError(f"Expected at least 1 geocode call, got {self.geocode_calls()}")

    def test_infer_directory_location_majority(self) -> None:
        loc = self.run_skill("infer-directory-location", str(self.test_root / "gps-mixed")).stdout.strip()
        self.assert_eq("Oakland", loc, "Majority location should be selected")

    def test_infer_directory_location_unknown(self) -> None:
        loc = self.run_skill("infer-directory-location", str(self.test_root / "no-gps")).stdout.strip()
        self.assert_eq("Unknown", loc, "No GPS in directory should return Unknown")

    def test_get_location_directory_inference(self) -> None:
        src = self.test_root / "mixed/m_2.jpg"
        gps_peer = self.test_root / "mixed/m_1.jpg"
        self.reset_geocode_calls()
        self.run_skill("clear-location-cache", str(src))
        self.run_skill("clear-location-cache", str(gps_peer))
        loc = self.run_skill("get-location", str(src)).stdout.strip()
        self.assert_eq("Manhattan", loc, "Non-GPS image should infer from folder peers")
        if self.geocode_calls() < 1:
            raise AssertionError(f"Expected at least 1 geocode call, got {self.geocode_calls()}")

    def test_get_location_unknown_not_cached(self) -> None:
        image = self.test_root / "unknown-gps/u_1.jpg"
        self.run_skill("clear-location-cache", str(image))
        loc = self.run_skill("get-location", str(image)).stdout.strip()
        self.assert_eq("Unknown", loc, "Unmapped GPS should return Unknown")
        if self.run_skill("has-cached-location", str(image), check=False).returncode == 0:
            raise AssertionError("Unknown must not be cached in IPTC:City")

    def test_get_location_missing_file_clean_error(self) -> None:
        result = self.run_skill("get-location", str(self.test_root / "does-not-exist.jpg"), check=False)
        if result.returncode == 0:
            raise AssertionError("Expected get-location to fail for missing file")
        self.assert_contains(result.stderr, "ERROR:", "CLI should return a controlled error")
        if "Traceback" in result.stderr:
            raise AssertionError("CLI should not emit a Python traceback for missing files")

    def test_analyze_directory_inference_caches_location(self) -> None:
        directory = self.test_root / "mixed"
        target = directory / "m_2.jpg"
        output = self.test_root / "mixed_report.txt"
        self.reset_geocode_calls()
        self.run_skill("clear-location-cache", str(target))
        self.run_skill("clear-location-cache", str(directory / "m_1.jpg"))
        self.run_skill("analyze-directory", str(directory), str(output))
        cached = self.run_skill("read-cached-location", str(target)).stdout.strip()
        self.assert_eq("Manhattan", cached, "Directory analysis should cache inferred locations")

    def test_analyze_directory_missing_dir_clean_error(self) -> None:
        result = self.run_skill(
            "analyze-directory",
            str(self.test_root / "does-not-exist"),
            str(self.test_root / "out.txt"),
            check=False,
        )
        if result.returncode == 0:
            raise AssertionError("Expected analyze-directory to fail for missing directory")
        self.assert_contains(result.stderr, "ERROR:", "CLI should return a controlled error")
        if "Traceback" in result.stderr:
            raise AssertionError("CLI should not emit a Python traceback for missing directories")

    def test_analyze_directory_creates_output_parent(self) -> None:
        output = self.test_root / "reports/nested/out.txt"
        self.run_skill("analyze-directory", str(self.test_root / "mixed"), str(output))
        if not output.is_file():
            raise AssertionError("analyze-directory should create missing output parent directories")

    def test_generate_caption_single_person(self) -> None:
        image = self.test_root / "people/p_1.png"
        self.run_skill("write-location", str(image), "Waikiki")
        caption = self.run_skill("generate-caption", str(image)).stdout.strip()
        self.assert_eq("John Doe in Waikiki", caption, "Single person caption format")

    def test_generate_caption_three_people(self) -> None:
        image = self.test_root / "people/p_2.jpg"
        self.run_skill("write-location", str(image), "Honolulu")
        caption = self.run_skill("generate-caption", str(image)).stdout.strip()
        self.assert_contains(caption, "John Doe", "Caption should include first name")
        self.assert_contains(caption, "Jane Smith", "Caption should include second name")
        self.assert_contains(caption, "Bob Jones", "Caption should include third name")
        self.assert_contains(caption, "in Honolulu", "Caption should include location")

    def test_generate_caption_location_only(self) -> None:
        image = self.test_root / "no-gps/no_1.jpg"
        self.run_skill("clear-location-cache", str(image))
        self.run_skill("write-location", str(image), "OnlyPlace")
        caption = self.run_skill("generate-caption", str(image)).stdout.strip()
        self.assert_eq("OnlyPlace", caption, "No people should produce location-only caption")

    def test_generate_caption_dynamic_updates(self) -> None:
        image = self.test_root / "people/p_1.png"
        self.run_skill("write-location", str(image), "DynamicTown")
        first = self.run_skill("generate-caption", str(image)).stdout.strip()
        self.set_region_name(image, "John Doe, Jane Smith")
        second = self.run_skill("generate-caption", str(image)).stdout.strip()
        if first == second:
            raise AssertionError("Caption should change after updating people tags")
        self.assert_contains(second, "Jane Smith", "Caption should reflect updated people tags")

    def test_get_coordinates_safe_valid(self) -> None:
        image = self.test_root / "gps-city-a/sf_2.jpg"
        coords = self.run_skill("get-coordinates-safe", str(image)).stdout.strip()
        self.assert_contains(coords, ",", "Safe coordinate extraction should return lat,lon")

    def test_get_coordinates_safe_invalid_file(self) -> None:
        result = self.run_skill("get-coordinates-safe", str(self.test_root / "does-not-exist.jpg"), check=False)
        if result.returncode == 0:
            raise AssertionError("Expected get-coordinates-safe to fail for missing file")

    def test_analyze_image_output(self) -> None:
        output = self.run_skill("analyze-image", str(self.test_root / "people/p_2.jpg")).stdout
        self.assert_contains(output, "File:", "Analyze output should include file")
        self.assert_contains(output, "People:", "Analyze output should include people")
        self.assert_contains(output, "Location:", "Analyze output should include location")

    def test_csv_export_columns(self) -> None:
        csv_path = self.test_root / "out.csv"
        self.run_skill("export-metadata-csv", str(self.test_root), str(csv_path))
        with csv_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            header = reader.fieldnames or []
            rows = list(reader)
        header_text = ",".join(header)
        self.assert_contains(header_text, "SourceFile", "CSV should include SourceFile")
        self.assert_contains(header_text, "FileName", "CSV should include FileName")
        self.assert_contains(header_text, "RegionName", "CSV should include RegionName")
        nested_day1 = str(self.test_root / "nested/day1/n1.jpg")
        nested_day2 = str(self.test_root / "nested/day2/n2.jpg")
        exported_sources = {row["SourceFile"] for row in rows}
        if nested_day1 not in exported_sources or nested_day2 not in exported_sources:
            raise AssertionError("CSV export should include nested images recursively")

    def test_csv_export_missing_dir_clean_error(self) -> None:
        result = self.run_skill(
            "export-metadata-csv",
            str(self.test_root / "does-not-exist"),
            str(self.test_root / "out.csv"),
            check=False,
        )
        if result.returncode == 0:
            raise AssertionError("Expected export-metadata-csv to fail for missing directory")
        self.assert_contains(result.stderr, "ERROR:", "CLI should return a controlled error")
        if "Traceback" in result.stderr:
            raise AssertionError("CLI should not emit a Python traceback for missing directories")

    def test_csv_export_creates_output_parent(self) -> None:
        output = self.test_root / "exports/nested/out.csv"
        self.run_skill("export-metadata-csv", str(self.test_root), str(output))
        if not output.is_file():
            raise AssertionError("export-metadata-csv should create missing output parent directories")

    def run(self) -> int:
        self.info(f"Using test root: {self.test_root}")
        self.info(f"Geocoder mode: {'LIVE (Nominatim)' if self.use_live_geocoder else 'MOCK (deterministic/offline)'}")

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
        self.run_test("Prereq exiftool missing path", self.test_prereq_exiftool_missing_path)
        self.run_test("Location cache write/read/clear", self.test_location_cache_write_read_clear)
        self.run_test("Place priority parser", self.test_place_priority_parser)
        self.run_test("Get location cache-first", self.test_get_location_cache_first)
        self.run_test("Get location geocode and cache", self.test_get_location_geocode_and_cache)
        self.run_test("Infer directory location majority", self.test_infer_directory_location_majority)
        self.run_test("Infer directory location unknown", self.test_infer_directory_location_unknown)
        self.run_test("Get location directory inference", self.test_get_location_directory_inference)
        self.run_test("Get location unknown not cached", self.test_get_location_unknown_not_cached)
        self.run_test("Get location missing file clean error", self.test_get_location_missing_file_clean_error)
        self.run_test("Analyze directory inference caches", self.test_analyze_directory_inference_caches_location)
        self.run_test("Analyze directory missing dir clean error", self.test_analyze_directory_missing_dir_clean_error)
        self.run_test("Analyze directory creates output parent", self.test_analyze_directory_creates_output_parent)
        self.run_test("Generate caption single person", self.test_generate_caption_single_person)
        self.run_test("Generate caption three people", self.test_generate_caption_three_people)
        self.run_test("Generate caption location only", self.test_generate_caption_location_only)
        self.run_test("Generate caption dynamic updates", self.test_generate_caption_dynamic_updates)
        self.run_test("Safe coordinates valid", self.test_get_coordinates_safe_valid)
        self.run_test("Safe coordinates invalid file", self.test_get_coordinates_safe_invalid_file)
        self.run_test("Analyze image output", self.test_analyze_image_output)
        self.run_test("CSV export columns", self.test_csv_export_columns)
        self.run_test("CSV export missing dir clean error", self.test_csv_export_missing_dir_clean_error)
        self.run_test("CSV export creates output parent", self.test_csv_export_creates_output_parent)

        print()
        print(f"Test summary: pass={self.pass_count} fail={self.fail_count} skip={self.skip_count}")
        return 0 if self.fail_count == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run image-metadata-utils skill tests")
    parser.add_argument("--live", action="store_true", help="Use live Nominatim geocoding")
    args = parser.parse_args(argv)

    harness = TestHarness(use_live_geocoder=args.live)
    try:
        return harness.run()
    finally:
        harness.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())