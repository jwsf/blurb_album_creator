#!/usr/bin/env python3
"""
Add all image-batcher batches to a .blurb file.
Reads batch state from /tmp/image_batcher_state.json.
Matches each batch to a template page with the right number of containers.
Uses orientation-aware template selection to match portrait/landscape images
to appropriately oriented containers.

CRITICAL: Uses string-based XML manipulation for the final output to preserve
CDATA wrappers, XML declaration format, and other formatting that Bookwright
requires. ElementTree is used only for reading/analysis, never for writing
the final bbf2.xml.
"""

import os
import re
import sys
import json
import xml.etree.ElementTree as ET
import subprocess
import random
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape


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
    """Get the orientation profile of a template page's image containers."""
    containers = page.findall('.//container[@type="image"]')
    orientations = [get_container_orientation(c) for c in containers]
    return {
        'portrait': sum(1 for o in orientations if o == 'portrait'),
        'landscape': sum(1 for o in orientations if o in ('landscape', 'square')),
        'orientations': orientations,
    }


def score_template_match(batch_image_data, page, page_profile):
    """Score how well a template page matches a batch's orientation mix."""
    batch_portrait = sum(1 for img in batch_image_data if get_image_orientation(img) == 'portrait')
    batch_landscape = len(batch_image_data) - batch_portrait

    template_portrait = page_profile['portrait']
    template_landscape = page_profile['landscape']

    portrait_diff = abs(batch_portrait - template_portrait)
    landscape_diff = abs(batch_landscape - template_landscape)
    total_diff = portrait_diff + landscape_diff

    score = max(0, 100 - total_diff * 10)
    return score


def assign_images_to_containers_by_orientation(batch_image_data, orientations):
    """Assign images to container slots respecting orientation matching.

    Returns a list of img_data in container order.
    """
    portrait_images = [img for img in batch_image_data if get_image_orientation(img) == 'portrait']
    landscape_images = [img for img in batch_image_data if get_image_orientation(img) == 'landscape']

    assignments = [None] * len(orientations)
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

    return [a for a in assignments if a is not None]


def analyze_template(blurb_file):
    """Analyze template pages using ElementTree (read-only).

    Returns template analysis data and the raw XML string for later string manipulation.
    """
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
    page_profiles = {}
    page_numbers = {}  # id(page) -> page number string

    spread_count = 0
    for page in section.findall('page'):
        pn = page.get('number')
        if not pn:
            continue
        # Skip spread pages — they are double-wide (2x page width) and cause
        # containers to appear off-screen when used as single-page templates
        if page.get('spread') == 'true':
            spread_count += 1
            continue
        containers = page.findall('.//container[@type="image"]')
        count = len(containers)
        if 1 <= count <= 5:
            pages_by_count[count].append(page)
            page_profiles[id(page)] = get_page_orientation_profile(page)
            page_numbers[id(page)] = pn

    if spread_count:
        print(f"  Skipped {spread_count} spread (double-wide) pages")

    # Determine max page number
    max_existing = 0
    for page in section.findall('page'):
        pn = page.get('number')
        if pn and pn.isdigit():
            max_existing = max(max_existing, int(pn))

    # Read raw XML for string-based manipulation
    with open('/tmp/bbf2_work.xml', 'r', encoding='utf-8') as f:
        raw_xml = f.read()

    # Extract raw XML strings for each template page (by page number)
    # Uses two separate patterns to correctly handle self-closing pages (<page .../>)
    # vs content pages (<page ...>...</page>). A single alternation fails because
    # [^>]* greedily consumes the / in />, falling through to the >.*?</page> branch.
    raw_pages = {}  # page_number_str -> raw XML string
    for m in re.finditer(r'(<page\b[^>]*\bnumber="(\d+)"[^>]*/>)', raw_xml):
        raw_pages[m.group(2)] = m.group(1)
    for m in re.finditer(r'(<page\b[^>]*\bnumber="(\d+)"[^/>][^>]*>.*?</page>)', raw_xml, re.DOTALL):
        raw_pages[m.group(2)] = m.group(1)

    # Remove spread pages from raw_pages — they must not be used as templates
    spread_keys = [k for k, v in raw_pages.items() if 'spread="true"' in v]
    for k in spread_keys:
        del raw_pages[k]

    print(f"  Extracted {len(raw_pages)} raw page templates ({len(spread_keys)} spread pages excluded)")

    return dict(pages_by_count), page_profiles, page_numbers, max_existing, raw_xml, raw_pages


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
    for s in sorted(available_sizes):
        if s >= needed:
            return s
    return max(available_sizes)


