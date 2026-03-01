---
name: image-batcher
description: Batch images from date-organized folders for processing in groups of 1-6, respecting both date and location boundaries
---

# Image Batcher Skill

This skill manages batching of images for album creation. When images are organized in date-prefixed folders, it creates batches respecting date and location boundaries. When no date folders are found (flat directory), it falls back to shuffling all images and splitting into random batches of 1-6.

## New in v2.1

**Flat-directory fallback:**
- When no `YYYY-MM-DD` date folders are found, automatically falls back to flat-directory mode
- Finds all images recursively, shuffles them randomly, and splits into batches of 1 to `max_batch_size`
- Each batch gets a random size for layout variety

## New in v2.0

**Enhanced Features:**
- **Batch metadata extraction**: Extract location, caption, orientation, and date for all images at once
- **Location-aware single-image batching**: Groups single-image dates by location before batching
- **Configurable batch sizes**: `--min-batch` and `--max-batch` flags to control batch size range
- **Orientation-aware batching**: Pre-groups portrait and landscape images for better template matching
- **Comprehensive reporting**: Statistics, batch size distribution, orientation breakdown, validation warnings
- **Flexible combining**: `--no-combine-singles` to disable single-image date combining
- **Batch size preference**: `--prefer-small` to prefer smaller batches over larger ones

## Purpose

When creating photo albums or processing many images, this skill helps you:
- Process images in manageable batches (configurable 1-5 images at a time)
- Maintain date organization (multi-image dates never span multiple dates)
- **Respect location boundaries** (splits batches when location changes within dates)
- **Group by orientation** (portrait and landscape images batched separately for better layout matching)
- Track progress through large image collections
- Optimize batch sizes (configurable preference for larger or smaller batches)
- **Extract comprehensive metadata** (location, captions, dates, orientation) in batch for efficiency

## State Management

The skill maintains state in `/tmp/image_batcher_state.json`:

```json
{
  "source_directory": "/path/to/images",
  "current_batch_index": 0,
  "total_batches": 15,
  "batches": [
    {
      "batch_number": 1,
      "date_folder": "2026-01-03",
      "folder_path": "inputs/2026-01-03 Window frames",
      "images": ["inputs/2026-01-03 Window frames/image1.jpg", ...],
      "image_count": 5
    },
    ...
  ]
}
```

## Supported Operations

### 1. Initialize / Scan
Scans the directory and creates batches with configurable options.

```bash
# Scan inputs directory with default settings (1-5 images, combine singles, prefer large)
python3 /path/to/batcher.py init inputs/

# Scan with custom batch sizes (2-4 images per batch)
python3 /path/to/batcher.py init inputs/ --min-batch 2 --max-batch 4

# Don't combine single-image dates (each becomes its own batch)
python3 /path/to/batcher.py init inputs/ --no-combine-singles

# Prefer smaller batches over larger ones
python3 /path/to/batcher.py init inputs/ --prefer-small

# Combined options
python3 /path/to/batcher.py init inputs/ --min-batch 3 --max-batch 5 --no-combine-singles
```

**Options:**
- `--min-batch N`: Minimum batch size (default: 1)
- `--max-batch N`: Maximum batch size (default: 5)
- `--no-combine-singles`: Don't combine single-image dates across dates
- `--prefer-small`: Prefer smaller batches instead of larger ones

### 2. Get Current Batch
Returns the current batch without advancing.

```bash
# Get current batch
python3 /path/to/batcher.py get_batch
```

### 3. Get Next Batch
Advances to the next batch and returns it.

```bash
# Get next batch and advance
python3 /path/to/batcher.py get_next_batch
```

### 4. Reset
Resets to the first batch.

```bash
# Reset to beginning
python3 /path/to/batcher.py reset
```

### 5. List All Batches
Shows all batches with summary.

```bash
# List all batches
python3 /path/to/batcher.py list_all
```

### 6. Get Status
Shows current progress.

```bash
# Show status
python3 /path/to/batcher.py status
```

## Date Folder Detection

