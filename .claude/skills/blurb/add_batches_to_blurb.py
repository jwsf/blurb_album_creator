#!/usr/bin/env python3
"""
Add all images from image-batcher state to a .blurb file.
Uses batch sizes from batcher state to match template page container counts.
Splits oversized batches when no matching template exists.
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

STATE_FILE = "/tmp/image_batcher_state.json"

def load_batcher_state():
    with open(STATE_FILE, 'r') as f:
        return json.load(f)

def analyze_template(blurb_file):
    subprocess.run(['sqlite3', blurb_file,
                   "SELECT writefile('/tmp/bbf2_work.xml', filecontent) FROM Files WHERE filepath='bbf2.xml';"],
                  capture_output=True)

    tree = ET.parse('/tmp/bbf2_work.xml')
    root = tree.getroot()

    section = root.find('.//section[@name=""]')
    if section is None:
        section = root.find('.//section')

    pages_by_count = defaultdict(list)
    for page in section.findall('page'):
        page_num = page.get('number')
        if not page_num:
            continue
        containers = page.findall('.//container[@type="image"]')
        count = len(containers)
        if 1 <= count <= 6:
            pages_by_count[count].append(page)

    return dict(pages_by_count), tree, root, section

def split_batch_to_fit(images, available_sizes):
    """Split a batch into sub-batches that fit available template sizes."""
    max_available = max(available_sizes)
    sub_batches = []
    remaining = list(images)
    
    while remaining:
        if len(remaining) <= max_available and len(remaining) in available_sizes:
            sub_batches.append(remaining)
            break
        # Take largest available chunk
        size = min(max_available, len(remaining))
        # Prefer a size that exists in templates
        while size > 0 and size not in available_sizes:
            size -= 1
        if size == 0:
            size = min(available_sizes)
        sub_batches.append(remaining[:size])
        remaining = remaining[size:]
    
    return sub_batches

def process_image(blurb_file, img_file):
    guid = str(uuid.uuid4()).upper()
    ext = os.path.splitext(img_file)[1][1:].lower()
    archive_path = f"images/{guid}.{ext}"

    result = subprocess.run(['sips', '-g', 'pixelWidth', '-g', 'pixelHeight', img_file],
                          capture_output=True, text=True)
    width = height = 0
    for line in result.stdout.split('\n'):
        if 'pixelWidth:' in line:
            width = int(line.split(':')[1].strip())
        elif 'pixelHeight:' in line:
            height = int(line.split(':')[1].strip())

    filesize = os.path.getsize(img_file)
    subprocess.run(['sqlite3', blurb_file,
                   f"INSERT OR REPLACE INTO Files (filepath, filecontent, filesize, filedate) "
                   f"VALUES ('{archive_path}', readfile('{img_file}'), {filesize}, datetime('now'));"],
                  capture_output=True)

    return {
        'guid': guid,
        'ext': ext,
        'width': width,
        'height': height,
        'path': archive_path,
        'filename': f"{guid}.{ext}",
        'basename': os.path.basename(img_file)
    }

def main():
    blurb_file = sys.argv[1]

    state = load_batcher_state()
    batches = state['batches']
    print(f"Loaded {len(batches)} batches from image-batcher state")

    print("\nAnalyzing template...")
    pages_by_count, tree, root, section = analyze_template(blurb_file)
    available_sizes = sorted(pages_by_count.keys())
    max_template = max(available_sizes)
    for count in available_sizes:
        print(f"  {count} containers: {len(pages_by_count[count])} template pages")

    # Expand batches to fit available templates
    expanded_batches = []
    for batch in batches:
        batch_images = batch['images']
        if len(batch_images) in pages_by_count:
            expanded_batches.append(batch_images)
        else:
            sub = split_batch_to_fit(batch_images, available_sizes)
            expanded_batches.extend(sub)

    print(f"\nExpanded to {len(expanded_batches)} pages (from {len(batches)} original batches)")
    total_expanded = sum(len(b) for b in expanded_batches)
    total_original = sum(b['image_count'] for b in batches)
    print(f"Total images: {total_expanded} (original: {total_original})")

    print(f"\nProcessing {len(expanded_batches)} pages...")
    all_image_data = []
    new_pages = []
    page_num = 1
    images_done = 0

    for batch_idx, batch_images in enumerate(expanded_batches):
        batch_size = len(batch_images)

        batch_data = []
        for img_file in batch_images:
            img_data = process_image(blurb_file, img_file)
            batch_data.append(img_data)

        all_image_data.extend(batch_data)
        images_done += batch_size

        template_page = random.choice(pages_by_count[batch_size])
        new_page = copy.deepcopy(template_page)
        new_page.set('number', str(page_num))

        containers = new_page.findall('.//container[@type="image"]')
        for container, img in zip(containers, batch_data):
            image_elem = container.find('image')
            if image_elem is not None:
                image_elem.set('src', img['filename'])
                image_elem.set('autolayout', 'fill')
            else:
                image_elem = ET.SubElement(container, 'image')
                image_elem.set('src', img['filename'])
                image_elem.set('rotate', '0')
                image_elem.set('flip', 'none')
                image_elem.set('x', '0')
                image_elem.set('y', '0')
                image_elem.set('scale', '1.0')
                image_elem.set('autolayout', 'fill')

        new_pages.append(new_page)

        if (batch_idx + 1) % 10 == 0 or batch_idx + 1 == len(expanded_batches):
            print(f"  Page {batch_idx + 1}/{len(expanded_batches)} ({images_done}/{total_expanded} images)")

        page_num += 1

    print("\nUpdating media registry...")
    subprocess.run(['sqlite3', blurb_file,
                   "SELECT writefile('/tmp/media_registry.xml', filecontent) FROM Files WHERE filepath='media_registry.xml';"],
                  capture_output=True)

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

    mr_tree.write('/tmp/media_registry.xml', encoding='utf-8', xml_declaration=True)
    filesize = os.path.getsize('/tmp/media_registry.xml')
    subprocess.run(['sqlite3', blurb_file,
                   f"UPDATE Files SET filecontent=readfile('/tmp/media_registry.xml'), "
                   f"filesize={filesize}, filedate=datetime('now') WHERE filepath='media_registry.xml';"],
                  capture_output=True)

    print("Inserting pages into book...")

    for page in section.findall('page'):
        pn = page.get('number')
        if pn and pn.isdigit():
            page.set('number', str(int(pn) + len(new_pages)))

    for np in reversed(new_pages):
        section.insert(0, np)

    # Delete original template pages (only from <section>, not covers/masterpages)
    # Only delete even numbers of pages to maintain spread alignment
    all_section_pages = section.findall('page')
    old_template_pages = all_section_pages[len(new_pages):]
    delete_count = len(old_template_pages)
    if delete_count % 2 != 0:
        delete_count -= 1

    deleted = 0
    if delete_count > 0:
        print(f"Removing {delete_count} original template pages...")
        for page in old_template_pages[:delete_count]:
            section.remove(page)
            deleted += 1
        kept = len(old_template_pages) - delete_count
        if kept > 0:
            print(f"  Kept {kept} template page(s) to maintain even page count")

    # Renumber all remaining pages sequentially
    for idx, page in enumerate(section.findall('page'), start=1):
        page.set('number', str(idx))

    tree.write('/tmp/bbf2_updated.xml', encoding='utf-8', xml_declaration=True)
    filesize = os.path.getsize('/tmp/bbf2_updated.xml')
    subprocess.run(['sqlite3', blurb_file,
                   f"UPDATE Files SET filecontent=readfile('/tmp/bbf2_updated.xml'), "
                   f"filesize={filesize}, filedate=datetime('now') WHERE filepath='bbf2.xml';"],
                  capture_output=True)

    for f in ['/tmp/bbf2_work.xml', '/tmp/bbf2_updated.xml', '/tmp/media_registry.xml']:
        if os.path.exists(f):
            os.remove(f)

    print(f"\n{'='*60}")
    print(f"COMPLETE")
    print(f"{'='*60}")
    print(f"Added {len(all_image_data)} images in {len(new_pages)} pages")
    if deleted > 0:
        print(f"Removed {deleted} original template pages")

    size_counts = defaultdict(int)
    for b in expanded_batches:
        size_counts[len(b)] += 1
    print(f"Page layout distribution:")
    for s in sorted(size_counts.keys()):
        print(f"  {s} images/page: {size_counts[s]} pages")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 add_batches_to_blurb.py <blurb_file>")
        sys.exit(1)
    main()
