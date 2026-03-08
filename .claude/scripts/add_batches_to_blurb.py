#!/usr/bin/env python3
"""
Add all image-batcher batches to a .blurb file.
Reads batch state from /tmp/image_batcher_state.json.
Matches each batch to a template page with the right number of containers.
"""

import os
import sys
import json
import xml.etree.ElementTree as ET
import subprocess
import random
import copy
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def load_batcher_state():
    with open('/tmp/image_batcher_state.json', 'r') as f:
        return json.load(f)


def analyze_template(blurb_file):
    """Analyze template pages and group by container count."""
    subprocess.run(
        ['sqlite3', blurb_file,
         "SELECT writefile('/tmp/bbf2_work.xml', filecontent) FROM Files WHERE filepath='bbf2.xml';"],
        capture_output=True
    )

    tree = ET.parse('/tmp/bbf2_work.xml')
    root = tree.getroot()
    section = root.find('.//section[@name=""]')
    if section is None:
        print("ERROR: No section found in bbf2.xml")
        sys.exit(1)

    pages_by_count = defaultdict(list)
    for page in section.findall('page'):
        pn = page.get('number')
        if not pn:
            continue
        containers = page.findall('.//container[@type="image"]')
        count = len(containers)
        if 1 <= count <= 6:
            pages_by_count[count].append(page)

    return dict(pages_by_count), tree, root, section


def get_image_dimensions(filepath):
    result = subprocess.run(
        ['sips', '-g', 'pixelWidth', '-g', 'pixelHeight', filepath],
        capture_output=True, text=True
    )
    width = height = 0
    for line in result.stdout.split('\n'):
        if 'pixelWidth:' in line:
            width = int(line.split(':')[1].strip())
        elif 'pixelHeight:' in line:
            height = int(line.split(':')[1].strip())
    return width, height


def find_best_template_size(needed, available_sizes):
    """Find the best template size for a given number of images."""
    if needed in available_sizes:
        return needed
    # Try larger sizes first
    for s in sorted(available_sizes):
        if s >= needed:
            return s
    # Fall back to largest available
    return max(available_sizes)