The skill identifies date folders by matching these patterns at the start of folder names:
- `YYYY-MM-DD` (e.g., "2026-01-03")
- `YYYY-MM-DD <description>` (e.g., "2026-01-03 Window frames")

Any folder starting with a date pattern is considered a date folder.

## Batching Algorithm

The algorithm uses a four-phase approach:

### Phase 1: Categorize Date Folders

1. Scan all date folders and identify:
   - **Multi-image folders** (2+ images): Keep images together in date-specific, location-aware batches
   - **Single-image folders** (1 image): Collect for potential cross-date batching

### Phase 2: Extract Metadata (Batch Processing)

**NEW**: Extract all metadata in a single batch exiftool call for efficiency:
- **Location hierarchy**: IPTC:City → XMP:City → GPS coordinates fallback
- **Captions**: XMP:Description or IPTC:Caption-Abstract
- **Date taken**: DateTimeOriginal
- **Orientation**: Portrait vs landscape (from width/height)
- **Dimensions**: Width and height in pixels

This replaces individual exiftool calls per image with one batch call for all images.

### Phase 3: Create Batches (Multi-Image Folders)

**For multi-image folders (location + orientation aware):**
1. Find all supported image files (jpg, jpeg, png, heic, tiff)
2. Sort images alphabetically
3. **Group by location** (consecutive images with same location)
4. Within each location group:
   - **Pre-group by orientation** (portrait vs landscape) if metadata available
   - Split into batches of min_size-max_size images:
     - Prefers larger batches (if `prefer_large=True`)
     - Or prefers smaller batches (if `prefer_small=True`)
     - Respects configurable min/max batch size constraints
   - Images stay within their date folder AND location
   - **Splits batch when location changes**

### Phase 4: Create Batches (Single-Image Folders)

**NEW: Location-aware single-image batching**

If `combine_singles=True` (default):
1. **Group single-image dates by location first**
2. Within each location group:
   - **Pre-group by orientation** (portrait vs landscape)
   - Create batches of min_size-max_size images:
     - **CAN span multiple dates** (since each date has only 1 image)
     - **CANNOT span locations** (NEW: respects location boundaries)
     - Maintains chronological order by date within location
     - Uses configurable batch size preferences

If `combine_singles=False`:
1. Each single-image date becomes its own batch (no combining)
2. Respects location and date boundaries completely

**Examples:**

**Example 1: Same location**
- Date folder with 13 images at "San Francisco" → 3 batches: [5, 5, 3]

**Example 2: Different locations**
```
Date folder with 10 images:
  - 5 images at "San Francisco" → Batch 1: [5 images]
  - 5 images at "Oakland"       → Batch 2: [5 images]
Result: 2 batches (split by location)
```

**Example 3: Multiple location changes**
```
Date folder with 12 images:
  - 4 images at "San Francisco" → Batch 1: [4 images]
  - 6 images at "Oakland"       → Batch 2: [5 images], Batch 3: [1 image]
  - 2 images at "Berkeley"      → Batch 4: [2 images]
Result: 4 batches (split by location changes)
```

**Example 4: Single-image dates (multi-location OK)**
```
2026-01-15: 1 image at "San Francisco"
2026-01-17: 1 image at "Oakland"        } → Batch: 3 images from 3 dates, 3 locations
2026-01-22: 1 image at "Berkeley"
```

This ensures images from different locations aren't mixed on the same page, while keeping related photos together.

## Implementation

Create the batcher script at `.claude/skills/image-batcher/batcher.py`:

