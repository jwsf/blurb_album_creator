#!/usr/bin/env python3
"""
Convert a .blurb file to PDF format.

Exports covers, inside covers, and all content pages with images and text.
"""

import os
import sys
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from io import BytesIO

try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    from reportlab.lib.pagesizes import inch
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from PIL import Image
except ImportError as e:
    print(f"ERROR: Required library not found: {e}")
    print("Install with: pip3 install --user --break-system-packages reportlab pillow")
    sys.exit(1)

# Global image cache for temp files (Phase 2 optimization)
# Maps image path -> temp file path to avoid repeated SQLite queries
_image_temp_cache = {}

def preextract_all_images(blurb_file, image_paths):
    """Pre-extract all images to temp files (Phase 2 optimization).

    Extracts all images in bulk to avoid repeated SQLite queries.
    """
    print("  Pre-extracting images...")

    # Extract all images in one pass
    for i, image_path in enumerate(image_paths):
        if image_path in _image_temp_cache:
            continue

        temp_path = f"/tmp/blurb_img_{os.path.basename(image_path)}"

        result = subprocess.run(
            ['sqlite3', blurb_file, f"SELECT writefile('{temp_path}', filecontent) FROM Files WHERE filepath='{image_path}';"],
            capture_output=True,
            text=True
        )

        if result.returncode == 0 and os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
            _image_temp_cache[image_path] = temp_path

        # Progress indicator
        if (i + 1) % 20 == 0:
            print(f"    Extracted {i + 1}/{len(image_paths)} images...")

    print(f"  ✓ Pre-extracted {len(_image_temp_cache)} images")

def extract_bbf2_xml(blurb_file):
    """Extract bbf2.xml from .blurb file."""
    subprocess.run(
        ['sqlite3', blurb_file, "SELECT writefile('/tmp/bbf2_pdf.xml', filecontent) FROM Files WHERE filepath='bbf2.xml';"],
        capture_output=True,
        text=True,
        check=True
    )
    return '/tmp/bbf2_pdf.xml'

def extract_image_from_archive(blurb_file, image_path):
    """Extract an image from the .blurb archive to temp file.

    Phase 2 optimization: Check cache first to avoid repeated SQLite queries.
    """
    # Check cache first (Phase 2 optimization)
    if image_path in _image_temp_cache:
        return _image_temp_cache[image_path]

    # Fallback to direct extraction if not in cache
    temp_path = f"/tmp/blurb_img_{os.path.basename(image_path)}"

    result = subprocess.run(
        ['sqlite3', blurb_file, f"SELECT writefile('{temp_path}', filecontent) FROM Files WHERE filepath='{image_path}';"],
        capture_output=True,
        text=True
    )

    if result.returncode == 0 and os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
        _image_temp_cache[image_path] = temp_path
        return temp_path
    return None

def extract_image_bytes_from_archive(blurb_file, image_path):
    """Extract an image from the .blurb archive as bytes (in-memory, no temp file)."""
    # Use hex() to get binary data as hex, then convert back to bytes
    result = subprocess.run(
        ['sqlite3', blurb_file, f"SELECT hex(filecontent) FROM Files WHERE filepath='{image_path}';"],
        capture_output=True,
        text=True
    )

    if result.returncode == 0 and result.stdout:
        try:
            # Convert hex string to bytes
            hex_str = result.stdout.strip()
            image_bytes = bytes.fromhex(hex_str)
            return image_bytes
        except ValueError:
            return None
    return None

def parse_html_text(cdata_text):
    """Parse HTML-like text from CDATA and return plain text."""
    if not cdata_text:
        return ""

    # Remove CDATA wrapper
    text = cdata_text.strip()
    if text.startswith('<![CDATA['):
        text = text[9:]
    if text.endswith(']]>'):
        text = text[:-3]

    # Simple HTML tag removal
    import re
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)

    return text.strip()

