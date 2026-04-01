#!/usr/bin/env python3
"""Python implementation for the image metadata skill."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Iterable, Sequence


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".tiff", ".tif", ".webp"}
USER_AGENT = "BlurbAlbumCreator/1.0"


def _run_command(command: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, capture_output=True, text=True, check=check)
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        raise RuntimeError(message) from exc


def check_exiftool() -> bool:
    return shutil.which("exiftool") is not None


def require_exiftool() -> None:
    if not check_exiftool():
        raise RuntimeError(
            "exiftool is not installed. Install it with 'brew install exiftool' on macOS."
        )


def _exiftool_lines(image: str | Path, *tags: str, numeric: bool = False) -> list[str]:
    require_exiftool()
    command = ["exiftool", "-api", "MissingTagValue="]
    if numeric:
        command.append("-n")
    command.extend(tags)
    command.extend(["-s3", str(image)])
    result = _run_command(command)
    return result.stdout.splitlines()


def _exiftool_value(image: str | Path, tag: str, *, numeric: bool = False) -> str:
    lines = _exiftool_lines(image, tag, numeric=numeric)
    if not lines:
        return ""
    return lines[0].strip()


def write_location(image: str | Path, location: str) -> None:
    require_exiftool()
    _run_command(["exiftool", "-overwrite_original", f"-IPTC:City={location}", str(image)])


def read_cached_location(image: str | Path) -> str:
    return _exiftool_value(image, "-IPTC:City")


def has_cached_location(image: str | Path) -> bool:
    return bool(read_cached_location(image))


def clear_location_cache(image: str | Path) -> None:
    require_exiftool()
    _run_command(["exiftool", "-overwrite_original", "-IPTC:City=", str(image)])


def parse_people(value: str) -> list[str]:
    if not value:
        return []
    normalized = value.replace(";", ",")
    return [part.strip() for part in normalized.split(",") if part.strip()]


def read_people(image: str | Path) -> list[str]:
    return parse_people(_exiftool_value(image, "-RegionName"))


def read_datetime_original(image: str | Path) -> str:
    return _exiftool_value(image, "-DateTimeOriginal")


def get_coordinates(image: str | Path) -> tuple[str, str]:
    lines = _exiftool_lines(image, "-GPSLatitude", "-GPSLongitude", numeric=True)
    if len(lines) < 2:
        return "", ""
    return lines[0].strip(), lines[1].strip()


def get_coordinates_safe(image: str | Path) -> str:
    image_path = Path(image)
    if not image_path.is_file():
        raise ValueError(f"File not found: {image}")

    lat_text, lon_text = get_coordinates(image)
    if not lat_text or not lon_text:
        raise ValueError("Image does not contain valid GPS coordinates")

    lat = float(lat_text)
    lon = float(lon_text)
    if lat < -90 or lat > 90:
        raise ValueError(f"Invalid latitude: {lat_text}")
    if lon < -180 or lon > 180:
        raise ValueError(f"Invalid longitude: {lon_text}")

    return f"{lat_text},{lon_text}"


def pick_place_from_json_text(payload: str) -> str:
    obj = json.loads(payload)
    address = obj.get("address", {})
    return (
        address.get("village")
        or address.get("town")
        or address.get("city")
        or address.get("suburb")
        or address.get("county")
        or address.get("state")
        or address.get("country")
        or "Unknown"
    )


def _log_geocode_call(geocode_log: str | None) -> None:
    if geocode_log:
        with open(geocode_log, "a", encoding="utf-8") as handle:
            handle.write("call\n")


def get_place_name_mock(lat: float, lon: float, geocode_log: str | None = None) -> str:
    _log_geocode_call(geocode_log)
    if abs(lat - 37.7749) < 0.01 and abs(lon - (-122.4194)) < 0.01:
        return "San Francisco"
    if abs(lat - 37.8044) < 0.01 and abs(lon - (-122.2712)) < 0.01:
        return "Oakland"
    if abs(lat - 40.748817) < 0.01 and abs(lon - (-73.985428)) < 0.01:
        return "Manhattan"
    return "Unknown"


def get_place_name_live(lat: float, lon: float, geocode_log: str | None = None) -> str:
    _log_geocode_call(geocode_log)
    time.sleep(1)
    params = urllib.parse.urlencode(
        {
            "format": "json",
            "lat": lat,
            "lon": lon,
            "zoom": 18,
            "addressdetails": 1,
        }
    )
    request = urllib.request.Request(
        f"https://nominatim.openstreetmap.org/reverse?{params}",
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return "Unknown"
    try:
        return pick_place_from_json_text(payload)
    except json.JSONDecodeError:
        return "Unknown"


def get_place_name(
    lat: float | str,
    lon: float | str,
    *,
    geocoder: str = "live",
    geocode_log: str | None = None,
) -> str:
    lat_value = float(lat)
    lon_value = float(lon)
    if geocoder == "mock":
        return get_place_name_mock(lat_value, lon_value, geocode_log)
    return get_place_name_live(lat_value, lon_value, geocode_log)


def require_directory(directory: str | Path) -> Path:
    directory_path = Path(directory)
    if not directory_path.exists():
        raise ValueError(f"Directory not found: {directory}")
    if not directory_path.is_dir():
        raise ValueError(f"Path is not a directory: {directory}")
    return directory_path


def prepare_output_path(output_file: str | Path) -> Path:
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path


def iter_images(directory: str | Path, *, recursive: bool) -> Iterable[Path]:
    directory_path = require_directory(directory)
    iterator = directory_path.rglob("*") if recursive else directory_path.iterdir()
    for path in sorted(iterator):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            yield path


def infer_directory_location(
    directory: str | Path,
    *,
    geocoder: str = "live",
    geocode_log: str | None = None,
) -> str:
    counts: dict[str, int] = {}
    for image in iter_images(directory, recursive=False):
        lat_text, lon_text = get_coordinates(image)
        if not lat_text or not lon_text:
            continue
        place = get_place_name(lat_text, lon_text, geocoder=geocoder, geocode_log=geocode_log)
        counts[place] = counts.get(place, 0) + 1

    if not counts:
        return "Unknown"
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def get_location(
    image: str | Path,
    *,
    geocoder: str = "live",
    geocode_log: str | None = None,
) -> str:
    cached = read_cached_location(image)
    if cached:
        return cached

    lat_text, lon_text = get_coordinates(image)
    if lat_text and lon_text:
        place = get_place_name(lat_text, lon_text, geocoder=geocoder, geocode_log=geocode_log)
        if place != "Unknown":
            write_location(image, place)
        return place

    place = infer_directory_location(Path(image).parent, geocoder=geocoder, geocode_log=geocode_log)
    if place != "Unknown":
        write_location(image, place)
    return place


def generate_caption(
    image: str | Path,
    *,
    geocoder: str = "live",
    geocode_log: str | None = None,
) -> str:
    people = read_people(image)
    place = get_location(image, geocoder=geocoder, geocode_log=geocode_log)

    caption = ""
    if len(people) == 1:
        caption = people[0]
    elif len(people) == 2:
        caption = f"{people[0]} and {people[1]}"
    elif len(people) > 2:
        caption = f"{', '.join(people[:-1])}, and {people[-1]}"

    if place != "Unknown":
        return f"{caption} in {place}" if caption else place
    return caption


def analyze_image(
    image: str | Path,
    *,
    geocoder: str = "live",
    geocode_log: str | None = None,
) -> str:
    people = ", ".join(read_people(image)) or "none"
    place = get_location(image, geocoder=geocoder, geocode_log=geocode_log)
    date_taken = read_datetime_original(image) or "unknown"
    lines = [
        f"File: {image}",
        f"People: {people}",
        f"Location: {place}",
        f"Date taken: {date_taken}",
    ]
    return "\n".join(lines)


def analyze_directory(
    directory: str | Path,
    output_file: str | Path,
    *,
    geocoder: str = "live",
    geocode_log: str | None = None,
) -> None:
    directory_path = require_directory(directory)
    output_path = prepare_output_path(output_file)
    report_lines = [
        "Image Analysis Report",
        f"Directory: {directory_path}",
        "",
    ]
    inferred_directory_location = ""

    for image in iter_images(directory_path, recursive=False):
        people = ", ".join(read_people(image)) or "(none)"
        lat_text, lon_text = get_coordinates(image)
        date_taken = read_datetime_original(image)
        place = read_cached_location(image)
        if not place:
            if lat_text and lon_text:
                place = get_place_name(lat_text, lon_text, geocoder=geocoder, geocode_log=geocode_log)
                if place != "Unknown":
                    write_location(image, place)
            else:
                if not inferred_directory_location:
                    inferred_directory_location = infer_directory_location(
                        directory_path, geocoder=geocoder, geocode_log=geocode_log
                    )
                place = inferred_directory_location
                if place != "Unknown":
                    write_location(image, place)

        report_lines.extend(
            [
                f"--- {image.name} ---",
                f"People: {people}",
                (
                    f"Location: {place} (GPS: {lat_text}, {lon_text})"
                    if lat_text and lon_text
                    else f"Location: {place} (inferred)"
                ),
                f"Date: {date_taken}" if date_taken else "Date: unknown",
                "",
            ]
        )

    output_path.write_text("\n".join(report_lines), encoding="utf-8")


def export_metadata_csv(directory: str | Path, output_file: str | Path) -> None:
    require_directory(directory)
    output_path = prepare_output_path(output_file)
    fieldnames = ["SourceFile", "FileName", "RegionName", "GPSPosition", "DateTimeOriginal"]
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for image in iter_images(directory, recursive=True):
            lat_text, lon_text = get_coordinates(image)
            writer.writerow(
                {
                    "SourceFile": str(image),
                    "FileName": image.name,
                    "RegionName": ", ".join(read_people(image)),
                    "GPSPosition": f"{lat_text}, {lon_text}" if lat_text and lon_text else "",
                    "DateTimeOriginal": read_datetime_original(image),
                }
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Image metadata helper")
    parser.add_argument("--geocoder", choices=["live", "mock"], default=os.getenv("IMAGE_SKILL_GEOCODER", "live"))
    parser.add_argument("--geocode-log")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("check-exiftool")

    parser_write = subparsers.add_parser("write-location")
    parser_write.add_argument("image")
    parser_write.add_argument("location")

    parser_read = subparsers.add_parser("read-cached-location")
    parser_read.add_argument("image")

    parser_has = subparsers.add_parser("has-cached-location")
    parser_has.add_argument("image")

    parser_clear = subparsers.add_parser("clear-location-cache")
    parser_clear.add_argument("image")

    subparsers.add_parser("pick-place-from-json")

    parser_place = subparsers.add_parser("get-place-name")
    parser_place.add_argument("lat", type=float)
    parser_place.add_argument("lon", type=float)

    parser_infer = subparsers.add_parser("infer-directory-location")
    parser_infer.add_argument("directory")

    parser_location = subparsers.add_parser("get-location")
    parser_location.add_argument("image")

    parser_caption = subparsers.add_parser("generate-caption")
    parser_caption.add_argument("image")

    parser_coords = subparsers.add_parser("get-coordinates-safe")
    parser_coords.add_argument("image")

    parser_analyze = subparsers.add_parser("analyze-image")
    parser_analyze.add_argument("image")

    parser_analyze_dir = subparsers.add_parser("analyze-directory")
    parser_analyze_dir.add_argument("directory")
    parser_analyze_dir.add_argument("output_file")

    parser_csv = subparsers.add_parser("export-metadata-csv")
    parser_csv.add_argument("directory")
    parser_csv.add_argument("output_file")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "check-exiftool":
            return 0 if check_exiftool() else 1
        if args.command == "write-location":
            write_location(args.image, args.location)
            return 0
        if args.command == "read-cached-location":
            value = read_cached_location(args.image)
            if value:
                print(value)
                return 0
            return 1
        if args.command == "has-cached-location":
            return 0 if has_cached_location(args.image) else 1
        if args.command == "clear-location-cache":
            clear_location_cache(args.image)
            return 0
        if args.command == "pick-place-from-json":
            print(pick_place_from_json_text(sys.stdin.read()))
            return 0
        if args.command == "get-place-name":
            print(
                get_place_name(
                    args.lat,
                    args.lon,
                    geocoder=args.geocoder,
                    geocode_log=args.geocode_log,
                )
            )
            return 0
        if args.command == "infer-directory-location":
            print(
                infer_directory_location(
                    args.directory,
                    geocoder=args.geocoder,
                    geocode_log=args.geocode_log,
                )
            )
            return 0
        if args.command == "get-location":
            print(get_location(args.image, geocoder=args.geocoder, geocode_log=args.geocode_log))
            return 0
        if args.command == "generate-caption":
            print(generate_caption(args.image, geocoder=args.geocoder, geocode_log=args.geocode_log))
            return 0
        if args.command == "get-coordinates-safe":
            print(get_coordinates_safe(args.image))
            return 0
        if args.command == "analyze-image":
            print(analyze_image(args.image, geocoder=args.geocoder, geocode_log=args.geocode_log))
            return 0
        if args.command == "analyze-directory":
            analyze_directory(
                args.directory,
                args.output_file,
                geocoder=args.geocoder,
                geocode_log=args.geocode_log,
            )
            return 0
        if args.command == "export-metadata-csv":
            export_metadata_csv(args.directory, args.output_file)
            return 0
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    parser.error(f"Unhandled command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())