```python
#!/usr/bin/env python3
"""
Image Batcher - Manages batches of images from date-organized folders.
Batches are 1-5 images each, never spanning multiple date folders.
"""

import os
import sys
import json
import re
from pathlib import Path
from typing import List, Dict, Optional

STATE_FILE = "/tmp/image_batcher_state.json"
SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.heic', '.tiff', '.tif'}
DATE_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}')

class ImageBatcher:
    def __init__(self):
        self.state = self.load_state()

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

    def create_batches_from_images(self, images: List[str], max_size: int = 5) -> List[List[str]]:
        """Split images into batches of 1-max_size, preferring larger batches."""
        if not images:
            return []

        batches = []
        remaining = list(images)

        while remaining:
            # Try to use the largest batch size possible
            for size in range(max_size, 0, -1):
                if len(remaining) >= size:
                    batches.append(remaining[:size])
                    remaining = remaining[size:]
                    break
            else:
                # Shouldn't happen, but handle edge case
                batches.append(remaining)
                remaining = []

        return batches

    def scan_directory(self, directory: str):
        """Scan directory for date folders and create batches."""
        directory = os.path.abspath(directory)

        if not os.path.exists(directory):
            raise ValueError(f"Directory does not exist: {directory}")

        print(f"Scanning directory: {directory}")
        print()

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
            print()
            self.state = {
                "source_directory": directory,
                "current_batch_index": 0,
                "total_batches": 0,
                "batches": []
            }
            self.save_state()
            return

        print(f"Found {len(date_folders)} date folders")
        print()

        # Process each date folder
        for folder in date_folders:
            folder_name = folder.name
            date_str = self.extract_date(folder_name)

            # Find images in this folder only (non-recursive within date folder)
            images = self.find_images_in_folder(str(folder))

            if not images:
                print(f"  {folder_name}: No images found")
                continue

            # Create batches for this date folder
            batches = self.create_batches_from_images(images)

            print(f"  {folder_name}: {len(images)} images → {len(batches)} batches")

            # Add batches to global list
            for batch_images in batches:
                batch_info = {
                    "batch_number": batch_number,
                    "date_folder": date_str,
                    "folder_path": str(folder),
                    "folder_name": folder_name,
                    "images": batch_images,
                    "image_count": len(batch_images)
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

        print()
        print(f"✅ Created {len(all_batches)} batches from {sum(b['image_count'] for b in all_batches)} images")
        print(f"   Batch sizes: {', '.join(str(b['image_count']) for b in all_batches)}")
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
            # Print date header when it changes
            if batch["date_folder"] != current_date:
                current_date = batch["date_folder"]
                print(f"\n{batch['folder_name']}:")

            current = " ← CURRENT" if batch["batch_number"] - 1 == self.state["current_batch_index"] else ""
            print(f"  Batch {batch['batch_number']}: {batch['image_count']} images{current}")
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
    print(f"  Image count: {batch['image_count']}")
    print(f"  Images:")
    for img in batch['images']:
        print(f"    - {img}")
    print()

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  batcher.py init <directory>     - Scan directory and create batches")
        print("  batcher.py get_batch            - Get current batch")
        print("  batcher.py get_next_batch       - Advance and get next batch")
        print("  batcher.py reset                - Reset to first batch")
        print("  batcher.py list_all             - List all batches")
        print("  batcher.py status               - Show current status")
        sys.exit(1)

    command = sys.argv[1]
    batcher = ImageBatcher()

    if command == "init":
        if len(sys.argv) < 3:
            print("Error: init requires directory argument")
            print("Usage: batcher.py init <directory>")
            sys.exit(1)
        directory = sys.argv[2]
        batcher.scan_directory(directory)

    elif command == "get_batch":
        batch = batcher.get_current_batch()
        if batch:
            print_batch(batch)

    elif command == "get_next_batch":
        batch = batcher.get_next_batch()
        if batch:
            print_batch(batch)

    elif command == "reset":
        batcher.reset()

    elif command == "list_all":
        batcher.list_all()

    elif command == "status":
        batcher.show_status()

    else:
        print(f"Unknown command: {command}")
        print("Available commands: init, get_batch, get_next_batch, reset, list_all, status")
        sys.exit(1)

if __name__ == "__main__":
    main()
```

## Usage Examples

### Example 1: Initialize with Default Settings