def extract_text_color(cdata_text):
    """Extract color from HTML style attribute in CDATA text."""
    if not cdata_text:
        return (0, 0, 0)  # Default to black

    import re
    # Look for color:#RRGGBB in style attribute
    color_match = re.search(r'color:#([0-9A-Fa-f]{6})', cdata_text)
    if color_match:
        hex_color = color_match.group(1)
        r = int(hex_color[0:2], 16) / 255.0
        g = int(hex_color[2:4], 16) / 255.0
        b = int(hex_color[4:6], 16) / 255.0
        return (r, g, b)

    return (0, 0, 0)  # Default to black

def extract_font_size(cdata_text):
    """Extract font size from HTML style attribute in CDATA text."""
    if not cdata_text:
        return 12  # Default font size

    import re
    # Look for font-size:XXpx in style attribute
    size_match = re.search(r'font-size:(\d+)px', cdata_text)
    if size_match:
        return int(size_match.group(1))

    return 12  # Default font size

def split_coversheet(coversheet, page_width, page_height):
    """Split a coversheet element into separate front and back cover elements.

    Coversheet format has a single wide element with containers for:
    - Back cover (left side)
    - Spine (middle, often contains text that extends onto covers)
    - Front cover (right side)

    Containers are assigned to front or back cover based on their center position.
    This includes spine text containers, which often extend onto the cover areas.

    Returns: (front_cover_element, back_cover_element)
    """
    import copy

    # Get coversheet dimensions
    coversheet_width = float(coversheet.get('width', page_width * 2))
    coversheet_height = float(coversheet.get('height', page_height))
    color = coversheet.get('color', '#ffffff')

    # Calculate where front cover starts (typically right side of coversheet)
    # Front cover is usually from x >= page_width onward
    front_x_threshold = page_width

    # Create synthetic front cover element
    front_cover = ET.Element('front')
    front_cover.set('width', str(page_width))
    front_cover.set('height', str(page_height))
    front_cover.set('color', color)

    # Create synthetic back cover element
    back_cover = ET.Element('back')
    back_cover.set('width', str(page_width))
    back_cover.set('height', str(page_height))
    back_cover.set('color', color)

    # Distribute containers to front or back cover based on position
    # Include spine text containers - they often extend onto the covers
    for container in coversheet.findall('.//container'):
        container_x = float(container.get('x', 0))
        container_width = float(container.get('width', 0))
        container_end = container_x + container_width

        # Clone container
        new_container = copy.deepcopy(container)

        # Determine which cover(s) this container overlaps
        on_back = container_x < front_x_threshold
        on_front = container_end > front_x_threshold

        if on_back and on_front:
            # Container spans both covers - add to both with adjusted positions
            # Add to back cover (clip to back cover boundary)
            back_container = copy.deepcopy(container)
            back_width = front_x_threshold - container_x
            back_container.set('width', str(back_width))
            back_cover.append(back_container)

            # Add to front cover (clip to front cover boundary)
            front_container = copy.deepcopy(container)
            front_container.set('x', '0')  # Starts at left edge of front cover
            front_width = container_end - front_x_threshold
            front_container.set('width', str(front_width))
            front_cover.append(front_container)
        elif container_x >= front_x_threshold:
            # Entirely on front cover - adjust x position
            adjusted_x = container_x - front_x_threshold
            new_container.set('x', str(adjusted_x))
            front_cover.append(new_container)
        else:
            # Entirely on back cover - x position stays the same
            back_cover.append(new_container)

    return front_cover, back_cover

