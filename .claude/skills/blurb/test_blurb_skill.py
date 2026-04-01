#!/usr/bin/env python3
"""Python test harness for the blurb skill helpers."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from xml.etree import ElementTree as ET


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
        self.skill_script = self.script_dir / "add_batches_to_blurb.py"
        self.skill = self._load_skill_module()

    def _load_skill_module(self):
        spec = importlib.util.spec_from_file_location("blurb_skill", self.skill_script)
        if spec is None or spec.loader is None:
            raise RuntimeError("Failed to load blurb skill module")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

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

    def assert_eq(self, expected: str, actual: str, message: str) -> None:
        if expected != actual:
            raise AssertionError(f"expected: {expected}\nactual:   {actual}\n{message}")

    def assert_contains(self, haystack: str, needle: str, message: str) -> None:
        if needle not in haystack:
            raise AssertionError(f"missing:  {needle}\n{message}")

    def test_container_orientation(self) -> None:
        portrait = ET.fromstring('<container width="100" height="300"/>')
        landscape = ET.fromstring('<container width="300" height="100"/>')
        square = ET.fromstring('<container width="100" height="102"/>')
        self.assert_eq("portrait", self.skill.get_container_orientation(portrait), "Expected portrait detection")
        self.assert_eq("landscape", self.skill.get_container_orientation(landscape), "Expected landscape detection")
        self.assert_eq("square", self.skill.get_container_orientation(square), "Expected square detection")

    def test_find_best_template_size(self) -> None:
        self.assert_eq("3", str(self.skill.find_best_template_size(3, {1, 2, 3, 5})), "Exact size should match")
        self.assert_eq("5", str(self.skill.find_best_template_size(4, {1, 2, 3, 5})), "Should choose next available size")
        self.assert_eq("5", str(self.skill.find_best_template_size(8, {1, 2, 3, 5})), "Should clamp to max size")

    def test_assign_images_orientation_first(self) -> None:
        imgs = [
            {"width": 600, "height": 1200, "path": "p1.jpg", "guid": "g1"},
            {"width": 700, "height": 1400, "path": "p2.jpg", "guid": "g2"},
            {"width": 1600, "height": 900, "path": "l1.jpg", "guid": "g3"},
        ]
        assigned = self.skill.assign_images_to_containers_by_orientation(imgs, ["portrait", "landscape", "portrait"])
        got = [img["path"] for img in assigned]
        self.assert_eq("p1.jpg", got[0], "Portrait slot should prefer portrait image")
        self.assert_eq("l1.jpg", got[1], "Landscape slot should prefer landscape image")
        self.assert_eq("p2.jpg", got[2], "Second portrait slot should use remaining portrait image")

    def test_fill_page_xml_sets_images_and_text(self) -> None:
        page_xml = (
            '<page number="1" id="page-old">'
            '<container type="image" id="c1" width="100" height="100">'
            '<image src="old.jpg" autolayout="fit"/></container>'
            '<container type="text" id="c2"><text><![CDATA[<p><span>Original text</span></p>]]></text></container>'
            '</page>'
        )
        images = [{"path": "images/new_one.jpg", "guid": "guid-1"}]
        updated = self.skill.fill_page_xml(page_xml, 42, images)
        self.assert_contains(updated, 'number="42"', "Page number should be updated")
        self.assert_contains(updated, 'src="new_one.jpg"', "Image src should be rewritten to filename")
        self.assert_contains(updated, 'autolayout="fill"', "Image autolayout should be forced to fill")
        self.assert_contains(updated, 'guid="guid-1"', "Image guid should be inserted")
        self.assert_contains(updated, "Lorem ipsum", "Visible text should be replaced")

    def test_replace_text_only_template_pages(self) -> None:
        raw_xml = (
            '<book><section name="">'
            '<page number="1"><container type="text"><text><![CDATA[<p><span>Keep?</span></p>]]></text></container></page>'
            '<page number="3"><container type="text"><text><![CDATA[<p><span>Stay</span></p>]]></text></container></page>'
            '</section></book>'
        )
        updated = self.skill.replace_text_on_template_pages(raw_xml, 1)
        self.assert_contains(updated, "Lorem ipsum", "Template page text should be replaced")
        self.assert_contains(updated, "Stay", "Non-template pages should remain unchanged")

    def test_build_media_entry_escapes_src(self) -> None:
        img = {
            "height": 100,
            "width": 200,
            "guid": "g-123",
            "ext": "jpg",
            "path": 'images/a&b"c.jpg',
        }
        entry = self.skill.build_media_entry(img)
        self.assert_contains(entry, "a&amp;b&quot;c.jpg", "Media entry should XML-escape src attribute")

    def run(self) -> int:
        self.run_test("Container orientation parsing", self.test_container_orientation)
        self.run_test("Best template size selection", self.test_find_best_template_size)
        self.run_test("Orientation-first image assignment", self.test_assign_images_orientation_first)
        self.run_test("Fill page XML updates images/text", self.test_fill_page_xml_sets_images_and_text)
        self.run_test("Replace text only template pages", self.test_replace_text_only_template_pages)
        self.run_test("Media entry escapes src", self.test_build_media_entry_escapes_src)

        print()
        print(f"Test summary: pass={self.pass_count} fail={self.fail_count} skip={self.skip_count}")
        return 0 if self.fail_count == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run blurb skill tests")
    parser.parse_args(argv)

    harness = TestHarness()
    return harness.run()


if __name__ == "__main__":
    raise SystemExit(main())