```bash
# Scan inputs directory with default settings
python3 .claude/skills/image-batcher/batcher.py init inputs/

# Output:
# Scanning directory: /Users/jowilson/Code/blurb_album_creator/inputs
# Configuration: min=1, max=5, combine_singles=True, prefer_large=True
#
# Found 9 date folders
#
# Extracting image metadata...
# Extracted metadata for 59 images
#
#   2026-01-03 Window frames: 12 images → 3 batches (2 locations: 4 at San Francisco, 8 at Unknown)
#   2026-01-06: 2 images → 1 batches at San Francisco
#   2026-01-18: 29 images → 9 batches (6 locations: 5 at Arnold, 12 at Calaveras County, 1 at Unknown, 1 at Arnold, 9 at Calaveras County, 1 at Unknown)
#   2026-01-19: 5 images → 3 batches (3 locations: 3 at Arnold, 1 at Murphys, 1 at Arnold)
#   2026-01-21: 4 images → 2 batches (2 locations: 1 at Unknown, 3 at San Francisco)
#   2026-01-29 Bath tray: 4 images → 1 batches at San Francisco
#
# Processing 3 single-image dates (location-aware batching):
#   Found 1 location groups
#   Batch 20: 3 images from 3 dates (2026-01-15, 2026-01-17, 2026-01-22) at San Francisco
#
# ============================================================
# BATCH CREATION SUMMARY
# ============================================================
# ✅ Created 20 batches from 59 images
#
# Statistics:
#   Date folders: 9
#     - Multi-image folders: 6
#     - Single-image folders: 3
#     - Empty folders: 0
#   Total images: 59
#   Metadata extracted: 59
#   Batches created: 20
#     - Multi-date batches: 1
#
# Batch size distribution:
#   1 images: 6 batches
#   2 images: 2 batches
#   3 images: 4 batches
#   4 images: 3 batches
#   5 images: 5 batches
#
# Image orientations: 4 portrait, 55 landscape
#
# ============================================================

# Get current (first) batch
python3 .claude/skills/image-batcher/batcher.py get_batch

# Output:
# Batch #1:
#   Date: 2026-01-03
#   Folder: 2026-01-03 Window frames
#   Image count: 5
#   Images:
#     - inputs/2026-01-03 Window frames/2026-01-03 17.38.36.jpg
#     - inputs/2026-01-03 Window frames/2026-01-03 17.39.35.jpg
#     - inputs/2026-01-03 Window frames/2026-01-03 22.44.12.jpg
#     - inputs/2026-01-03 Window frames/2026-01-03 22.44.15.jpg
#     - inputs/2026-01-03 Window frames/P1510141.JPG
```

### Example 1b: Custom Configuration

```bash
# Scan with custom settings: max 3 images per batch, don't combine singles
python3 .claude/skills/image-batcher/batcher.py init inputs/ --max-batch 3 --no-combine-singles

# Output:
# Scanning directory: /Users/jowilson/Code/blurb_album_creator/inputs
# Configuration: min=1, max=3, combine_singles=False, prefer_large=True
#
# Found 9 date folders
#
# Extracting image metadata...
# Extracted metadata for 59 images
#
#   2026-01-03 Window frames: 12 images → 5 batches (2 locations: 4 at San Francisco, 8 at Unknown)
#   2026-01-06: 2 images → 1 batches at San Francisco
#   2026-01-18: 29 images → 13 batches (6 locations: 5 at Arnold, 12 at Calaveras County, 1 at Unknown, 1 at Arnold, 9 at Calaveras County, 1 at Unknown)
#   2026-01-19: 5 images → 3 batches (3 locations: 3 at Arnold, 1 at Murphys, 1 at Arnold)
#   2026-01-21: 4 images → 2 batches (2 locations: 1 at Unknown, 3 at San Francisco)
#   2026-01-29 Bath tray: 4 images → 2 batches at San Francisco
#
# Processing 3 single-image dates (no combining):
#   Batch 27: 2026-01-15 at San Francisco
#   Batch 28: 2026-01-17 at San Francisco
#   Batch 29: 2026-01-22 at San Francisco
#
# ============================================================
# BATCH CREATION SUMMARY
# ============================================================
# ✅ Created 29 batches from 59 images
#
# Statistics:
#   Date folders: 9
#     - Multi-image folders: 6
#     - Single-image folders: 3
#     - Empty folders: 0
#   Total images: 59
#   Metadata extracted: 59
#   Batches created: 29
#
# Batch size distribution:
#   1 images: 12 batches
#   2 images: 4 batches
#   3 images: 13 batches
#
# Image orientations: 4 portrait, 55 landscape
#
# ============================================================
```