def regenerate_ids(page_xml):
    """Replace all id="..." attributes in a page XML string with fresh UUIDs."""
    def replace_id(m):
        return f'{m.group(1)}id="{str(uuid.uuid4())}"'
    return re.sub(r'(\s)id="[^"]*"', replace_id, page_xml)


def fill_page_xml(page_xml, page_num, image_assignments):
    """Fill a raw page XML string with images using string-based manipulation.

    - Sets page number
    - Generates new IDs for page and all containers
    - Fills image containers with image src and guid
    - Replaces text content with 'Lorem ipsum'

    image_assignments is a list of img_data dicts in container order.
    """
    # Set page number
    page_xml = re.sub(r'(\bnumber=")[^"]*(")', f'\\g<1>{page_num}\\2', page_xml, count=1)

    # Generate fresh IDs for page and all containers
    page_xml = regenerate_ids(page_xml)

    # Find all image containers and fill them with images
    img_idx = 0

    def fill_image_container(m):
        nonlocal img_idx
        container_xml = m.group(0)

        # Only process image-type containers
        if 'type="image"' not in container_xml:
            return container_xml

        if img_idx >= len(image_assignments):
            return container_xml

        img = image_assignments[img_idx]
        img_idx += 1
        filename = img['path'].split('/')[-1]
        guid = img['guid']

        # Check if there's already an <image> element
        if '<image ' in container_xml or '<image/' in container_xml:
            # Replace existing image src and add guid
            container_xml = re.sub(
                r'(<image\b[^>]*\bsrc=")[^"]*(")',
                f'\\g<1>{filename}\\2',
                container_xml
            )
            # Set autolayout="fill"
            if 'autolayout=' in container_xml:
                container_xml = re.sub(
                    r'(\bautolayout=")[^"]*(")',
                    '\\g<1>fill\\2',
                    container_xml
                )
            else:
                container_xml = re.sub(
                    r'(<image\b[^/]*)',
                    f'\\1 autolayout="fill"',
                    container_xml
                )
            # Add guid attribute
            if 'guid=' not in container_xml.split('<image')[1].split('>')[0] if '<image' in container_xml else '':
                container_xml = re.sub(
                    r'(<image\b)',
                    f'\\1 guid="{guid}"',
                    container_xml
                )
        else:
            # No image element -- insert one into the container
            image_tag = (
                f'<image guid="{guid}" src="{filename}" '
                f'rotate="0" flip="none" x="0" y="0" scale="1.0" autolayout="fill"/>'
            )
            if container_xml.rstrip().endswith('/>'):
                # Self-closing container: convert to open/close form and insert image
                container_xml = re.sub(r'/>\s*$', f'>\n{image_tag}\n</container>', container_xml)
            else:
                container_xml = container_xml.replace('</container>', f'{image_tag}\n</container>')

        return container_xml

    # Process containers - match both self-closing and full containers.
    # IMPORTANT: The second [^>]*? must be LAZY. If greedy, it consumes the '/'
    # in '/>' causing the alternation to fall through to '>.*?</container>',
    # which then matches across multiple containers in the same page.
    page_xml = re.sub(
        r'<container\b[^>]*type="image"[^>]*?(?:/>|>.*?</container>)',
        fill_image_container,
        page_xml,
        flags=re.DOTALL
    )

    # Replace visible text with 'Lorem ipsum' in all text containers
    # Text is inside CDATA: <![CDATA[<p ...><span ...>Visible text</span></p>]]>
    # CRITICAL: Must not replace ]]> (CDATA closing) which the regex can match
    def replace_text_in_cdata(m):
        text_elem = m.group(0)
        def replace_visible(tm):
            text = tm.group(2)
            if text.strip() and text.strip() != ']]>':
                return tm.group(1) + 'Lorem ipsum' + tm.group(3)
            return tm.group(0)
        text_elem = re.sub(r'(>)([^<]+)(<)', replace_visible, text_elem)
        return text_elem

    # Also handle HTML-escaped text (ElementTree output format) - in case
    def replace_text_in_escaped(m):
        text_elem = m.group(0)
        def replace_visible(tm):
            text = tm.group(2)
            if text.strip() and text.strip() != ']]>':
                return tm.group(1) + 'Lorem ipsum' + tm.group(3)
            return tm.group(0)
        text_elem = re.sub(r'(&gt;)([^&]+?)(&lt;)', replace_visible, text_elem)
        return text_elem

    page_xml = re.sub(r'<text\b[^>]*>.*?</text>', replace_text_in_cdata, page_xml, flags=re.DOTALL)
    page_xml = re.sub(r'<text\b[^>]*>.*?</text>', replace_text_in_escaped, page_xml, flags=re.DOTALL)

    return page_xml