def process_all_batches(blurb_file):
    state = load_batcher_state()
    batches = state['batches']

    if not batches:
        print("No batches to process")
        return

    total_images = sum(b['image_count'] for b in batches)
    print(f"Processing {len(batches)} batches with {total_images} images total")
    print()

    pages_by_count, tree, root, section = analyze_template(blurb_file)
    available_sizes = set(pages_by_count.keys())

    print("Available template layouts:")
    for count in sorted(pages_by_count.keys()):
        print(f"  {count} containers: {len(pages_by_count[count])} pages")
    print()

    # Determine max page number in existing template
    max_existing = 0
    for page in section.findall('page'):
        pn = page.get('number')
        if pn and pn.isdigit():
            max_existing = max(max_existing, int(pn))

    all_image_data = []
    new_pages = []
    page_num = max_existing + 1
    images_added = 0
    pages_created = 0

    for batch in batches:
        batch_num = batch['batch_number']
        batch_images = batch['images']
        batch_label = batch.get('folder_name', batch.get('date_folder', ''))

        remaining_images = list(batch_images)
        sub_batch_num = 0

        while remaining_images:
            # Find best template size for remaining images
            use_size = find_best_template_size(len(remaining_images), available_sizes)
            # Don't use more containers than images
            use_size = min(use_size, len(remaining_images))
            # Make sure we have a template for this size
            if use_size not in pages_by_count:
                # Find the largest available that fits
                for s in sorted(available_sizes, reverse=True):
                    if s <= len(remaining_images):
                        use_size = s
                        break
                else:
                    use_size = min(available_sizes)

            sub_images = remaining_images[:use_size]
            remaining_images = remaining_images[use_size:]
            sub_batch_num += 1

            # Pick random template page with matching container count
            template_page = random.choice(pages_by_count[use_size])
            new_page = copy.deepcopy(template_page)
            new_page.set('number', str(page_num))

            # Process each image in sub-batch
            batch_image_data = []
            for img_path in sub_images:
                if not os.path.exists(img_path):
                    print(f"    WARNING: Image not found: {img_path}")
                    continue

                guid = str(uuid.uuid4()).upper()
                ext = Path(img_path).suffix[1:].lower()
                if ext == 'jpeg':
                    ext = 'jpg'
                archive_path = f"images/{guid}.{ext}"

                width, height = get_image_dimensions(img_path)

                # Add to archive with error checking
                # Escape single quotes in paths for SQL
                escaped_img_path = img_path.replace("'", "''")
                filesize = os.path.getsize(img_path)
                result = subprocess.run(
                    ['sqlite3', blurb_file,
                     f"INSERT OR REPLACE INTO Files (filepath, filecontent, filesize, filedate) "
                     f"VALUES ('{archive_path}', readfile('{escaped_img_path}'), {filesize}, datetime('now'));"],
                    capture_output=True, text=True
                )

                if result.returncode != 0:
                    print(f"    ERROR adding {os.path.basename(img_path)}: {result.stderr}")
                    continue

                # Verify the image was actually added
                verify_result = subprocess.run(
                    ['sqlite3', blurb_file,
                     f"SELECT COUNT(*) FROM Files WHERE filepath='{archive_path}';"],
                    capture_output=True, text=True
                )

                if verify_result.stdout.strip() != '1':
                    print(f"    ERROR: Failed to verify {os.path.basename(img_path)} in archive")
                    continue

                img_data = {
                    'guid': guid,
                    'ext': ext,
                    'width': width,
                    'height': height,
                    'path': archive_path,
                    'basename': os.path.basename(img_path)
                }
                batch_image_data.append(img_data)
                all_image_data.append(img_data)
                images_added += 1

            # Fill containers on the page
            containers = new_page.findall('.//container[@type="image"]')
            for idx, (container, img) in enumerate(zip(containers, batch_image_data)):
                filename = img['path'].split('/')[-1]
                image_elem = container.find('image')
                if image_elem is not None:
                    image_elem.set('src', filename)
                    image_elem.set('autolayout', 'fill')
                else:
                    image_elem = ET.SubElement(container, 'image')
                    image_elem.set('src', filename)
                    image_elem.set('rotate', '0')
                    image_elem.set('flip', 'none')
                    image_elem.set('x', '0')
                    image_elem.set('y', '0')
                    image_elem.set('scale', '1.0')
                    image_elem.set('autolayout', 'fill')

            new_pages.append(new_page)
            pages_created += 1

            if sub_batch_num == 1 and not remaining_images:
                print(f"  Batch {batch_num}: {len(batch_image_data)} images -> page {page_num} ({use_size}-container template) [{batch_label}]")
            else:
                print(f"  Batch {batch_num}.{sub_batch_num}: {len(batch_image_data)} images -> page {page_num} ({use_size}-container template) [{batch_label}]")

            page_num += 1

    # Append all new pages to end of section
    for new_page in new_pages:
        section.append(new_page)

    # Verify pages were added
    final_count = len(section.findall('page'))
    print(f"Pages in section after append: {final_count}")

    # Save updated XML
    tree.write('/tmp/bbf2_updated.xml', encoding='utf-8', xml_declaration=True)
    filesize = os.path.getsize('/tmp/bbf2_updated.xml')
    print(f"Updated XML size: {filesize:,} bytes")

    # Verify the written XML
    verify_tree = ET.parse('/tmp/bbf2_updated.xml')
    verify_section = verify_tree.getroot().find('.//section[@name=""]')
    verify_count = len(verify_section.findall('page'))
    print(f"Pages in written XML: {verify_count}")

    if verify_count != final_count:
        print(f"ERROR: Page count mismatch! Expected {final_count}, got {verify_count}")
        sys.exit(1)

    # Update archive
    result = subprocess.run(
        ['sqlite3', blurb_file,
         f"UPDATE Files SET filecontent=readfile('/tmp/bbf2_updated.xml'), "
         f"filesize={filesize}, filedate=datetime('now') WHERE filepath='bbf2.xml';"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"ERROR updating archive: {result.stderr}")
        sys.exit(1)

    # Verify update succeeded
    subprocess.run(['sqlite3', blurb_file,
                   "SELECT writefile('/tmp/bbf2_verify.xml', filecontent) FROM Files WHERE filepath='bbf2.xml';"],
                  capture_output=True)
    verify_tree2 = ET.parse('/tmp/bbf2_verify.xml')
    verify_section2 = verify_tree2.getroot().find('.//section[@name=""]')
    final_verify_count = len(verify_section2.findall('page'))
    print(f"Pages in archive after update: {final_verify_count}")

    if final_verify_count != verify_count:
        print(f"ERROR: Archive update failed! Expected {verify_count}, got {final_verify_count}")
        sys.exit(1)

    # Update media_registry.xml
    print()
    print("Updating media registry...")
    subprocess.run(
        ['sqlite3', blurb_file,
         "SELECT writefile('/tmp/media_registry.xml', filecontent) FROM Files WHERE filepath='media_registry.xml';"],
        capture_output=True
    )

    try:
        mr_tree = ET.parse('/tmp/media_registry.xml')
        mr_root = mr_tree.getroot()
        images_elem = mr_root.find('.//images')
    except ET.ParseError:
        mr_root = ET.Element('medialist')
        images_elem = ET.SubElement(mr_root, 'images')
        ET.SubElement(mr_root, 'videos')
        ET.SubElement(mr_root, 'audio')
        ET.SubElement(mr_root, 'text')
        mr_tree = ET.ElementTree(mr_root)

    if images_elem is None:
        images_elem = ET.SubElement(mr_root, 'images')

    for img in all_image_data:
        modified_date = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        media = ET.SubElement(images_elem, 'media')
        media.set('modified', modified_date)
        media.set('height', str(img['height']))
        media.set('dateTaken', '')
        media.set('webImportAlbum', '')
        media.set('enhanceable', 'UNKNOWN')
        media.set('validated', 'true')
        media.set('guid', img['guid'])
        media.set('ext', img['ext'])
        media.set('width', str(img['width']))
        media.set('importBatchNum', '1')
        media.set('cameraModel', 'unknown')
        media.set('designerImage', 'false')
        media.set('cameraMake', 'unknown')
        media.set('src', img['path'])
        media.set('webImportSource', '')

    mr_tree.write('/tmp/media_registry_updated.xml', encoding='utf-8', xml_declaration=True)
    mr_size = os.path.getsize('/tmp/media_registry_updated.xml')
    subprocess.run(
        ['sqlite3', blurb_file,
         f"UPDATE Files SET filecontent=readfile('/tmp/media_registry_updated.xml'), "
         f"filesize={mr_size}, filedate=datetime('now') WHERE filepath='media_registry.xml';"],
        capture_output=True
    )

    # Cleanup
    for f in ['/tmp/bbf2_work.xml', '/tmp/bbf2_updated.xml', '/tmp/bbf2_verify.xml',
              '/tmp/media_registry.xml', '/tmp/media_registry_updated.xml']:
        if os.path.exists(f):
            os.remove(f)

    # Final verification
    print()
    print("=" * 60)
    print("FINAL VERIFICATION")
    print("=" * 60)

    # Count images in archive (including template images)
    archive_result = subprocess.run(
        ['sqlite3', blurb_file,
         "SELECT COUNT(*) FROM Files WHERE filepath LIKE 'images/%';"],
        capture_output=True, text=True
    )
    total_archive_count = int(archive_result.stdout.strip())

    # Count template images (they're already in the archive)
    # We can estimate this by counting XML refs in template pages
    subprocess.run(['sqlite3', blurb_file,
                   "SELECT writefile('/tmp/bbf2_final_check.xml', filecontent) FROM Files WHERE filepath='bbf2.xml';"],
                  capture_output=True)
    verify_tree = ET.parse('/tmp/bbf2_final_check.xml')
    verify_section = verify_tree.getroot().find('.//section[@name=""]')

    template_ref_count = 0
    xml_ref_count = 0
    for page in verify_section.findall('page'):
        pn = int(page.get('number'))
        for c in page.findall('.//container[@type="image"]'):
            img = c.find('image')
            if img is not None and img.get('src'):
                if pn <= max_existing:
                    template_ref_count += 1
                else:
                    xml_ref_count += 1

    # Count media registry entries
    subprocess.run(['sqlite3', blurb_file,
                   "SELECT writefile('/tmp/media_registry_final.xml', filecontent) FROM Files WHERE filepath='media_registry.xml';"],
                  capture_output=True)
    mr_verify = ET.parse('/tmp/media_registry_final.xml')
    mr_images = mr_verify.getroot().find('.//images')
    media_count = len(mr_images.findall('media')) if mr_images is not None else 0

    expected = sum(len(b['images']) for b in state['batches'])
    new_archive_count = total_archive_count - template_ref_count

    print(f"Expected (source images): {expected}")
    print(f"Images processed: {images_added}")
    print(f"XML refs in new pages: {xml_ref_count}")
    print(f"Archive files (new only): {new_archive_count}")
    print(f"Archive files (total): {total_archive_count} (includes {template_ref_count} from template)")
    print(f"Media registry entries: {media_count}")

    if images_added != expected:
        print(f"\n⚠️  WARNING: {expected - images_added} images failed to add")

    if new_archive_count != images_added:
        print(f"\n⚠️  ERROR: New archive count mismatch (expected {images_added}, got {new_archive_count})")

    if xml_ref_count != images_added:
        print(f"\n⚠️  ERROR: XML reference mismatch (expected {images_added}, got {xml_ref_count})")

    if new_archive_count == images_added == xml_ref_count == expected:
        print(f"\n✓ All counts match: {images_added} images added successfully")
        print(f"✓ Input: {expected} images")
        print(f"✓ Archive: {new_archive_count} new + {template_ref_count} template = {total_archive_count} total")
        print(f"✓ XML: {xml_ref_count} new references")

    print("=" * 60)
    print(f"Pages {max_existing + 1} - {max_existing + pages_created} appended to book")
    print("=" * 60)

    # Cleanup verification files
    for f in ['/tmp/bbf2_final_check.xml', '/tmp/media_registry_final.xml']:
        if os.path.exists(f):
            os.remove(f)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 add_batches_to_blurb.py <blurb_file>")
        sys.exit(1)

    blurb_file = sys.argv[1]
    if not os.path.exists(blurb_file):
        print(f"ERROR: File not found: {blurb_file}")
        sys.exit(1)

    process_all_batches(blurb_file)