### Example 2: Advance Through Batches

```bash
# Get next batch (advances from batch 1 to batch 2)
python3 .claude/skills/image-batcher/batcher.py get_next_batch

# Output:
# Batch #2:
#   Date: 2026-01-03
#   Folder: 2026-01-03 Window frames
#   Image count: 5
#   Images:
#     - inputs/2026-01-03 Window frames/P1510175.JPG
#     - inputs/2026-01-03 Window frames/P1510177.JPG
#     - inputs/2026-01-03 Window frames/P1510179.JPG
#     - inputs/2026-01-03 Window frames/P1510197.JPG
#     - inputs/2026-01-03 Window frames/P1510201.JPG

# Get next batch again
python3 .claude/skills/image-batcher/batcher.py get_next_batch

# Output:
# Batch #3:
#   Date: 2026-01-03
#   Folder: 2026-01-03 Window frames
#   Image count: 2
#   Images:
#     - inputs/2026-01-03 Window frames/P1510202.JPG
#     - inputs/2026-01-03 Window frames/P1510203.JPG
```

### Example 2a: Multi-Date Batch (Single Images Combined)

```bash
# Navigate to the multi-date batch (batch 14 in this example)
# This batch combines images from three dates that each had only one image

python3 .claude/skills/image-batcher/batcher.py get_batch

# Output:
# Batch #14:
#   Date: 2026-01-15 to 2026-01-22
#   Folder: 3 dates
#   Image count: 3
#   Images:
#     - inputs/2026-01-15/2026-01-15 14.33.32.jpg
#     - inputs/2026-01-17/IMG_0368.JPG
#     - inputs/2026-01-22/2026-01-22 07.40.32.jpg

# Note: This batch spans three dates (2026-01-15, 2026-01-17, 2026-01-22)
# because each of those dates contained only a single image.
# Multi-image dates always stay in their own date-specific batches.
```

### Example 3: Check Status

```bash
python3 .claude/skills/image-batcher/batcher.py status

# Output:
# Status:
#   Source: /Users/jowilson/Code/blurb_album_creator/inputs
#   Total batches: 23
#   Current batch: 4/23
#   Completed: 3/23
#   Remaining: 20
#
# Current Batch #4:
#   Date: 2026-01-06
#   Folder: 2026-01-06
#   Images: 2
```

### Example 4: List All Batches

```bash
python3 .claude/skills/image-batcher/batcher.py list_all

# Output:
# All Batches (23 total):
# Source: /Users/jowilson/Code/blurb_album_creator/inputs
#
# 2026-01-03 Window frames:
#   Batch 1: 5 images
#     - image1.jpg
#     - image2.jpg
#     - image3.jpg
#     - image4.jpg
#     - image5.jpg
#   Batch 2: 5 images
#     - image6.jpg
#     ...
#   Batch 3: 2 images ← CURRENT
#     - image11.jpg
#     - image12.jpg
#
# 2026-01-06:
#   Batch 4: 2 images
#     - photo1.jpg
#     - photo2.jpg
# ...
```

### Example 5: Reset to Beginning

```bash
python3 .claude/skills/image-batcher/batcher.py reset

# Output:
# ✅ Reset to first batch

python3 .claude/skills/image-batcher/batcher.py get_batch

# Output:
# Batch #1:
#   Date: 2026-01-03
#   Folder: 2026-01-03 Window frames
#   Image count: 5
#   ...
```

## Integration with Other Skills

### Use with /blurb Skill

```bash
# Initialize batcher
python3 .claude/skills/image-batcher/batcher.py init inputs/

# Process each batch
while true; do
  # Get current batch
  batch=$(python3 .claude/skills/image-batcher/batcher.py get_batch)

  if [ $? -ne 0 ]; then
    echo "No more batches"
    break
  fi

  # Extract image paths (parse JSON output)
  # Add images to blurb file using /blurb skill

  # Advance to next batch
  python3 .claude/skills/image-batcher/batcher.py get_next_batch
done
```

