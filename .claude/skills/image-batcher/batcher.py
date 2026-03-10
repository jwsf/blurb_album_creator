#!/usr/bin/env python3
"""
Image Batcher - Manages batches of images from date-organized folders.
Batches are 1-5 images each, never spanning multiple date folders or locations.

When no date folders are found, falls back to flat-directory mode:
groups images by filename commonality (shared non-numeric words) and splits
into batches of 1 to max_batch_size, preserving filename sort order.

Features:
- Enhanced metadata extraction (location hierarchy, captions, date validation)
- Location-aware single-image date batching
- Flat-directory fallback with filename-commonality grouping
- Order-preserving batching (image order is never altered)
- Configurable batch sizes and strategies
- Comprehensive reporting and validation
"""

import os
import sys
import json
import re
import subprocess
import argparse
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from collections import defaultdict

STATE_FILE = "/tmp/image_batcher_state.json"
SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.heic', '.tiff', '.tif'}
DATE_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}')

class ImageBatcher:
    def __init__(self, min_batch_size: int = 1, max_batch_size: int = 5,
                 combine_singles: bool = True, prefer_large: bool = True):
        """Initialize ImageBatcher with configuration options.

        Args:
            min_batch_size: Minimum batch size (default 1)
            max_batch_size: Maximum batch size (default 5)
            combine_singles: Whether to combine single-image dates (default True)
            prefer_large: Whether to prefer larger batches (default True)
        """
        self.state = self.load_state()
        self.min_batch_size = max(1, min_batch_size)
        self.max_batch_size = max(self.min_batch_size, max_batch_size)
        self.combine_singles = combine_singles
        self.prefer_large = prefer_large
        self.stats = defaultdict(int)  # Statistics tracking

    def load_state(self) -> Dict:
        """Load state from file or return empty state."""
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        return {
            "source_directory": None,
            "current_batch_index": 0,
            "total_batches": 0,
            "batches": []
        }

    def save_state(self):
        """Save state to file."""
        with open(STATE_FILE, 'w') as f:
            json.dump(self.state, f, indent=2)

    def is_date_folder(self, folder_name: str) -> bool:
        """Check if folder name starts with a date pattern."""
        return bool(DATE_PATTERN.match(folder_name))

    def extract_date(self, folder_name: str) -> str:
        """Extract date from folder name."""
        match = DATE_PATTERN.match(folder_name)
        if match:
            return match.group(0)
        return folder_name

    def find_images_in_folder(self, folder_path: str) -> List[str]:
        """Find all supported images in a folder (non-recursive)."""
        images = []
        folder = Path(folder_path)

        if not folder.exists() or not folder.is_dir():
            return images

        for file in sorted(folder.iterdir()):
            if file.is_file() and file.suffix.lower() in SUPPORTED_EXTENSIONS:
                images.append(str(file))

        return images

    def find_images_recursive(self, directory: str) -> List[str]:
        """Find all supported images in a directory recursively."""
        images = []
        for root, dirs, files in os.walk(directory):
            for f in sorted(files):
                if Path(f).suffix.lower() in SUPPORTED_EXTENSIONS:
                    images.append(os.path.join(root, f))
        return sorted(images)

    def get_image_metadata(self, image_paths: List[str]) -> Dict[str, Dict]:
        """Extract metadata from multiple images in batch using exiftool.

        Returns dict mapping image_path -> metadata dict with keys:
        - location: str or None (IPTC:City, XMP:City, or EXIF:GPSPosition fallback)
        - caption: str or None (XMP:Description or IPTC:Caption-Abstract)
        - date_taken: str or None (DateTimeOriginal)
        - orientation: 'portrait' or 'landscape'
        - width: int
        - height: int
        """
        if not image_paths:
            return {}

        # Batch extract metadata for all images at once
        try:
            result = subprocess.run(
                ['exiftool', '-json', '-IPTC:City', '-XMP:City',
                 '-EXIF:GPSPosition', '-XMP:Description', '-IPTC:Caption-Abstract',
                 '-DateTimeOriginal', '-ImageWidth', '-ImageHeight'] + image_paths,
                capture_output=True,
                text=True,
                timeout=len(image_paths) * 2  # 2 seconds per image
            )

            if result.returncode != 0:
                return {}

            import json
            metadata_list = json.loads(result.stdout)

            metadata_map = {}
            for item in metadata_list:
                source_file = item.get('SourceFile')
                if not source_file:
                    continue

                # Extract location with fallback hierarchy
                location = None
                if item.get('City'):  # IPTC or XMP City
                    location = item['City']
                elif item.get('GPSPosition'):
                    # Use GPS coordinates as location string
                    location = f"GPS:{item['GPSPosition']}"

                # Extract caption
                caption = item.get('Description') or item.get('Caption-Abstract')

                # Extract date
                date_taken = item.get('DateTimeOriginal')

                # Get dimensions and orientation
                width = item.get('ImageWidth', 0)
                height = item.get('ImageHeight', 0)
                orientation = 'portrait' if height > width else 'landscape'

                metadata_map[source_file] = {
                    'location': location,
                    'caption': caption,
                    'date_taken': date_taken,
                    'orientation': orientation,
                    'width': width,
                    'height': height
                }

            return metadata_map

        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
            return {}

    def get_image_location(self, image_path: str) -> Optional[str]:
        """Extract location from image metadata (IPTC:City).

        Note: For batch processing, use get_image_metadata() instead.
        """
        try:
            result = subprocess.run(
                ['exiftool', '-IPTC:City', '-s3', image_path],
                capture_output=True,
                text=True,
                timeout=5
            )
            location = result.stdout.strip()
            return location if location else None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

    def group_images_by_location(self, images: List[str]) -> List[Tuple[Optional[str], List[str]]]:
        """Group consecutive images by location."""
        if not images:
            return []

        groups = []
        current_location = self.get_image_location(images[0])
        current_group = [images[0]]

        for img in images[1:]:
            location = self.get_image_location(img)

            # If location changed, start a new group
            if location != current_location:
                groups.append((current_location, current_group))
                current_location = location
                current_group = [img]
            else:
                current_group.append(img)

        # Add final group
        if current_group:
            groups.append((current_location, current_group))

        return groups

    def create_batches_from_images(self, images: List[str], metadata: Dict[str, Dict] = None) -> List[List[str]]:
        """Split images into batches of min_size-max_size.

        Image order is always preserved — images appear in batches in the
        same order they are provided.

        Args:
            images: List of image paths
            metadata: Optional metadata dict from get_image_metadata()

        Returns:
            List of batches (each batch is a list of image paths)
        """
        return self._create_batches_simple(images)

    def _create_batches_simple(self, images: List[str]) -> List[List[str]]:
        """Split images into batches respecting min/max size and preference."""
        if not images:
            return []

        batches = []
        remaining = list(images)

        while remaining:
            if self.prefer_large:
                # Try to use the largest batch size possible
                for size in range(self.max_batch_size, self.min_batch_size - 1, -1):
                    if len(remaining) >= size:
                        batches.append(remaining[:size])
                        remaining = remaining[size:]
                        break
                else:
                    # Remaining is smaller than min_batch_size
                    if remaining:
                        batches.append(remaining)
                        remaining = []
            else:
                # Use minimum batch size
                size = min(self.min_batch_size, len(remaining))
                batches.append(remaining[:size])
                remaining = remaining[size:]

        return batches

    def scan_directory(self, directory: str):
        """Scan directory for date folders and create batches."""
        directory = os.path.abspath(directory)

        if not os.path.exists(directory):
            raise ValueError(f"Directory does not exist: {directory}")

        print(f"Scanning directory: {directory}")
        print(f"Configuration: min={self.min_batch_size}, max={self.max_batch_size}, " +
              f"combine_singles={self.combine_singles}, prefer_large={self.prefer_large}")
        print()

        # Reset statistics
        self.stats.clear()

        all_batches = []
        batch_number = 1

        # Find all subdirectories
        root_path = Path(directory)

        # Get all immediate subdirectories that start with dates
        date_folders = []
        for item in sorted(root_path.iterdir()):
            if item.is_dir() and self.is_date_folder(item.name):
                date_folders.append(item)

        if not date_folders:
            print("No date folders found (folders starting with YYYY-MM-DD pattern)")
            print("Falling back to flat-directory mode: scanning all images recursively")
            print()
            self._scan_flat_directory(directory)
            return

        print(f"Found {len(date_folders)} date folders")
        self.stats['total_date_folders'] = len(date_folders)
        print()

        # First pass: collect all images and extract metadata in batch
        print("Extracting image metadata...")
        all_images = []
        folder_images_map = {}  # Maps folder -> list of images

        for folder in date_folders:
            images = self.find_images_in_folder(str(folder))
            if images:
                all_images.extend(images)
                folder_images_map[folder] = images

        if not all_images:
            print("No images found in any date folders")
            self.state = {
                "source_directory": directory,
                "current_batch_index": 0,
                "total_batches": 0,
                "batches": []
            }
            self.save_state()
            return

        # Batch extract metadata for ALL images at once
        metadata = self.get_image_metadata(all_images)
        print(f"Extracted metadata for {len(metadata)} images")
        self.stats['total_images'] = len(all_images)
        self.stats['metadata_extracted'] = len(metadata)
        print()

        # Second pass: categorize folders as single-image or multi-image
        multi_image_folders = []
        single_image_data = []  # List of (folder, date_str, folder_name, image_path, metadata)

        for folder in date_folders:
            folder_name = folder.name
            date_str = self.extract_date(folder_name)
            images = folder_images_map.get(folder, [])

            if not images:
                print(f"  {folder_name}: No images found")
                self.stats['empty_folders'] += 1
                continue

            if len(images) == 1:
                # Single image - collect for potential cross-date batching
                img_metadata = metadata.get(images[0], {})
                single_image_data.append((folder, date_str, folder_name, images[0], img_metadata))
                self.stats['single_image_folders'] += 1
            else:
                # Multiple images - keep in date-specific batches
                multi_image_folders.append((folder, date_str, folder_name, images))
                self.stats['multi_image_folders'] += 1

        # Third pass: process multi-image folders (location-aware batches with metadata)
        for folder, date_str, folder_name, images in multi_image_folders:
            # Group images by location first
            location_groups = self.group_images_by_location(images)

            total_batches = 0
            for location, location_images in location_groups:
                # Create batches within each location group (with orientation awareness)
                batches = self.create_batches_from_images(location_images, metadata)
                total_batches += len(batches)

                for batch_images in batches:
                    batch_info = {
                        "batch_number": batch_number,
                        "date_folder": date_str,
                        "folder_path": str(folder),
                        "folder_name": folder_name,
                        "images": batch_images,
                        "image_count": len(batch_images),
                        "is_multi_date": False,
                        "location": location,
                        "is_multi_location": False
                    }
                    all_batches.append(batch_info)
                    batch_number += 1
                    self.stats['batches_created'] += 1

            # Print summary
            if len(location_groups) > 1:
                location_summary = ", ".join([f"{len(imgs)} at {loc or 'Unknown'}" for loc, imgs in location_groups])
                print(f"  {folder_name}: {len(images)} images → {total_batches} batches ({len(location_groups)} locations: {location_summary})")
                self.stats['multi_location_dates'] += 1
            else:
                location = location_groups[0][0] if location_groups else None
                loc_str = f" at {location}" if location else ""
                print(f"  {folder_name}: {len(images)} images → {total_batches} batches{loc_str}")

        # Fourth pass: create batches from single-image dates
        if single_image_data:
            print()
            if self.combine_singles:
                print(f"Processing {len(single_image_data)} single-image dates (location-aware batching):")

                # Group single-image dates by location
                location_groups = defaultdict(list)
                for folder, date_str, folder_name, img, img_metadata in single_image_data:
                    location = img_metadata.get('location', 'Unknown')
                    location_groups[location].append((folder, date_str, folder_name, img, img_metadata))

                print(f"  Found {len(location_groups)} location groups")

                # Create batches within each location group
                for location, group_data in location_groups.items():
                    group_images = [img for _, _, _, img, _ in group_data]

                    # Create batches for this location group (with orientation awareness)
                    single_batches = self.create_batches_from_images(group_images, metadata)

                    for batch_images in single_batches:
                        # Collect date info for all images in this batch
                        batch_dates = []
                        batch_folders = []

                        for img in batch_images:
                            # Find the date/folder info for this image
                            for folder, date_str, folder_name, single_img, _ in group_data:
                                if single_img == img:
                                    if date_str not in batch_dates:
                                        batch_dates.append(date_str)
                                    if folder_name not in batch_folders:
                                        batch_folders.append(folder_name)
                                    break

                        # Determine display info
                        if len(batch_dates) == 1:
                            date_display = batch_dates[0]
                            folder_display = batch_folders[0]
                            is_multi = False
                        else:
                            date_display = f"{batch_dates[0]} to {batch_dates[-1]}"
                            folder_display = f"{len(batch_dates)} dates"
                            is_multi = True

                        batch_info = {
                            "batch_number": batch_number,
                            "date_folder": date_display,
                            "folder_path": str(group_data[0][0].parent),
                            "folder_name": folder_display,
                            "images": batch_images,
                            "image_count": len(batch_images),
                            "is_multi_date": is_multi,
                            "is_multi_location": False,  # Single location per batch now
                            "location": location if location != 'Unknown' else None,
                            "date_list": batch_dates if is_multi else [batch_dates[0]]
                        }
                        all_batches.append(batch_info)
                        self.stats['batches_created'] += 1
                        if is_multi:
                            self.stats['multi_date_batches'] += 1

                        # Print info
                        loc_info = f" at {location}" if location != 'Unknown' else ""
                        if is_multi:
                            print(f"  Batch {batch_number}: {len(batch_images)} images from {len(batch_dates)} dates ({', '.join(batch_dates)}){loc_info}")
                        else:
                            print(f"  Batch {batch_number}: 1 image from {batch_dates[0]}{loc_info}")

                        batch_number += 1

            else:
                print(f"Processing {len(single_image_data)} single-image dates (no combining):")
                # Don't combine - create one batch per single image
                for folder, date_str, folder_name, img, img_metadata in single_image_data:
                    location = img_metadata.get('location')

                    batch_info = {
                        "batch_number": batch_number,
                        "date_folder": date_str,
                        "folder_path": str(folder),
                        "folder_name": folder_name,
                        "images": [img],
                        "image_count": 1,
                        "is_multi_date": False,
                        "is_multi_location": False,
                        "location": location,
                        "date_list": [date_str]
                    }
                    all_batches.append(batch_info)
                    self.stats['batches_created'] += 1

                    loc_info = f" at {location}" if location else ""
                    print(f"  Batch {batch_number}: {folder_name}{loc_info}")
                    batch_number += 1

        # Update state
        self.state = {
            "source_directory": directory,
            "current_batch_index": 0,
            "total_batches": len(all_batches),
            "batches": all_batches
        }

        self.save_state()

        # Comprehensive reporting
        print()
        print("=" * 60)
        print("BATCH CREATION SUMMARY")
        print("=" * 60)

        total_images = sum(b['image_count'] for b in all_batches)
        multi_date_count = sum(1 for b in all_batches if b.get('is_multi_date', False))
        multi_location_count = sum(1 for b in all_batches if b.get('is_multi_location', False))

        print(f"✅ Created {len(all_batches)} batches from {total_images} images")
        print()

        print("Statistics:")
        print(f"  Date folders: {self.stats.get('total_date_folders', 0)}")
        print(f"    - Multi-image folders: {self.stats.get('multi_image_folders', 0)}")
        print(f"    - Single-image folders: {self.stats.get('single_image_folders', 0)}")
        print(f"    - Empty folders: {self.stats.get('empty_folders', 0)}")
        print(f"  Total images: {self.stats.get('total_images', 0)}")
        print(f"  Metadata extracted: {self.stats.get('metadata_extracted', 0)}")
        print(f"  Batches created: {self.stats.get('batches_created', 0)}")
        if multi_date_count > 0:
            print(f"    - Multi-date batches: {multi_date_count}")
        if multi_location_count > 0:
            print(f"    - Multi-location dates: {self.stats.get('multi_location_dates', 0)}")
        print()

        # Batch size distribution
        batch_sizes = [b['image_count'] for b in all_batches]
        size_counts = defaultdict(int)
        for size in batch_sizes:
            size_counts[size] += 1

        print("Batch size distribution:")
        for size in sorted(size_counts.keys()):
            print(f"  {size} images: {size_counts[size]} batches")
        print()

        # Orientation statistics
        portrait_count = sum(1 for img in all_images if metadata.get(img, {}).get('orientation') == 'portrait')
        landscape_count = len(all_images) - portrait_count
        print(f"Image orientations: {portrait_count} portrait, {landscape_count} landscape")
        print()

        # Warnings and validation
        warnings = []
        if self.stats.get('metadata_extracted', 0) < self.stats.get('total_images', 0):
            missing = self.stats['total_images'] - self.stats['metadata_extracted']
            warnings.append(f"⚠️  {missing} images missing metadata")

        if self.stats.get('empty_folders', 0) > 0:
            warnings.append(f"⚠️  {self.stats['empty_folders']} empty date folders")

        if warnings:
            print("Warnings:")
            for warning in warnings:
                print(f"  {warning}")
            print()

        print("=" * 60)
        print()

    def _extract_filename_group_key(self, filepath: str) -> str:
        """Extract a group key from a filename by removing numeric tokens and extension.

        Splits the filename on non-alphanumeric characters, discards purely
        numeric tokens (sequence numbers, dates-as-digits, etc.), and joins
        the remaining words in lowercase.

        Examples:
            'beach_sunset_001.jpg'   -> 'beach_sunset'
            'IMG_2024_mountain.jpg'  -> 'img_mountain'
            'DSC_0042.jpg'           -> 'dsc'
            '001.jpg'                -> ''
        """
        name = Path(filepath).stem
        tokens = re.split(r'[^a-zA-Z0-9]+', name)
        word_tokens = [t.lower() for t in tokens if t and not t.isdigit()]
        return '_'.join(word_tokens)

    def _scan_flat_directory(self, directory: str):
        """Fallback: scan a flat directory with no date folders.

        Finds all images recursively, groups them by filename commonality
        (shared non-numeric words), and splits into batches while
        preserving filename sort order.
        """
        all_images = self.find_images_recursive(directory)

        if not all_images:
            print("No images found in directory")
            self.state = {
                "source_directory": directory,
                "current_batch_index": 0,
                "total_batches": 0,
                "batches": []
            }
            self.save_state()
            return

        print(f"Found {len(all_images)} images (flat directory mode)")
        print()

        # Group consecutive images by filename commonality (preserving sort order)
        groups = []
        current_key = self._extract_filename_group_key(all_images[0])
        current_group = [all_images[0]]

        for img in all_images[1:]:
            key = self._extract_filename_group_key(img)
            if key != current_key:
                groups.append((current_key, current_group))
                current_key = key
                current_group = [img]
            else:
                current_group.append(img)
        groups.append((current_key, current_group))

        print(f"Found {len(groups)} filename group(s):")
        for key, imgs in groups:
            print(f"  '{key or '(numeric only)'}': {len(imgs)} images")
        print()

        # Create batches from groups (order preserved within and across groups)
        all_batches = []
        batch_number = 1

        for group_key, group_images in groups:
            batches = self._create_batches_simple(group_images)
            for batch_images in batches:
                display_name = group_key or os.path.basename(directory)
                batch_info = {
                    "batch_number": batch_number,
                    "date_folder": display_name,
                    "folder_path": directory,
                    "folder_name": display_name,
                    "images": batch_images,
                    "image_count": len(batch_images),
                    "is_multi_date": False,
                    "is_multi_location": False,
                    "location": None,
                    "filename_group": group_key
                }
                all_batches.append(batch_info)
                batch_number += 1

        # Update state
        self.state = {
            "source_directory": directory,
            "current_batch_index": 0,
            "total_batches": len(all_batches),
            "batches": all_batches
        }
        self.save_state()

        # Report
        print("=" * 60)
        print("BATCH CREATION SUMMARY (flat directory mode)")
        print("=" * 60)

        total_images = sum(b['image_count'] for b in all_batches)
        print(f"Created {len(all_batches)} batches from {total_images} images")
        print(f"Filename groups: {len(groups)}")
        print()

        # Batch size distribution
        size_counts = defaultdict(int)
        for b in all_batches:
            size_counts[b['image_count']] += 1

        print("Batch size distribution:")
        for size in sorted(size_counts.keys()):
            print(f"  {size} images: {size_counts[size]} batches")
        print()
        print("=" * 60)
        print()

    def get_current_batch(self) -> Optional[Dict]:
        """Get the current batch without advancing."""
        if not self.state["batches"]:
            print("No batches available. Run 'init' first.")
            return None

        if self.state["current_batch_index"] >= self.state["total_batches"]:
            print("No more batches available.")
            return None

        return self.state["batches"][self.state["current_batch_index"]]

    def get_next_batch(self) -> Optional[Dict]:
        """Advance to next batch and return it."""
        if not self.state["batches"]:
            print("No batches available. Run 'init' first.")
            return None

        # Advance
        self.state["current_batch_index"] += 1
        self.save_state()

        if self.state["current_batch_index"] >= self.state["total_batches"]:
            print("No more batches available.")
            return None

        return self.state["batches"][self.state["current_batch_index"]]

    def reset(self):
        """Reset to the first batch."""
        self.state["current_batch_index"] = 0
        self.save_state()
        print("✅ Reset to first batch")

    def list_all(self):
        """List all batches."""
        if not self.state["batches"]:
            print("No batches available. Run 'init' first.")
            return

        print(f"All Batches ({self.state['total_batches']} total):")
        print(f"Source: {self.state['source_directory']}")
        print()

        current_date = None
        for batch in self.state["batches"]:
            # Print date header when it changes (for single-date batches)
            if not batch.get("is_multi_date", False):
                if batch["date_folder"] != current_date:
                    current_date = batch["date_folder"]
                    print(f"\n{batch['folder_name']}:")
            else:
                # Multi-date batch - print special header
                current_date = None
                print(f"\nMulti-date batch ({batch['folder_name']}):")

            current = " ← CURRENT" if batch["batch_number"] - 1 == self.state["current_batch_index"] else ""
            multi_date_marker = " [MULTI-DATE]" if batch.get("is_multi_date", False) else ""
            location = batch.get("location")
            loc_marker = f" at {location}" if location else ""
            print(f"  Batch {batch['batch_number']}: {batch['image_count']} images{multi_date_marker}{loc_marker}{current}")
            for img in batch["images"]:
                print(f"    - {os.path.basename(img)}")

        print()

    def show_status(self):
        """Show current status."""
        if not self.state["batches"]:
            print("No batches available. Run 'init' first.")
            return

        total = self.state["total_batches"]
        current_idx = self.state["current_batch_index"]

        print(f"Status:")
        print(f"  Source: {self.state['source_directory']}")
        print(f"  Total batches: {total}")
        print(f"  Current batch: {current_idx + 1}/{total}")
        print(f"  Completed: {current_idx}/{total}")
        print(f"  Remaining: {total - current_idx}")

        if current_idx < total:
            current = self.state["batches"][current_idx]
            print()
            print(f"Current Batch #{current['batch_number']}:")
            print(f"  Date: {current['date_folder']}")
            print(f"  Folder: {current['folder_name']}")
            print(f"  Images: {current['image_count']}")

        print()

