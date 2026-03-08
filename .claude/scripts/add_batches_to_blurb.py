#!/usr/bin/env python3
"""
Add all image-batcher batches to a .blurb file.
Reads batch state from /tmp/image_batcher_state.json.
Matches each batch to a template page with the right number of containers.
Uses orientation-aware template selection to match portrait/landscape images
to appropriately oriented containers.
"""

import os
import sys
import json
import re
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


def get_container_orientation(container):
    """Determine if a container is portrait, landscape, or square."""
    w = float(container.get('width', 0))
    h = float(container.get('height', 0))
    if h > w * 1.05:
        return 'portrait'
    elif w > h * 1.05:
        return 'landscape'
    else:
        return 'square'


def get_image_orientation(img_data):
    """Determine if an image is portrait or landscape."""
    w = img_data['width']
    h = img_data['height']
    if h > w:
        return 'portrait'
    else:
        return 'landscape'


def get_page_orientation_profile(page):
    """Get the orientation profile of a template page's image containers.

    Returns a dict with counts of portrait, landscape, and square containers,
    plus an ordered list of container orientations.
    """
    containers = page.findall('.//container[@type="image"]')
    orientations = [get_container_orientation(c) for c in containers]
    return {
        'portrait': sum(1 for o in orientations if o == 'portrait'),
        'landscape': sum(1 for o in orientations if o in ('landscape', 'square')),
        'orientations': orientations,
    }


def score_template_match(batch_image_data, page, page_profile):
    """Score how well a template page matches a batch's orientation mix.

    Returns a score from 0-100 where 100 is a perfect orientation match.
    """
    batch_portrait = sum(1 for img in batch_image_data if get_image_orientation(img) == 'portrait')
    batch_landscape = len(batch_image_data) - batch_portrait

    template_portrait = page_profile['portrait']
    template_landscape = page_profile['landscape']

    portrait_diff = abs(batch_portrait - template_portrait)
    landscape_diff = abs(batch_landscape - template_landscape)
    total_diff = portrait_diff + landscape_diff

    # Each mismatch costs 10 points from a perfect 100
    score = max(0, 100 - total_diff * 10)
    return score


def assign_images_to_containers(batch_image_data, page, page_profile):
    """Assign images to containers respecting orientation matching.

    Portrait images go to portrait containers, landscape to landscape.
    Preserves the relative order within each orientation group.
    Returns a list of (container, img_data) pairs in container order.
    """
    containers = page.findall('.//container[@type="image"]')
    orientations = page_profile['orientations']

    # Split images by orientation, preserving order within each group
    portrait_images = [img for img in batch_image_data if get_image_orientation(img) == 'portrait']
    landscape_images = [img for img in batch_image_data if get_image_orientation(img) == 'landscape']

    # Build assignment: for each container, pick the best-matching image
    assignments = [None] * len(containers)
    portrait_idx = 0
    landscape_idx = 0

    # First pass: assign matching orientations
    for i, orient in enumerate(orientations):
        if orient == 'portrait' and portrait_idx < len(portrait_images):
            assignments[i] = portrait_images[portrait_idx]
            portrait_idx += 1
        elif orient in ('landscape', 'square') and landscape_idx < len(landscape_images):
            assignments[i] = landscape_images[landscape_idx]
            landscape_idx += 1

    # Second pass: fill remaining slots with whatever's left
    remaining = []
    if portrait_idx < len(portrait_images):
        remaining.extend(portrait_images[portrait_idx:])
    if landscape_idx < len(landscape_images):
        remaining.extend(landscape_images[landscape_idx:])

    remaining_idx = 0
    for i in range(len(assignments)):
        if assignments[i] is None and remaining_idx < len(remaining):
            assignments[i] = remaining[remaining_idx]
            remaining_idx += 1

    return list(zip(containers, [a for a in assignments if a is not None]))


def analyze_template(blurb_file):
    """Analyze template pages, group by container count, and extract orientation profiles."""
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
    page_profiles = {}  # keyed by id(page)
    for page in section.findall('page'):
        pn = page.get('number')
        if not pn:
            continue
        containers = page.findall('.//container[@type="image"]')
        count = len(containers)
        if 1 <= count <= 6:
            pages_by_count[count].append(page)
            page_profiles[id(page)] = get_page_orientation_profile(page)

    return dict(pages_by_count), page_profiles, tree, root, section


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


def replace_text_with_lorem(html):
    """Replace visible text nodes in HTML/CDATA content with 'Lorem ipsum'.

    Matches non-empty text between > and < tags, preserving all HTML structure,
    attributes, and whitespace-only nodes.
    """
    return re.sub(
        r'(>)([^<]+)(<)',
        lambda m: m.group(1) + 'Lorem ipsum' + m.group(3)
        if m.group(2).strip() else m.group(0),
        html
    )