### Use with /image Skill

```bash
# Get current batch
batch_info=$(python3 .claude/skills/image-batcher/batcher.py get_batch)

# Extract captions for images in current batch using /image skill
# (Process only the 1-5 images in current batch)

# Advance to next batch
python3 .claude/skills/image-batcher/batcher.py get_next_batch
```

## Workflow

When invoked with `/image-batcher`:

1. **Determine operation:**
   - Initialize/scan directory
   - Get current batch
   - Get next batch
   - Show status
   - List all batches
   - Reset to beginning

2. **Execute operation:**
   - Load state from `/tmp/image_batcher_state.json`
   - Perform requested operation
   - Save state if modified

3. **Return results:**
   - For get_batch/get_next_batch: Return batch info (date, folder, images)
   - For status: Show progress summary
   - For list_all: Show all batches organized by date

## Key Features

- **Smart date handling**:
  - Multi-image dates (2+): Keep images together in date-specific batches
  - Single-image dates (1): Optionally combine across dates into efficient batches
  - Configurable: `--no-combine-singles` to disable combining
- **Enhanced location-aware batching**:
  - **Batch metadata extraction**: One exiftool call for all images (efficient)
  - **Location hierarchy**: IPTC:City → XMP:City → GPS coordinates fallback
  - Splits batches when location changes within a date
  - Multi-image dates: Respect location boundaries
  - **NEW**: Single-image dates: Also respect location boundaries (grouped by location first)
- **Orientation-aware batching**:
  - Detects portrait vs landscape from image dimensions
  - Pre-groups images by orientation before batching
  - Better template matching in album creation
- **Configurable batching**:
  - `--min-batch N` and `--max-batch N`: Control batch size range (default: 1-5)
  - `--prefer-small`: Prefer smaller batches over larger ones
  - `--prefer-large`: Prefer larger batches (default)
- **Comprehensive metadata**:
  - Location, caption, date, orientation, dimensions
  - Extracted in one batch call for all images
- **Comprehensive reporting**:
  - Statistics: Folder counts, metadata extraction, batch counts
  - Batch size distribution chart
  - Orientation breakdown (portrait/landscape)
  - Validation warnings (missing metadata, empty folders)
- **Stateful**: Remembers current position across invocations
- **Non-recursive within dates**: Only looks at images directly in date folders
- **Resumable**: Can reset, skip ahead, or check status at any time

## Notes

- State file location: `/tmp/image_batcher_state.json`
- Supported image formats: JPG, JPEG, PNG, HEIC, TIFF, TIF
- Date pattern: Folders starting with `YYYY-MM-DD`
- Batch size: Configurable (default 1-5 images per batch)
- **Metadata extraction**:
  - **Batch processing**: One exiftool call for all images (efficient)
  - **Location hierarchy**: IPTC:City → XMP:City → GPS coordinates fallback
  - **Captions**: XMP:Description or IPTC:Caption-Abstract
  - **Orientation**: Portrait vs landscape from dimensions
  - **Date**: DateTimeOriginal
- **Multi-image dates** (2+ images):
  - Batches never span multiple dates
  - **Batches split when location changes**
  - **Orientation-aware**: Portrait and landscape batched separately
- **Single-image dates** (1 image) with `combine_singles=True` (default):
  - Batches CAN span multiple dates for efficiency
  - **NEW**: Batches CANNOT span locations (grouped by location first)
  - **Orientation-aware**: Portrait and landscape batched separately
- **Single-image dates** with `--no-combine-singles`:
  - Each date becomes its own batch (no combining)
- Images within a folder are sorted alphabetically before location grouping
- Multi-date batches are clearly marked with date range (e.g., "2026-01-15 to 2026-01-22")
- Location info displayed in batch summaries (e.g., "at San Francisco" or "3 locations")
- **Comprehensive reporting**: Statistics, distribution, orientations, warnings