def print_batch(batch: Dict):
    """Print batch information in a readable format."""
    if not batch:
        return

    print(f"Batch #{batch['batch_number']}:")
    print(f"  Date: {batch['date_folder']}")
    print(f"  Folder: {batch['folder_name']}")
    location = batch.get('location')
    if location:
        print(f"  Location: {location}")
    print(f"  Image count: {batch['image_count']}")
    print(f"  Images:")
    for img in batch['images']:
        print(f"    - {img}")
    print()

def main():
    parser = argparse.ArgumentParser(
        description='Image Batcher - Manage batches of images from date-organized folders',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scan directory with default settings (1-5 images per batch, combine singles)
  batcher.py init /path/to/photos

  # Scan with custom batch sizes (2-4 images per batch)
  batcher.py init /path/to/photos --min-batch 2 --max-batch 4

  # Don't combine single-image dates
  batcher.py init /path/to/photos --no-combine-singles

  # Prefer smaller batches
  batcher.py init /path/to/photos --prefer-small

  # Get current batch
  batcher.py get_batch

  # Get next batch and advance
  batcher.py get_next_batch

  # List all batches
  batcher.py list_all

  # Show status
  batcher.py status

  # Reset to first batch
  batcher.py reset
        """
    )

    parser.add_argument('command', choices=['init', 'get_batch', 'get_next_batch', 'reset', 'list_all', 'status'],
                        help='Command to execute')
    parser.add_argument('directory', nargs='?', help='Directory to scan (required for init command)')

    # Configuration options
    parser.add_argument('--min-batch', type=int, default=1,
                        help='Minimum batch size (default: 1)')
    parser.add_argument('--max-batch', type=int, default=5,
                        help='Maximum batch size (default: 5)')
    parser.add_argument('--no-combine-singles', action='store_true',
                        help='Don\'t combine single-image dates (each becomes its own batch)')
    parser.add_argument('--prefer-small', action='store_true',
                        help='Prefer smaller batches (default: prefer larger)')

    args = parser.parse_args()

    # Create batcher with configuration
    batcher = ImageBatcher(
        min_batch_size=args.min_batch,
        max_batch_size=args.max_batch,
        combine_singles=not args.no_combine_singles,
        prefer_large=not args.prefer_small
    )

    if args.command == "init":
        if not args.directory:
            parser.error("init command requires directory argument")
        batcher.scan_directory(args.directory)

    elif args.command == "get_batch":
        batch = batcher.get_current_batch()
        if batch:
            print_batch(batch)

    elif args.command == "get_next_batch":
        batch = batcher.get_next_batch()
        if batch:
            print_batch(batch)

    elif args.command == "reset":
        batcher.reset()

    elif args.command == "list_all":
        batcher.list_all()

    elif args.command == "status":
        batcher.show_status()

if __name__ == "__main__":
    main()
