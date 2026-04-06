#!/usr/bin/env python3
"""
Convert a .blurb file to PDF format.

Exports covers, inside covers, and all content pages with images and text.

Stand-alone usage
-----------------
    python3 blurb_to_pdf.py <blurb_file>

The output PDF is written to the same directory with the same base name:
    python3 blurb_to_pdf.py "outputs/My Album 2026-03-21 10:00.blurb"
    # -> outputs/My Album 2026-03-21 10:00.pdf

Requirements
------------
    pip3 install --user --break-system-packages reportlab pillow

- Python 3
- reportlab (PDF generation)
- Pillow / PIL (image processing and EXIF orientation)
- macOS with Arial fonts in /System/Library/Fonts/Supplemental/ (falls back
  to Helvetica if Arial is not available)
- sqlite3 CLI (ships with macOS; used to extract images from the .blurb
  SQLite archive)

What the PDF contains
---------------------
- Front and back covers (softcover, imagewrap, or dustjacket)
- All content pages with images positioned and cropped to match Bookwright
- Text containers with font size, color, alignment, and rotation preserved
- Background colors per page
- EXIF orientation applied automatically to images
- PDF metadata (title, author) from the .blurb book info

What the PDF omits
------------------
- Inside covers (masterpage section)
- Spine (not applicable to PDF)
- Elements that sit entirely on the spine area

Notes
-----
- Conversion is CPU and memory intensive.  When converting multiple .blurb
  files, run them one at a time — do not run in parallel.
- Large albums (50+ pages) can take several minutes.  The script prints
  progress indicators and time estimates while it runs.
- An existing PDF at the output path is overwritten without prompting.
- Exit code 0 on success, 1 on failure.
"""

import gc
import os
import sys
import hashlib
import tempfile
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
    from reportlab.pdfbase.pdfmetrics import registerFontFamily
    from PIL import Image
except ImportError as e:
    print(f"ERROR: Required library not found: {e}")
    print("Install with: pip3 install --user --break-system-packages reportlab pillow")
    sys.exit(1)

# Global image cache for temp files (Phase 2 optimization)
# Maps image path -> temp file path to avoid repeated SQLite queries
_image_temp_cache = {}

# Whether fonts have been registered
_fonts_registered = False


def _sql_quote(value):
    """Escape a Python string as a SQLite single-quoted literal."""
    return str(value).replace("'", "''")


def _temp_image_path(image_path):
    """Create a collision-resistant temp image path for archive extraction."""
    suffix = Path(image_path).suffix or ".img"
    digest = hashlib.sha1(image_path.encode("utf-8")).hexdigest()[:16]
    return f"/tmp/blurb_img_{os.getpid()}_{digest}{suffix}"


def _cleanup_temp_files(xml_file=None):
    """Best-effort cleanup for temporary XML and extracted image files."""
    if xml_file and os.path.exists(xml_file):
        try:
            os.remove(xml_file)
        except OSError:
            pass
    for temp_path in _image_temp_cache.values():
        try:
            os.remove(temp_path)
        except OSError:
            pass
    _image_temp_cache.clear()

def register_fonts():
    """Register Arial TTF fonts from macOS system fonts, with Helvetica fallback."""
    global _fonts_registered
    if _fonts_registered:
        return

    font_dir = "/System/Library/Fonts/Supplemental"
    font_files = {
        "Arial": os.path.join(font_dir, "Arial.ttf"),
        "Arial-Bold": os.path.join(font_dir, "Arial Bold.ttf"),
        "Arial-Italic": os.path.join(font_dir, "Arial Italic.ttf"),
        "Arial-BoldItalic": os.path.join(font_dir, "Arial Bold Italic.ttf"),
    }

    all_found = all(os.path.exists(f) for f in font_files.values())
    if all_found:
        for name, path in font_files.items():
            pdfmetrics.registerFont(TTFont(name, path))
        registerFontFamily(
            "Arial",
            normal="Arial",
            bold="Arial-Bold",
            italic="Arial-Italic",
            boldItalic="Arial-BoldItalic",
        )
        print("Registered Arial font family from system fonts")
    else:
        # Fallback: register Helvetica aliases so resolve_font_name always works
        print("Warning: Arial TTF not found, falling back to Helvetica")

    _fonts_registered = True