def replace_text_on_template_pages(raw_xml, max_existing_page):
    """Replace visible text on template pages (1..max_existing_page) with 'Lorem ipsum'.

    Operates on the raw XML string, handling both CDATA and HTML-escaped formats.
    """
    replaced_count = 0

    def process_page_match(match):
        nonlocal replaced_count
        page_xml = match.group(0)

        page_num_match = re.search(r'\bnumber="(\d+)"', page_xml)
        if not page_num_match:
            return page_xml

        page_num = int(page_num_match.group(1))
        if page_num > max_existing_page:
            return page_xml

        original = page_xml

        # Handle CDATA format: >Visible text< inside CDATA blocks
        # CRITICAL: Must not replace ]]> (CDATA closing) which the regex can match
        def replace_cdata_text(text_match):
            text_content = text_match.group(0)
            def replace_visible(tm):
                text = tm.group(2)
                if text.strip() and text.strip() != ']]>':
                    return tm.group(1) + 'Lorem ipsum' + tm.group(3)
                return tm.group(0)
            return re.sub(r'(>)([^<]+)(<)', replace_visible, text_content)

        # Handle escaped format: &gt;Visible text&lt;
        def replace_escaped_text(text_match):
            text_content = text_match.group(0)
            def replace_visible(tm):
                text = tm.group(2)
                if text.strip() and text.strip() != ']]>':
                    return tm.group(1) + 'Lorem ipsum' + tm.group(3)
                return tm.group(0)
            return re.sub(r'(&gt;)([^&]+?)(&lt;)', replace_visible, text_content)

        page_xml = re.sub(r'<text\b[^>]*>.*?</text>', replace_cdata_text, page_xml, flags=re.DOTALL)
        page_xml = re.sub(r'<text\b[^>]*>.*?</text>', replace_escaped_text, page_xml, flags=re.DOTALL)

        if page_xml != original:
            replaced_count += 1
        return page_xml

    # Match page blocks - handle both self-closing and full page tags
    raw_xml = re.sub(
        r'<page\b[^>]*\bnumber="\d+"[^>]*>.*?</page>',
        process_page_match,
        raw_xml,
        flags=re.DOTALL
    )

    print(f"  Replaced text with 'Lorem ipsum' on {replaced_count} template pages")
    return raw_xml