def clean_template_pages(section, max_existing):
    """Remove original template body pages and replace text in new pages.

    1. Delete all template pages (1 <= page_number <= max_existing)
    2. Replace text content in new pages with 'Lorem ipsum'
    3. Print summary
    """
    # --- 1. Delete original template body pages ---
    pages_deleted = 0
    pages_to_remove = []
    for page in section.findall('page'):
        pn = page.get('number')
        if not pn or not pn.lstrip('-').isdigit():
            continue
        pn_int = int(pn)
        if 1 <= pn_int <= max_existing:
            pages_to_remove.append(page)

    for page in pages_to_remove:
        section.remove(page)
        pages_deleted += 1

    # --- 2. Renumber surviving pages sequentially from 1 ---
    page_num = 1
    for page in section.findall('page'):
        pn = page.get('number')
        if not pn or not pn.lstrip('-').isdigit():
            continue
        pn_int = int(pn)
        if pn_int < 0:
            continue  # masterpage; skip
        page.set('number', str(page_num))
        page_num += 1

    # --- 3. Replace text in new pages with "Lorem ipsum" ---
    text_pages_replaced = 0
    for page in section.findall('page'):
        pn = page.get('number')
        if not pn or not pn.lstrip('-').isdigit():
            continue
        pn_int = int(pn)
        if pn_int < 1:
            continue  # masterpage; skip

        text_containers = page.findall('.//container[@type="text"]')
        if not text_containers:
            continue

        replaced_any = False
        for container in text_containers:
            # Text is stored in the container's text or tail, or in child elements
            # Walk all text content in the container
            for elem in container.iter():
                if elem.text and elem.text.strip():
                    original = elem.text
                    elem.text = replace_text_with_lorem(original)
                    if elem.text != original:
                        replaced_any = True
                if elem.tail and elem.tail.strip():
                    original = elem.tail
                    elem.tail = replace_text_with_lorem(original)
                    if elem.tail != original:
                        replaced_any = True

        if replaced_any:
            text_pages_replaced += 1

    # --- 4. Summary ---
    print()
    print(f"Template cleanup: deleted {pages_deleted} original template pages, "
          f"renumbered {page_num - 1} pages (1-{page_num - 1}), "
          f"replaced text in {text_pages_replaced} new pages")


def process_all_batches(blurb_file):
    state = load_batcher_state()
    batches = state['batches']

    if not batches:
        print("No batches to process")
        return

    total_images = sum(b['image_count'] for b in batches)
    print(f"Processing {len(batches)} batches with {total_images} images total")
    print()

    pages_by_count, page_profiles, tree, root, section = analyze_template(blurb_file)
    available_sizes = set(pages_by_count.keys())

    print("Available template layouts:")
    for count in sorted(pages_by_count.keys()):
        pages = pages_by_count[count]
        # Summarize orientation profiles for this container count
        profiles = [page_profiles[id(p)] for p in pages]
        unique_profiles = set()
        for prof in profiles:
            unique_profiles.add((prof['portrait'], prof['landscape']))
        profile_strs = [f"{p}P/{l}L" for p, l in sorted(unique_profiles)]
        print(f"  {count} containers: {len(pages)} pages (layouts: {', '.join(profile_strs)})")
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

            # Process each image in sub-batch first (need dimensions for orientation matching)
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

            # Select best-matching template page based on orientation
            candidates = pages_by_count[use_size]
            best_score = -1
            best_pages = []
            for candidate in candidates:
                profile = page_profiles[id(candidate)]
                score = score_template_match(batch_image_data, candidate, profile)
                if score > best_score:
                    best_score = score
                    best_pages = [candidate]
                elif score == best_score:
                    best_pages.append(candidate)

            # Among equally-scored pages, pick randomly for variety
            template_page = random.choice(best_pages)
            template_profile = page_profiles[id(template_page)]
            new_page = copy.deepcopy(template_page)
            new_page.set('number', str(page_num))

            # Build orientation profile for the deep-copied page
            copied_profile = get_page_orientation_profile(new_page)

            # Fill containers using orientation-aware assignment
            assignments = assign_images_to_containers(batch_image_data, new_page, copied_profile)
            for container, img in assignments:
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

            # Build orientation summary for log
            batch_p = sum(1 for img in batch_image_data if get_image_orientation(img) == 'portrait')
            batch_l = len(batch_image_data) - batch_p
            tmpl_p = template_profile['portrait']
            tmpl_l = template_profile['landscape']
            orient_info = f"{batch_p}P/{batch_l}L -> {tmpl_p}P/{tmpl_l}L (score:{best_score})"

            if sub_batch_num == 1 and not remaining_images:
                print(f"  Batch {batch_num}: {len(batch_image_data)} images -> page {page_num} [{orient_info}] [{batch_label}]")
            else:
                print(f"  Batch {batch_num}.{sub_batch_num}: {len(batch_image_data)} images -> page {page_num} [{orient_info}] [{batch_label}]")

            page_num += 1

    # Append all new pages to end of section
    for new_page in new_pages:
        section.append(new_page)

    # Clean up: remove original template pages and replace text in new pages
    clean_template_pages(section, max_existing)

    # Verify pages were added
    final_count = len(section.findall('page'))
    print(f"Pages in section after cleanup: {final_count}")

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