def convert_blurb_to_pdf(blurb_file):
    """Convert .blurb file to PDF."""
    if not os.path.exists(blurb_file):
        print(f"ERROR: File not found: {blurb_file}")
        return False

    # Generate PDF filename
    pdf_file = str(Path(blurb_file).with_suffix('.pdf'))

    print(f"Converting: {os.path.basename(blurb_file)}")
    print(f"Output: {os.path.basename(pdf_file)}")
    print()

    # Extract bbf2.xml
    print("Extracting book structure...")
    xml_file = extract_bbf2_xml(blurb_file)

    # Parse XML
    tree = ET.parse(xml_file)
    root = tree.getroot()

    # Get book info
    info = root.find('.//info')
    title = ""
    author = ""
    if info is not None:
        title_elem = info.find('title')
        author_elem = info.find('author')
        if title_elem is not None and title_elem.text:
            title = title_elem.text.strip()
            if title.startswith('<![CDATA['):
                title = title[9:-3]
        if author_elem is not None and author_elem.text:
            author = author_elem.text.strip()
            if author.startswith('<![CDATA['):
                author = author[9:-3]

    print(f"Title: {title}")
    print(f"Author: {author}")
    print()

    # Get page dimensions from book element
    # The root element IS the book element and contains width/height attributes in points
    book_elem = root

    # Try to get dimensions from book element attributes
    width_str = book_elem.get('width')
    height_str = book_elem.get('height')

    if width_str and height_str:
        try:
            page_width = float(width_str)
            page_height = float(height_str)
            print(f"Page size: {page_width/inch:.2f}\" × {page_height/inch:.2f}\" ({page_width:.0f} × {page_height:.0f} points)")
        except (ValueError, TypeError) as e:
            print(f"Warning: Could not parse dimensions from book element: {e}")
            print(f"  width='{width_str}', height='{height_str}'")
            print("Using default 8\" × 8\" page size")
            page_width = 8 * inch
            page_height = 8 * inch
    else:
        print("Warning: No width/height attributes found on book element")
        print("Using default 8\" × 8\" page size")
        page_width = 8 * inch
        page_height = 8 * inch

    print(f"Aspect ratio: {page_width/page_height:.3f}:1")
    print()

    # Get the content section and covers for later use
    # Try to find section with name="" first (standard format)
    section = root.find('.//section[@name=""]')

    # Fallback: If not found, look for ANY section element
    # Some albums have section without name attribute or with name=None
    if section is None:
        section = root.find('.//section')

    masterpage = root.find('.//masterpage')

    # Find the first available cover type and store front/back for later
    front_cover = None
    back_cover = None
    cover_type_name = None

    for cover_type in ['softcover', 'imagewrap', 'dustjacket']:
        cover = root.find(f'.//cover[@type="{cover_type}"]')
        if cover is not None:
            # Check for separate front/back elements first
            front_cover = cover.find('front')
            back_cover = cover.find('back')

            # If no separate elements, check for coversheet format
            if front_cover is None and back_cover is None:
                coversheet = cover.find('coversheet')
                if coversheet is not None:
                    # Split coversheet into front and back covers
                    front_cover, back_cover = split_coversheet(coversheet, page_width, page_height)

            # Only set cover_type_name if we found at least one cover
            if front_cover is not None or back_cover is not None:
                cover_type_name = cover_type
                break

    # Fallback: If no covers found with standard types, look for ANY cover element
    # Some albums use type="None" instead of specific cover types
    if front_cover is None and back_cover is None:
        covers = root.findall('.//cover')
        for cover in covers:
            # Check for coversheet format
            coversheet = cover.find('coversheet')
            if coversheet is not None:
                # Split coversheet into front and back covers
                front_cover, back_cover = split_coversheet(coversheet, page_width, page_height)
                cover_type_name = cover.get('type', 'unknown')
                break

            # Check for separate front/back elements
            front = cover.find('front')
            back = cover.find('back')
            if front is not None or back is not None:
                front_cover = front
                back_cover = back
                cover_type_name = cover.get('type', 'unknown')
                break

    # Calculate total pages to show progress (excluding inside covers)
    total_pages = 0
    if front_cover is not None:
        total_pages += 1
    # Skip masterpage (inside covers) - not included in PDF
    if section is not None:
        total_pages += len(section.findall('page'))
    if back_cover is not None:
        total_pages += 1

    # Show time estimate
    print(f"Total pages to process: {total_pages}")
    if total_pages > 50:
        print("⚠️  Large album detected: PDF conversion may take several minutes")
        print(f"   Estimated time: {total_pages * 2} - {total_pages * 4} seconds")
    elif total_pages > 20:
        print("⏱  PDF conversion may take 1-2 minutes")
    print()

    # Phase 2 optimization: Pre-extract all images to avoid repeated SQLite queries
    print("Phase 2 optimization: Pre-extracting images...")
    all_image_paths = set()
    for img_elem in root.findall('.//image[@src]'):
        src = img_elem.get('src')
        if src:
            # Build full path in archive
            if not src.startswith('images/'):
                src = f"images/{src}"
            all_image_paths.add(src)

    if all_image_paths:
        preextract_all_images(blurb_file, sorted(all_image_paths))
    print()

    # Create PDF
    c = canvas.Canvas(pdf_file, pagesize=(page_width, page_height))
    c.setTitle(title)
    c.setAuthor(author)

    page_count = 0
    import time
    start_time = time.time()

    # Process front cover as FIRST page of PDF
    if front_cover is not None:
        page_count += 1
        print(f"[{page_count}/{total_pages}] Processing front cover ({cover_type_name})...")
        process_page(c, front_cover, blurb_file, page_width, page_height, f"Front Cover ({cover_type_name})")
        c.showPage()

    # Skip inside covers (masterpage) - not included in PDF

    # Process content pages
    if section is not None:
        pages = sorted(section.findall('page'), key=lambda p: int(p.get('number', 0)))
        print(f"\nProcessing {len(pages)} content pages...")
        for page in pages:
            page_num = page.get('number')
            page_count += 1

            # Show progress every 10 pages for large albums, or every page for small albums
            if total_pages > 50:
                if page_count % 10 == 0:
                    elapsed = time.time() - start_time
                    rate = page_count / elapsed if elapsed > 0 else 0
                    remaining = (total_pages - page_count) / rate if rate > 0 else 0
                    print(f"[{page_count}/{total_pages}] Page {page_num} ({page_count * 100 // total_pages}% complete, ~{int(remaining)}s remaining)")
            else:
                print(f"[{page_count}/{total_pages}] Page {page_num}")

            process_page(c, page, blurb_file, page_width, page_height, f"Page {page_num}")
            c.showPage()

    # Process back cover as LAST page of PDF
    if back_cover is not None:
        page_count += 1
        print(f"\n[{page_count}/{total_pages}] Processing back cover ({cover_type_name})...")
        process_page(c, back_cover, blurb_file, page_width, page_height, f"Back Cover ({cover_type_name})")
        c.showPage()

    # Save PDF
    print(f"\n[{total_pages}/{total_pages}] Saving PDF...")
    c.save()

    elapsed_time = time.time() - start_time
    elapsed_mins = int(elapsed_time // 60)
    elapsed_secs = int(elapsed_time % 60)

    print()
    print(f"✅ Created PDF with {page_count} pages")
    print(f"   Output: {pdf_file}")
    if elapsed_mins > 0:
        print(f"   Time elapsed: {elapsed_mins}m {elapsed_secs}s")
    else:
        print(f"   Time elapsed: {elapsed_secs}s")

    # Cleanup temp files
    os.remove(xml_file)

    return True

def process_page(c, page_elem, blurb_file, page_width, page_height, page_label):
    """Process a single page and add to PDF."""
    # Set background color
    color = page_elem.get('color', '#ffffff')
    if color.startswith('#'):
        r = int(color[1:3], 16) / 255.0
        g = int(color[3:5], 16) / 255.0
        b = int(color[5:7], 16) / 255.0
        c.setFillColorRGB(r, g, b)
        c.rect(0, 0, page_width, page_height, fill=1, stroke=0)

    # Process image containers
    for container in page_elem.findall('.//container[@type="image"]'):
        process_image_container(c, container, blurb_file, page_height)

    # Process text containers
    for container in page_elem.findall('.//container[@type="text"]'):
        process_text_container(c, container, page_height)

def process_image_container(c, container, blurb_file, page_height):
    """Process an image container and draw image on PDF matching .blurb positioning exactly."""
    # Get container dimensions and position
    container_x = float(container.get('x', 0))
    container_y = float(container.get('y', 0))
    container_width = float(container.get('width', 0))
    container_height = float(container.get('height', 0))

    # Find image element
    image_elem = container.find('image')
    if image_elem is None:
        return

    src = image_elem.get('src')
    if not src:
        return

    # Get image positioning attributes from .blurb file
    img_rotate = float(image_elem.get('rotate', 0))
    img_flip = image_elem.get('flip', 'none')
    autolayout = image_elem.get('autolayout', 'none')

    # Build full path in archive (images/filename)
    if not src.startswith('images/'):
        src = f"images/{src}"

    try:
        from PIL import Image as PILImage
        from PIL import ImageOps

        # Extract image from archive
        temp_image = extract_image_from_archive(blurb_file, src)
        if not temp_image:
            return

        # Load and process image
        img = PILImage.open(temp_image)

        # Apply EXIF orientation only if needed (optimization)
        try:
            exif = img.getexif()
            if exif and exif.get(0x0112, 1) != 1:  # 0x0112 = Orientation tag
                img = ImageOps.exif_transpose(img)
        except:
            # If EXIF fails, skip it
            pass

        # Apply rotation if specified
        if img_rotate != 0:
            img = img.rotate(-img_rotate, expand=True)

        # Apply flip if specified
        if img_flip == 'horizontal':
            img = img.transpose(PILImage.FLIP_LEFT_RIGHT)
        elif img_flip == 'vertical':
            img = img.transpose(PILImage.FLIP_TOP_BOTTOM)
        elif img_flip == 'both':
            img = img.transpose(PILImage.FLIP_LEFT_RIGHT)
            img = img.transpose(PILImage.FLIP_TOP_BOTTOM)

        # Get dimensions after transformations
        img_width, img_height = img.size

        # Convert to RGB if needed
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')

        # Save processed image to BytesIO (keeps in memory for drawing)
        # Use quality=80 for balanced quality/speed (Phase 3)
        img_buffer = BytesIO()
        img.save(img_buffer, format='JPEG', quality=80, optimize=False)
        img_buffer.seek(0)

        # Create ImageReader for ReportLab
        image_reader = ImageReader(img_buffer)

        # Clean up original temp file
        os.unlink(temp_image)

        # Calculate scale and position based on autolayout
        if autolayout == 'fill':
            # Calculate scale to fill container (crop to fit)
            scale_x = container_width / img_width
            scale_y = container_height / img_height
            img_scale = max(scale_x, scale_y)  # Use larger scale to ensure full coverage

            # Calculate dimensions after scaling
            scaled_width = img_width * img_scale
            scaled_height = img_height * img_scale

            # Center the image in the container
            img_x = (container_width - scaled_width) / 2
            img_y = (container_height - scaled_height) / 2
        else:
            # Use explicit scale and position from .blurb file
            img_scale = float(image_elem.get('scale', 1.0))
            img_x = float(image_elem.get('x', 0))
            img_y = float(image_elem.get('y', 0))
            scaled_width = img_width * img_scale
            scaled_height = img_height * img_scale

        # Calculate absolute position on page
        img_top_blurb = container_y + img_y
        img_bottom_blurb = img_top_blurb + scaled_height
        abs_x = container_x + img_x
        abs_y = page_height - img_bottom_blurb

        # Container position in PDF coordinates (for clipping)
        container_pdf_y = page_height - container_y - container_height

        # Set up clipping to container bounds
        c.saveState()

        # Create clipping path for container
        clip_path = c.beginPath()
        clip_path.rect(container_x, container_pdf_y, container_width, container_height)
        c.clipPath(clip_path, stroke=0)

        # Draw the image at the exact position specified in .blurb
        c.drawImage(image_reader, abs_x, abs_y,
                   width=scaled_width, height=scaled_height,
                   preserveAspectRatio=True, mask='auto')

        c.restoreState()

    except Exception as e:
        print(f"    Warning: Could not draw image {src}: {e}")

def process_text_container(c, container, page_height):
    """Process a text container and draw text on PDF with correct colors and rotation."""
    # Get container dimensions and position
    x = float(container.get('x', 0))
    y = float(container.get('y', 0))
    width = float(container.get('width', 0))
    height = float(container.get('height', 0))

    # Find text element
    text_elem = container.find('text')
    if text_elem is None or not text_elem.text:
        return

    # Parse text content
    text_content = parse_html_text(text_elem.text)
    if not text_content:
        return

    # Extract color and font size from HTML
    text_color = extract_text_color(text_elem.text)
    font_size = extract_font_size(text_elem.text)

    # Parse transform matrix for rotation
    # Transform format: "a b c d" representing matrix | a  c |
    #                                                  | b  d |
    transform = container.get('transform', '1 0 0 1')
    rotation_angle = 0

    if transform and transform != '1 0 0 1':
        try:
            parts = transform.split()
            if len(parts) == 4:
                m_a, m_b, m_c, m_d = [float(p) for p in parts]

                # Calculate rotation angle from matrix
                # Common cases:
                # '0 1 -1 0' = 90° counterclockwise
                # '0 -1 1 0' = 90° clockwise (270° or -90°)
                # '-1 0 0 -1' = 180°
                # '1 0 0 1' = no rotation

                import math
                if abs(m_a) < 0.01 and abs(m_b - 1) < 0.01 and abs(m_c + 1) < 0.01 and abs(m_d) < 0.01:
                    rotation_angle = 90  # 90° CCW
                elif abs(m_a) < 0.01 and abs(m_b + 1) < 0.01 and abs(m_c - 1) < 0.01 and abs(m_d) < 0.01:
                    rotation_angle = -90  # 90° CW
                elif abs(m_a + 1) < 0.01 and abs(m_b) < 0.01 and abs(m_c) < 0.01 and abs(m_d + 1) < 0.01:
                    rotation_angle = 180  # 180°
                else:
                    # Generic case: atan2(b, a) gives rotation angle
                    rotation_angle = math.degrees(math.atan2(m_b, m_a))
        except (ValueError, AttributeError):
            pass

    # Convert y coordinate (PDF origin is bottom-left, blurb is top-left)
    pdf_y = page_height - y - height

    # Set text color from .blurb file
    c.setFillColorRGB(text_color[0], text_color[1], text_color[2])

    # Quick check: estimate if text will fit at original size
    # This avoids the expensive auto-sizing loop for most containers
    c.setFont("Helvetica", font_size)
    line_height = font_size * 1.3  # 1.3x for proper spacing with descenders
    estimated_lines = len(text_content) / (width / (font_size * 0.5))  # Rough estimate
    estimated_height = estimated_lines * line_height

    # Auto-scale font size to fit container
    actual_font_size = font_size
    min_font_size = max(6, font_size * 0.5)  # Don't go below 6pt or 50% of original
    lines = []

    # Always try to fit text by adjusting font size
    while actual_font_size >= min_font_size:
        c.setFont("Helvetica", actual_font_size)
        line_height = actual_font_size * 1.3  # 1.3x for proper spacing with descenders

        # Word wrap at current font size
        lines = []
        words = text_content.split()
        current_line = []

        for word in words:
            test_line = ' '.join(current_line + [word])
            if c.stringWidth(test_line, "Helvetica", actual_font_size) <= width - 10:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]

        if current_line:
            lines.append(' '.join(current_line))

        # Check if all lines fit in container height (with space for descenders on last line)
        descender_space = actual_font_size * 0.3  # Extra space for descenders on last line
        total_height = len(lines) * line_height + descender_space
        if total_height <= height:
            # Text fits! Use this font size
            break

        # Text doesn't fit, try smaller font
        actual_font_size -= 1

    # If still doesn't fit at minimum size, truncate lines
    line_height = actual_font_size * 1.3  # 1.3x for proper spacing with descenders
    descender_space = actual_font_size * 0.3
    max_lines = int((height - descender_space) / line_height)
    if len(lines) > max_lines:
        lines = lines[:max_lines]

    # Apply clipping to keep text within container bounds
    c.saveState()

    # Create clipping path for container (prevent text overflow)
    clip_path = c.beginPath()
    clip_path.rect(x, pdf_y, width, height)
    c.clipPath(clip_path, stroke=0)

    if rotation_angle != 0:
        # For rotated text, we need to adjust the origin point
        # Rotation in ReportLab is around the origin, so we translate first
        if abs(rotation_angle - 90) < 0.1:
            # 90° CCW: text reads upward (spine text)
            # After 90° CCW rotation:
            #   - Rotated +X axis points upward in page space (original +Y)
            #   - Rotated +Y axis points leftward in page space (original -X)
            # Place origin at the right edge of where text should appear horizontally
            text_x = x + height  # Right edge of text band in page space
            text_y = pdf_y       # Bottom of text area
            c.translate(text_x, text_y)
            c.rotate(90)
            # Draw text going upward: increment rotated X (page Y), keep rotated Y at 0
            for i, line in enumerate(lines):
                # Rotated X increases = page Y increases (upward)
                # Rotated Y = 0 keeps us at the origin's page X position
                c.drawString(5 + i * line_height, 0, line)
        elif abs(rotation_angle + 90) < 0.1:
            # 90° CW: text reads downward (spine text)
            # After 90° CW rotation:
            #   - Rotated +X axis points downward in page space (original -Y)
            #   - Rotated +Y axis points rightward in page space (original +X)
            # Place origin at the left edge of where text should appear horizontally
            text_x = x           # Left edge of text band in page space
            text_y = pdf_y + height  # Top of text area (will draw downward)
            c.translate(text_x, text_y)
            c.rotate(-90)
            # Draw text going downward: increment rotated X (page -Y), keep rotated Y at 0
            for i, line in enumerate(lines):
                # Rotated X increases = page Y decreases (downward)
                # Rotated Y = 0 keeps us at the origin's page X position
                c.drawString(5 + i * line_height, 0, line)
        else:
            # Generic rotation
            text_x = x + width / 2
            text_y = pdf_y + height / 2
            c.translate(text_x, text_y)
            c.rotate(rotation_angle)
            for i, line in enumerate(lines):
                c.drawString(-c.stringWidth(line, "Helvetica", font_size) / 2, -i * line_height, line)

    else:
        # No rotation - draw normally
        text_y = pdf_y + height - line_height  # Start from top of container

        # Draw text with clipping applied (from saveState above)
        for line in lines:
            c.drawString(x + 5, text_y, line)
            text_y -= line_height

    # Restore graphics state (removes clipping)
    c.restoreState()

def main():
    if len(sys.argv) < 2:
        print("Usage: blurb_to_pdf.py <blurb_file>")
        print()
        print("Converts a .blurb file to PDF format.")
        print("The PDF will include covers, inside covers, and all content pages")
        print("with embedded images and text.")
        sys.exit(1)

    blurb_file = sys.argv[1]

    if not blurb_file.endswith('.blurb'):
        print("ERROR: File must have .blurb extension")
        sys.exit(1)

    success = convert_blurb_to_pdf(blurb_file)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