def build_media_entry(img):
    """Build a media registry XML entry as a string."""
    modified_date = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    # Escape src path to handle filenames with &, <, >, or "
    safe_src = escape(img["path"], {'"': '&quot;'})
    return (
        f'<media modified="{modified_date}" height="{img["height"]}" '
        f'dateTaken="" webImportAlbum="" enhanceable="UNKNOWN" validated="true" '
        f'guid="{img["guid"]}" ext="{img["ext"]}" width="{img["width"]}" '
        f'importBatchNum="1" cameraModel="unknown" designerImage="false" '
        f'cameraMake="unknown" src="{safe_src}" webImportSource=""/>'
    )


def process_all_batches(blurb_file):
    state = load_batcher_state()
    batches = state['batches']

    if not batches:
        print("No batches to process")
        return

    total_images = sum(b['image_count'] for b in batches)
    print(f"Processing {len(batches)} batches with {total_images} images total")
    print()

    pages_by_count, page_profiles, page_numbers, max_existing, raw_xml, raw_pages = \
        analyze_template(blurb_file)
    available_sizes = set(pages_by_count.keys())

    print("Available template layouts:")
    for count in sorted(pages_by_count.keys()):
        pages = pages_by_count[count]
        profiles = [page_profiles[id(p)] for p in pages]
        unique_profiles = set()
        for prof in profiles:
            unique_profiles.add((prof['portrait'], prof['landscape']))
        profile_strs = [f"{p}P/{l}L" for p, l in sorted(unique_profiles)]
        print(f"  {count} containers: {len(pages)} pages (layouts: {', '.join(profile_strs)})")
    print()

    all_image_data = []
    new_page_xmls = []  # raw XML strings for new pages
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
            use_size = find_best_template_size(len(remaining_images), available_sizes)
            use_size = min(use_size, len(remaining_images))
            if use_size not in pages_by_count:
                for s in sorted(available_sizes, reverse=True):
                    if s <= len(remaining_images):
                        use_size = s
                        break
                else:
                    use_size = min(available_sizes)

            sub_images = remaining_images[:use_size]
            remaining_images = remaining_images[use_size:]
            sub_batch_num += 1

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

            if not batch_image_data:
                continue

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

            template_page = random.choice(best_pages)
            template_profile = page_profiles[id(template_page)]
            template_pn = page_numbers[id(template_page)]

            # Get the RAW XML for this template page (preserves CDATA etc)
            template_raw = raw_pages.get(template_pn)
            if not template_raw:
                print(f"    WARNING: Could not find raw XML for template page {template_pn}")
                continue

            # Assign images to containers by orientation
            ordered_images = assign_images_to_containers_by_orientation(
                batch_image_data, template_profile['orientations']
            )

            # Build the new page using string-based manipulation
            new_page_xml = fill_page_xml(template_raw, page_num, ordered_images)
            new_page_xmls.append(new_page_xml)
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

    # --- String-based XML assembly (preserves CDATA and original formatting) ---
    print(f"\nAssembling final XML ({pages_created} new pages)...")

    # Delete original template pages from <section> (only even count, never covers/masterpages)
    # Template pages have number="1" through number="max_existing"
    print(f"Removing original template pages (1-{max_existing})...")
    template_page_count = max_existing
    delete_count = template_page_count
    if delete_count % 2 != 0:
        delete_count -= 1

    deleted_pages = 0
    if delete_count > 0:
        # Remove template pages by matching their page number within <section>
        # We need to find the <section> block and remove pages within it
        # Process pages from highest to lowest to avoid renumbering issues
        pages_to_delete = list(range(1, delete_count + 1))
        for pn in pages_to_delete:
            # Match both self-closing and content pages
            # Self-closing: <page ... number="N" .../>
            pattern_self_closing = rf'<page\b[^>]*\bnumber="{pn}"[^>]*/>\s*'
            # Content page: <page ... number="N" ...>...</page>
            pattern_content = rf'<page\b[^>]*\bnumber="{pn}"[^/>][^>]*>.*?</page>\s*'

            new_xml = re.sub(pattern_content, '', raw_xml, count=1, flags=re.DOTALL)
            if new_xml == raw_xml:
                new_xml = re.sub(pattern_self_closing, '', raw_xml, count=1)
            if new_xml != raw_xml:
                raw_xml = new_xml
                deleted_pages += 1

        kept = template_page_count - deleted_pages
        print(f"  Removed {deleted_pages} template pages")
        if kept > 0:
            print(f"  Kept {kept} template page(s) to maintain even page count")

    # Replace text with 'Lorem ipsum' on any remaining template pages
    remaining_template = template_page_count - deleted_pages
    if remaining_template > 0:
        print(f"Replacing text with 'Lorem ipsum' on {remaining_template} remaining template page(s)...")
        raw_xml = replace_text_on_template_pages(raw_xml, max_existing)

    # Insert new pages before </section>
    new_pages_block = '\n'.join(new_page_xmls)
    raw_xml = raw_xml.replace('</section>', f'{new_pages_block}\n</section>')

    # Renumber all remaining pages sequentially (1, 2, 3, ...)
    print("Renumbering pages sequentially...")
    page_counter = [0]  # use list for closure mutability
    def renumber_page(m):
        page_counter[0] += 1
        return f'{m.group(1)}{page_counter[0]}{m.group(3)}'

    # Only renumber pages inside <section>...</section>
    section_match = re.search(r'(<section\b[^>]*>)(.*?)(</section>)', raw_xml, re.DOTALL)
    if section_match:
        section_content = section_match.group(2)
        section_content = re.sub(r'(\bnumber=")(\d+)(")', renumber_page, section_content)
        raw_xml = raw_xml[:section_match.start(2)] + section_content + raw_xml[section_match.end(2):]
    total_pages = page_counter[0]
    print(f"  Renumbered {total_pages} pages (1-{total_pages})")

    # Write the assembled XML
    with open('/tmp/bbf2_updated.xml', 'w', encoding='utf-8') as f:
        f.write(raw_xml)

    filesize = os.path.getsize('/tmp/bbf2_updated.xml')
    print(f"Updated XML size: {filesize:,} bytes")

    # Verify page count (string-based, avoids ET.parse which can't handle CDATA)
    with open('/tmp/bbf2_updated.xml', 'r', encoding='utf-8') as f:
        verify_xml = f.read()
    verify_count = len(re.findall(r'<page\b[^>]*\bnumber="\d+"', verify_xml))
    print(f"Pages in final XML: {verify_count}")

    # Update archive with the string-assembled XML (preserves CDATA)
    result = subprocess.run(
        ['sqlite3', blurb_file,
         f"UPDATE Files SET filecontent=readfile('/tmp/bbf2_updated.xml'), "
         f"filesize={filesize}, filedate=datetime('now') WHERE filepath='bbf2.xml';"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"ERROR updating archive: {result.stderr}")
        sys.exit(1)

    # Verify archive update
    subprocess.run(['sqlite3', blurb_file,
                   "SELECT writefile('/tmp/bbf2_verify.xml', filecontent) FROM Files WHERE filepath='bbf2.xml';"],
                  capture_output=True)
    verify_size = os.path.getsize('/tmp/bbf2_verify.xml')
    print(f"Archive XML size: {verify_size:,} bytes (expected {filesize:,})")

    # Update media_registry.xml using string-based insertion
    print("\nUpdating media registry...")
    subprocess.run(
        ['sqlite3', blurb_file,
         "SELECT writefile('/tmp/media_registry.xml', filecontent) FROM Files WHERE filepath='media_registry.xml';"],
        capture_output=True
    )

    with open('/tmp/media_registry.xml', 'r', encoding='utf-8') as f:
        mr_xml = f.read()

    # Truncate at first </medialist> to discard any trailing garbage
    # (some templates have corrupt data after the closing tag)
    end_tag = '</medialist>'
    end_idx = mr_xml.find(end_tag)
    if end_idx != -1:
        truncated = mr_xml[end_idx + len(end_tag):]
        if truncated.strip():
            print(f"  Cleaned {len(truncated):,} bytes of trailing data after </medialist>")
        mr_xml = mr_xml[:end_idx + len(end_tag)]

    # Build media entries
    media_entries = '\n'.join(build_media_entry(img) for img in all_image_data)

    # Insert before </images> (count=1 to avoid corrupting XML when multiple </images> exist)
    if '</images>' in mr_xml:
        mr_xml = mr_xml.replace('</images>', f'{media_entries}\n</images>', 1)
    elif '<images/>' in mr_xml:
        mr_xml = mr_xml.replace('<images/>', f'<images>\n{media_entries}\n</images>', 1)
    else:
        print("WARNING: Could not find <images> element in media_registry.xml")

    # Validate media_registry.xml is well-formed before writing to archive
    try:
        ET.fromstring(mr_xml)
    except ET.ParseError as e:
        print(f"ERROR: media_registry.xml is not valid XML after update: {e}")
        sys.exit(1)

    with open('/tmp/media_registry_updated.xml', 'w', encoding='utf-8') as f:
        f.write(mr_xml)

    mr_size = os.path.getsize('/tmp/media_registry_updated.xml')
    subprocess.run(
        ['sqlite3', blurb_file,
         f"UPDATE Files SET filecontent=readfile('/tmp/media_registry_updated.xml'), "
         f"filesize={mr_size}, filedate=datetime('now') WHERE filepath='media_registry.xml';"],
        capture_output=True
    )

    # Cleanup temp files
    for f in ['/tmp/bbf2_work.xml', '/tmp/bbf2_updated.xml', '/tmp/bbf2_verify.xml',
              '/tmp/media_registry.xml', '/tmp/media_registry_updated.xml']:
        if os.path.exists(f):
            os.remove(f)

    # Final verification
    print()
    print("=" * 60)
    print("FINAL VERIFICATION")
    print("=" * 60)

    archive_result = subprocess.run(
        ['sqlite3', blurb_file,
         "SELECT COUNT(*) FROM Files WHERE filepath LIKE 'images/%';"],
        capture_output=True, text=True
    )
    total_archive_count = int(archive_result.stdout.strip())

    subprocess.run(['sqlite3', blurb_file,
                   "SELECT writefile('/tmp/bbf2_final_check.xml', filecontent) FROM Files WHERE filepath='bbf2.xml';"],
                  capture_output=True)

    with open('/tmp/bbf2_final_check.xml', 'r', encoding='utf-8') as f:
        final_xml = f.read()

    # Count all image refs in section pages
    xml_ref_count = 0
    for page_match in re.finditer(r'<page\b[^>]*\bnumber="(\d+)"[^>]*>.*?</page>', final_xml, re.DOTALL):
        page_content = page_match.group(0)
        img_refs = len(re.findall(r'<image\b[^>]*\bsrc="[^"]+', page_content))
        xml_ref_count += img_refs

    subprocess.run(['sqlite3', blurb_file,
                   "SELECT writefile('/tmp/media_registry_final.xml', filecontent) FROM Files WHERE filepath='media_registry.xml';"],
                  capture_output=True)

    with open('/tmp/media_registry_final.xml', 'r', encoding='utf-8') as f:
        mr_content = f.read()
    media_count = mr_content.count('<media ')

    expected = sum(b['image_count'] for b in state['batches'])

    print(f"Expected (source images): {expected}")
    print(f"Images processed: {images_added}")
    print(f"Pages created: {pages_created}")
    print(f"Template pages deleted: {deleted_pages}")
    print(f"Final page count: {total_pages}")
    print(f"XML image refs: {xml_ref_count}")
    print(f"Archive image files: {total_archive_count}")
    print(f"Media registry entries: {media_count}")

    all_ok = True
    if images_added != expected:
        print(f"\n  WARNING: {expected - images_added} images failed to add")
        all_ok = False

    if xml_ref_count != images_added:
        print(f"\n  WARNING: XML refs ({xml_ref_count}) != images added ({images_added})")
        all_ok = False

    if all_ok:
        print(f"\n  All counts match: {images_added} images in {pages_created} pages")

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