def resolve_font_name(bold=False, italic=False):
    """Return the registered font name for the given bold/italic combination.

    Uses Arial if registered, otherwise falls back to Helvetica.
    """
    font_dir = "/System/Library/Fonts/Supplemental"
    arial_available = os.path.exists(os.path.join(font_dir, "Arial.ttf"))

    if arial_available:
        if bold and italic:
            return "Arial-BoldItalic"
        elif bold:
            return "Arial-Bold"
        elif italic:
            return "Arial-Italic"
        else:
            return "Arial"
    else:
        # Helvetica built-in variants
        if bold and italic:
            return "Helvetica-BoldOblique"
        elif bold:
            return "Helvetica-Bold"
        elif italic:
            return "Helvetica-Oblique"
        else:
            return "Helvetica"

def preextract_all_images(blurb_file, image_paths):
    """Pre-extract all images to temp files (Phase 2 optimization).

    Extracts all images in bulk to avoid repeated SQLite queries.
    """
    print("  Pre-extracting images...")

    # Extract all images in one pass
    for i, image_path in enumerate(image_paths):
        if image_path in _image_temp_cache:
            continue

        temp_path = _temp_image_path(image_path)
        sql_image = _sql_quote(image_path)
        sql_temp = _sql_quote(temp_path)

        result = subprocess.run(
            ['sqlite3', blurb_file, f"SELECT writefile('{sql_temp}', filecontent) FROM Files WHERE filepath='{sql_image}';"],
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
    handle, temp_path = tempfile.mkstemp(prefix=f"bbf2_pdf_{os.getpid()}_", suffix=".xml")
    os.close(handle)
    sql_temp = _sql_quote(temp_path)
    subprocess.run(
        ['sqlite3', blurb_file, f"SELECT writefile('{sql_temp}', filecontent) FROM Files WHERE filepath='bbf2.xml';"],
        capture_output=True,
        text=True,
        check=True
    )
    return temp_path

def extract_image_from_archive(blurb_file, image_path):
    """Extract an image from the .blurb archive to temp file.

    Phase 2 optimization: Check cache first to avoid repeated SQLite queries.
    """
    # Check cache first (Phase 2 optimization)
    if image_path in _image_temp_cache:
        return _image_temp_cache[image_path]

    # Fallback to direct extraction if not in cache
    temp_path = _temp_image_path(image_path)
    sql_image = _sql_quote(image_path)
    sql_temp = _sql_quote(temp_path)

    result = subprocess.run(
        ['sqlite3', blurb_file, f"SELECT writefile('{sql_temp}', filecontent) FROM Files WHERE filepath='{sql_image}';"],
        capture_output=True,
        text=True
    )

    if result.returncode == 0 and os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
        _image_temp_cache[image_path] = temp_path
        return temp_path
    return None

def extract_image_bytes_from_archive(blurb_file, image_path):
    """Extract an image from the .blurb archive as bytes (in-memory, no temp file)."""
    sql_image = _sql_quote(image_path)
    # Use hex() to get binary data as hex, then convert back to bytes
    result = subprocess.run(
        ['sqlite3', blurb_file, f"SELECT hex(filecontent) FROM Files WHERE filepath='{sql_image}';"],
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

def parse_rich_text(cdata_text):
    """Parse HTML text from CDATA into structured paragraph objects.

    Returns a list of paragraph dicts:
    [
        {
            "alignment": "center" | "left" | "right",
            "runs": [
                {
                    "text": "Hello",
                    "font_size": 12,
                    "bold": False,
                    "italic": False,
                    "color": (0.0, 0.0, 0.0),
                }
            ]
        },
        ...
    ]
    """
    import re
    from html.parser import HTMLParser

    if not cdata_text:
        return []

    # Remove CDATA wrapper
    text = cdata_text.strip()
    if text.startswith('<![CDATA['):
        text = text[9:]
    if text.endswith(']]>'):
        text = text[:-3]
    text = text.strip()

    if not text:
        return []

    class RichTextParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.paragraphs = []
            self.current_para = None
            self.bold_depth = 0
            self.italic_depth = 0
            # Track style-based bold/italic per span (stack of bools)
            self.span_bold_stack = []
            self.span_italic_stack = []
            self.current_font_size = 12
            self.current_color = (0.0, 0.0, 0.0)

        def handle_starttag(self, tag, attrs):
            attrs_dict = dict(attrs)
            tag_lower = tag.lower()

            if tag_lower == 'p':
                alignment = "left"
                cls = attrs_dict.get('class', '')
                if 'align-center' in cls:
                    alignment = "center"
                elif 'align-right' in cls:
                    alignment = "right"
                self.current_para = {"alignment": alignment, "runs": []}

            elif tag_lower == 'span':
                style = attrs_dict.get('style', '')
                # Extract font-size (handles both "font-size:12px" and "font-size: 12px")
                size_match = re.search(r'font-size:\s*(\d+)px', style)
                if size_match:
                    self.current_font_size = int(size_match.group(1))
                # Extract color (handles both "color:#fff" and "color: #fff")
                color_match = re.search(r'(?<![a-z-])color:\s*#([0-9A-Fa-f]{6})', style)
                if color_match:
                    hex_color = color_match.group(1)
                    r = int(hex_color[0:2], 16) / 255.0
                    g = int(hex_color[2:4], 16) / 255.0
                    b = int(hex_color[4:6], 16) / 255.0
                    self.current_color = (r, g, b)
                # Extract font-weight: bold from style attribute
                span_bold = bool(re.search(r'font-weight:\s*bold', style))
                if span_bold:
                    self.bold_depth += 1
                self.span_bold_stack.append(span_bold)
                # Extract font-style: italic from style attribute
                span_italic = bool(re.search(r'font-style:\s*italic', style))
                if span_italic:
                    self.italic_depth += 1
                self.span_italic_stack.append(span_italic)

            elif tag_lower == 'strong' or tag_lower == 'b':
                self.bold_depth += 1

            elif tag_lower == 'em' or tag_lower == 'i':
                self.italic_depth += 1

        def handle_endtag(self, tag):
            tag_lower = tag.lower()
            if tag_lower == 'p':
                if self.current_para is not None:
                    self.paragraphs.append(self.current_para)
                    self.current_para = None
            elif tag_lower == 'span':
                # Undo style-based bold/italic for this span
                if self.span_bold_stack:
                    if self.span_bold_stack.pop():
                        self.bold_depth = max(0, self.bold_depth - 1)
                if self.span_italic_stack:
                    if self.span_italic_stack.pop():
                        self.italic_depth = max(0, self.italic_depth - 1)
            elif tag_lower == 'strong' or tag_lower == 'b':
                self.bold_depth = max(0, self.bold_depth - 1)
            elif tag_lower == 'em' or tag_lower == 'i':
                self.italic_depth = max(0, self.italic_depth - 1)

        def handle_data(self, data):
            if self.current_para is None:
                return
            # Decode HTML entities handled by HTMLParser automatically
            # Strip zero-width spaces and other invisible Unicode
            cleaned = data.replace('\u200b', '').replace('\u200c', '').replace('\u200d', '')
            cleaned = cleaned.replace('\ufeff', '')  # BOM
            if not cleaned or cleaned.isspace():
                return
            self.current_para["runs"].append({
                "text": cleaned,
                "font_size": self.current_font_size,
                "bold": self.bold_depth > 0,
                "italic": self.italic_depth > 0,
                "color": self.current_color,
            })

        def handle_entityref(self, name):
            # HTMLParser calls handle_data for most entities, but handle edge cases
            entity_map = {'nbsp': ' ', 'amp': '&', 'lt': '<', 'gt': '>'}
            char = entity_map.get(name, '')
            if char:
                self.handle_data(char)

    parser = RichTextParser()
    parser.feed(text)

    # Filter out paragraphs with no visible text runs
    return [p for p in parser.paragraphs if p["runs"]]

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
    xml_file = None

    try:
        # Register fonts before any canvas operations
        register_fonts()

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

        # Fallback: covers have no type= attribute (only sku=).
        # Use the book's own SKU to identify the preferred cover type, then
        # find the matching cover.  Fall back to the first available cover.
        if front_cover is None and back_cover is None:
            book_sku = book_elem.get('sku', '')
            sku_preference = []
            for sku_pat, ct_name in [("-IW-", "imagewrap"), ("-SC-", "softcover"), ("-DJ-", "dustjacket")]:
                if sku_pat in book_sku:
                    sku_preference.insert(0, (sku_pat, ct_name))
                else:
                    sku_preference.append((sku_pat, ct_name))

            covers = root.findall('.//cover')

            def _try_cover(cover):
                """Return (front, back, type_name) from a cover element, or (None, None, None)."""
                coversheet = cover.find('coversheet')
                if coversheet is not None:
                    fc, bc = split_coversheet(coversheet, page_width, page_height)
                    return fc, bc, cover.get('type', cover.get('sku', 'unknown'))
                front = cover.find('front')
                back = cover.find('back')
                if front is not None or back is not None:
                    return front, back, cover.get('type', cover.get('sku', 'unknown'))
                return None, None, None

            # Try covers in SKU-preference order
            cover_map = {}
            for cover in covers:
                sku = cover.get('sku', '')
                for sku_pat, ct_name in sku_preference:
                    if sku_pat in sku:
                        cover_map[ct_name] = cover
                        break

            for _, ct_name in sku_preference:
                if ct_name in cover_map:
                    fc, bc, ctn = _try_cover(cover_map[ct_name])
                    if fc is not None or bc is not None:
                        front_cover, back_cover, cover_type_name = fc, bc, ct_name
                        break

            # Last resort: first cover with any content
            if front_cover is None and back_cover is None:
                for cover in covers:
                    fc, bc, ctn = _try_cover(cover)
                    if fc is not None or bc is not None:
                        front_cover, back_cover, cover_type_name = fc, bc, ctn
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

            # Periodically force garbage collection to reclaim image memory
                if page_count % 10 == 0:
                    gc.collect()

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

        return True
    except Exception as exc:
        print(f"ERROR: Failed to convert .blurb to PDF: {exc}")
        return False
    finally:
        _cleanup_temp_files(xml_file)

def process_page(c, page_elem, blurb_file, page_width, page_height, page_label):
    """Process a single page and add to PDF."""
    # Set background color
    # Colors can be #RRGGBB (6 hex) or #RRGGBBAA (8 hex with alpha).
    # Alpha 00 = fully transparent, meaning "no background" — treat as white for PDF.
    color = page_elem.get('color', '#ffffff')
    if color.startswith('#'):
        hex_digits = color[1:]
        alpha = 1.0
        if len(hex_digits) == 8:
            alpha = int(hex_digits[6:8], 16) / 255.0
            hex_digits = hex_digits[:6]
        if alpha == 0:
            # Fully transparent background — use white in PDF
            r, g, b = 1.0, 1.0, 1.0
        else:
            r = int(hex_digits[0:2], 16) / 255.0
            g = int(hex_digits[2:4], 16) / 255.0
            b = int(hex_digits[4:6], 16) / 255.0
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

        # Free memory: close PIL image and BytesIO buffer
        img.close()
        img_buffer.close()
        del img, img_buffer, image_reader

    except Exception as e:
        print(f"    Warning: Could not draw image {src}: {e}")

def _word_wrap_runs(c, runs, max_width):
    """Word-wrap a list of text runs into lines that fit within max_width.

    Each run has: text, font_size, bold, italic, color.
    Returns a list of lines, where each line is a list of run fragments:
        [{"text": ..., "font_name": ..., "font_size": ..., "color": ..., "width": ...}, ...]
    """
    lines = []
    current_line = []
    current_width = 0.0

    for run in runs:
        font_name = resolve_font_name(bold=run["bold"], italic=run["italic"])
        font_size = run["font_size"]
        color = run["color"]
        words = run["text"].split()

        for i, word in enumerate(words):
            # Add space before word if not the first item on the line
            prefix = " " if current_line and i > 0 or (current_line and i == 0) else ""
            # If this is the first word of a new run but line already has content, add space
            if i == 0 and current_line:
                # Check if previous run ended with space or this run starts fresh
                prefix = " "

            test_text = prefix + word
            word_width = c.stringWidth(test_text, font_name, font_size)

            if current_width + word_width <= max_width or not current_line:
                # Word fits on current line (or line is empty, must add at least one word)
                current_line.append({
                    "text": test_text,
                    "font_name": font_name,
                    "font_size": font_size,
                    "color": color,
                    "width": word_width,
                })
                current_width += word_width
            else:
                # Word doesn't fit, start a new line
                lines.append(current_line)
                text_no_prefix = word
                word_width_no_prefix = c.stringWidth(text_no_prefix, font_name, font_size)
                current_line = [{
                    "text": text_no_prefix,
                    "font_name": font_name,
                    "font_size": font_size,
                    "color": color,
                    "width": word_width_no_prefix,
                }]
                current_width = word_width_no_prefix

    if current_line:
        lines.append(current_line)

    return lines


def _measure_layout(c, paragraphs, container_width, scale=1.0):
    """Measure total height of paragraphs with optional scale factor applied to font sizes.

    Returns (total_height, layout) where layout is a list of:
        {"line_fragments": [...], "alignment": str, "line_height": float, "font_size": float}
    """
    layout = []
    total_height = 0.0

    for para in paragraphs:
        # Apply scale to runs
        scaled_runs = []
        for run in para["runs"]:
            scaled_runs.append({
                "text": run["text"],
                "font_size": max(6, run["font_size"] * scale),
                "bold": run["bold"],
                "italic": run["italic"],
                "color": run["color"],
            })

        # Determine the dominant font size for line height
        max_font_size = max(r["font_size"] for r in scaled_runs)
        line_height = max_font_size * 1.3

        # Word-wrap with margin
        wrapped_lines = _word_wrap_runs(c, scaled_runs, container_width - 10)

        for line_frags in wrapped_lines:
            layout.append({
                "line_fragments": line_frags,
                "alignment": para["alignment"],
                "line_height": line_height,
                "font_size": max_font_size,
            })
            total_height += line_height

    return total_height, layout


def process_text_container(c, container, page_height):
    """Process a text container and draw text on PDF with rich formatting."""
    import math

    # Get container dimensions and position
    x = float(container.get('x', 0))
    y = float(container.get('y', 0))
    width = float(container.get('width', 0))
    height = float(container.get('height', 0))

    # Find text element
    text_elem = container.find('text')
    if text_elem is None or not text_elem.text:
        return

    # Parse rich text into structured paragraphs
    paragraphs = parse_rich_text(text_elem.text)
    if not paragraphs:
        return

    # Parse transform matrix for rotation
    transform = container.get('transform', '1 0 0 1')
    rotation_angle = 0

    if transform and transform != '1 0 0 1':
        try:
            parts = transform.split()
            if len(parts) == 4:
                m_a, m_b, m_c, m_d = [float(p) for p in parts]

                if abs(m_a) < 0.01 and abs(m_b - 1) < 0.01 and abs(m_c + 1) < 0.01 and abs(m_d) < 0.01:
                    rotation_angle = 90
                elif abs(m_a) < 0.01 and abs(m_b + 1) < 0.01 and abs(m_c - 1) < 0.01 and abs(m_d) < 0.01:
                    rotation_angle = -90
                elif abs(m_a + 1) < 0.01 and abs(m_b) < 0.01 and abs(m_c) < 0.01 and abs(m_d + 1) < 0.01:
                    rotation_angle = 180
                else:
                    rotation_angle = math.degrees(math.atan2(m_b, m_a))
        except (ValueError, AttributeError):
            pass

    # Convert y coordinate (PDF origin is bottom-left, blurb is top-left)
    pdf_y = page_height - y - height

    # Determine effective text area for rotated containers
    if abs(rotation_angle) in (90, 270):
        text_area_width = height
        text_area_height = width
    else:
        text_area_width = width
        text_area_height = height

    # Auto-scale: try scale=1.0 first, reduce if text overflows
    scale = 1.0
    min_scale = 0.5
    total_h, layout = _measure_layout(c, paragraphs, text_area_width, scale)

    while total_h > text_area_height and scale > min_scale:
        scale -= 0.05
        total_h, layout = _measure_layout(c, paragraphs, text_area_width, scale)

    # Truncate lines that exceed container height
    truncated_layout = []
    used_height = 0.0
    for item in layout:
        if used_height + item["line_height"] > text_area_height + 1:  # +1 for rounding tolerance
            break
        truncated_layout.append(item)
        used_height += item["line_height"]
    layout = truncated_layout

    # Apply clipping to keep text within container bounds.
    # Extend the bottom of the clip rect by 3 points so that character
    # descenders (which extend below the baseline) are not clipped when
    # the last line's baseline sits near the container bottom.
    c.saveState()
    clip_path = c.beginPath()
    clip_path.rect(x, pdf_y - 3, width, height + 3)
    c.clipPath(clip_path, stroke=0)

    def draw_layout_lines(layout, origin_x, origin_y, area_width):
        """Draw layout lines starting from origin, moving downward."""
        cursor_y = origin_y
        for item in layout:
            cursor_y -= item["line_height"]
            alignment = item["alignment"]

            # Calculate total line width for centering/right alignment
            total_line_width = sum(frag["width"] for frag in item["line_fragments"])

            if alignment == "center":
                draw_x = origin_x + (area_width - total_line_width) / 2
            elif alignment == "right":
                draw_x = origin_x + area_width - total_line_width - 5
            else:
                draw_x = origin_x + 5  # Left with small margin

            for frag in item["line_fragments"]:
                c.setFillColorRGB(frag["color"][0], frag["color"][1], frag["color"][2])
                c.setFont(frag["font_name"], frag["font_size"])
                c.drawString(draw_x, cursor_y, frag["text"])
                draw_x += frag["width"]

    if rotation_angle != 0:
        if abs(rotation_angle - 90) < 0.1:
            # 90 CCW: text reads upward (spine text)
            c.translate(x + height, pdf_y)
            c.rotate(90)
            # In rotated space, width=height of container, height=width of container
            draw_layout_lines(layout, 0, text_area_height, text_area_width)
        elif abs(rotation_angle + 90) < 0.1:
            # 90 CW: text reads downward
            c.translate(x, pdf_y + height)
            c.rotate(-90)
            draw_layout_lines(layout, 0, text_area_height, text_area_width)
        else:
            # Generic rotation
            c.translate(x + width / 2, pdf_y + height / 2)
            c.rotate(rotation_angle)
            draw_layout_lines(layout, -text_area_width / 2, text_area_height / 2, text_area_width)
    else:
        # No rotation - draw normally
        draw_layout_lines(layout, x, pdf_y + height, width)

    c.restoreState()

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 blurb_to_pdf.py <blurb_file>")
        print()
        print("Convert a .blurb file (Bookwright SQLite archive) to PDF.")
        print()
        print("The output PDF is written next to the input file with the same")
        print("base name.  An existing PDF at that path is overwritten.")
        print()
        print("Example:")
        print('  python3 blurb_to_pdf.py "outputs/My Album.blurb"')
        print("  # -> outputs/My Album.pdf")
        print()
        print("Requires: pip3 install --user --break-system-packages reportlab pillow")
        sys.exit(1)

    blurb_file = sys.argv[1]

    if not blurb_file.endswith('.blurb'):
        print("ERROR: File must have .blurb extension")
        sys.exit(1)

    success = convert_blurb_to_pdf(blurb_file)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
