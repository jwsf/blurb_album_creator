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
import math
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

# Emoji and other pictographic characters have no glyph in Arial at all,
# and reportlab can't draw them as text even with a fallback font
# registered -- the ones actually used in these books (Apple Color Emoji)
# are color BITMAP glyphs (an sbix table), and reportlab's font support
# only understands vector outlines (glyf/CFF). The only way to show the
# real glyph is to rasterize it separately (via Pillow, which does
# support sbix) and place it as a small inline image within the text
# line instead of drawing it as a character.
_EMOJI_FONT_PATH = "/System/Library/Fonts/Apple Color Emoji.ttc"
_EMOJI_RENDER_SIZE = 160  # a valid sbix strike size for this font
_emoji_image_cache = {}


def _needs_emoji_fallback(ch):
    """Whether a character falls in a pictographic Unicode block with no
    corresponding glyph in Arial, and so needs image-based fallback
    rendering rather than being drawn as text."""
    cp = ord(ch)
    return (
        0x2300 <= cp <= 0x23FF or   # Misc Technical (e.g. ⏱ stopwatch, ⏰ ⌚)
        0x2600 <= cp <= 0x27BF or   # Misc symbols & dingbats (e.g. ✅ ✔)
        0x2B00 <= cp <= 0x2BFF or   # Misc symbols and arrows (e.g. ⭐)
        0x1F000 <= cp <= 0x1FFFF    # Emoji & supplemental pictographs (e.g. 🚶 🍽 🎂)
    )


def _get_emoji_image(ch):
    """Render a single emoji character to an (ImageReader, aspect_ratio)
    pair via Pillow, cached by character. Returns None if the glyph can't
    be rendered (font missing, or genuinely blank for this character).
    """
    if ch in _emoji_image_cache:
        return _emoji_image_cache[ch]
    result = None
    try:
        if os.path.exists(_EMOJI_FONT_PATH):
            from PIL import Image as PILImage, ImageDraw, ImageFont
            font = ImageFont.truetype(_EMOJI_FONT_PATH, size=_EMOJI_RENDER_SIZE)
            pad = 20
            canvas_size = _EMOJI_RENDER_SIZE + 2 * pad
            im = PILImage.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(im)
            draw.text((pad, pad), ch, font=font, embedded_color=True)
            bbox = im.getbbox()
            if bbox is not None:
                cropped = im.crop(bbox)
                buf = BytesIO()
                cropped.save(buf, format="PNG")
                buf.seek(0)
                result = (ImageReader(buf), cropped.width / cropped.height)
    except Exception:
        result = None
    _emoji_image_cache[ch] = result
    return result


def _split_text_and_emoji(text):
    """Split text into (segment, is_emoji) pieces, one emoji character
    per piece, preserving order so word-wrap can treat each emoji as its
    own indivisible unit alongside the surrounding words."""
    pieces = []
    buf = []
    for ch in text:
        if _needs_emoji_fallback(ch):
            if buf:
                pieces.append((''.join(buf), False))
                buf = []
            pieces.append((ch, True))
        else:
            buf.append(ch)
    if buf:
        pieces.append((''.join(buf), False))
    return pieces


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
            self.underline_depth = 0
            # Track style-based bold/italic/underline per span (stack of bools)
            self.span_bold_stack = []
            self.span_italic_stack = []
            self.span_underline_stack = []
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
                # Most paragraphs carry an explicit "line-height:108%" (or
                # 115/116%) inline style -- the actual leading Bookwright
                # uses, nowhere close to the flat 1.3x this renderer used
                # to assume for every line regardless. A paragraph with no
                # inline override relies on the "line-height-qt" CSS class
                # (defined in Bookwright's own stylesheet, not present in
                # this archive) for its default; 108% is by far the most
                # common explicit value in practice, so it's used as the
                # fallback for those too rather than guessing something
                # further off.
                p_style = attrs_dict.get('style', '')
                lh_match = re.search(r'line-height:\s*(\d+(?:\.\d+)?)%', p_style)
                line_height_ratio = float(lh_match.group(1)) / 100.0 if lh_match else 1.08
                self.current_para = {
                    "alignment": alignment,
                    "runs": [],
                    "line_height_ratio": line_height_ratio,
                }

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
                # Underline is marked via class="underline" rather than a
                # style property in this format's rich-text markup.
                cls = attrs_dict.get('class', '')
                span_underline = 'underline' in cls.split() or bool(
                    re.search(r'text-decoration:\s*underline', style)
                )
                if span_underline:
                    self.underline_depth += 1
                self.span_underline_stack.append(span_underline)

            elif tag_lower == 'strong' or tag_lower == 'b':
                self.bold_depth += 1

            elif tag_lower == 'em' or tag_lower == 'i':
                self.italic_depth += 1

            elif tag_lower == 'u':
                self.underline_depth += 1

        def handle_endtag(self, tag):
            tag_lower = tag.lower()
            if tag_lower == 'p':
                if self.current_para is not None:
                    self.paragraphs.append(self.current_para)
                    self.current_para = None
            elif tag_lower == 'span':
                # Undo style-based bold/italic/underline for this span
                if self.span_bold_stack:
                    if self.span_bold_stack.pop():
                        self.bold_depth = max(0, self.bold_depth - 1)
                if self.span_italic_stack:
                    if self.span_italic_stack.pop():
                        self.italic_depth = max(0, self.italic_depth - 1)
                if self.span_underline_stack:
                    if self.span_underline_stack.pop():
                        self.underline_depth = max(0, self.underline_depth - 1)
            elif tag_lower == 'strong' or tag_lower == 'b':
                self.bold_depth = max(0, self.bold_depth - 1)
            elif tag_lower == 'em' or tag_lower == 'i':
                self.italic_depth = max(0, self.italic_depth - 1)
            elif tag_lower == 'u':
                self.underline_depth = max(0, self.underline_depth - 1)

        def handle_data(self, data):
            if self.current_para is None:
                return
            # Decode HTML entities handled by HTMLParser automatically
            # Strip zero-width spaces and other invisible Unicode. FE0F
            # (variation selector-16, "render as emoji") and FFFC (object
            # replacement character, a leftover placeholder for some
            # embedded object with no image data left in this text field)
            # carry no glyph of their own either way.
            cleaned = data.replace('\u200b', '').replace('\u200c', '').replace('\u200d', '')
            cleaned = cleaned.replace('\ufeff', '').replace('\ufe0f', '').replace('\ufffc', '')
            if not cleaned:
                if data:
                    # The original text node had SOME content (a
                    # zero-width space, typically) that stripped down to
                    # nothing -- this is how a deliberate blank paragraph,
                    # used as vertical space between two real paragraphs,
                    # is authored. Record an empty-text run rather than
                    # dropping it outright: with no run at all the whole
                    # paragraph would look empty and get filtered out
                    # below, silently collapsing the blank line and
                    # pulling the paragraph after it up to close the gap.
                    self.current_para["runs"].append({
                        "text": "",
                        "font_size": self.current_font_size,
                        "bold": self.bold_depth > 0,
                        "italic": self.italic_depth > 0,
                        "underline": self.underline_depth > 0,
                        "color": self.current_color,
                    })
                return
            if cleaned.isspace():
                # A whitespace-only text node -- often an entire "spacer"
                # span between two differently-styled runs (e.g. an
                # underlined heading run followed by a plain-text run with
                # a separate space-only span between them). Keep it as a
                # single space so word-wrap still knows a real space
                # belongs between the runs on either side of it, rather
                # than silently losing that and running them together.
                self.current_para["runs"].append({
                    "text": " ",
                    "font_size": self.current_font_size,
                    "bold": self.bold_depth > 0,
                    "italic": self.italic_depth > 0,
                    "underline": self.underline_depth > 0,
                    "color": self.current_color,
                })
                return
            # Split off any emoji/pictographic characters into their own
            # runs, each flagged so word-wrap and drawing treat it as an
            # inline image rather than a drawable character (see
            # _needs_emoji_fallback).
            for segment, is_emoji in _split_text_and_emoji(cleaned):
                self.current_para["runs"].append({
                    "text": segment,
                    "font_size": self.current_font_size,
                    "bold": self.bold_depth > 0,
                    "italic": self.italic_depth > 0,
                    "underline": self.underline_depth > 0,
                    "color": self.current_color,
                    "emoji": is_emoji,
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

    # Wrap-style covers (e.g. imagewrap) add a turn-in/bleed flap around the
    # entire perimeter of the coversheet so artwork can wrap around the
    # board edge. That flap makes the coversheet taller than the trimmed
    # page on both top and bottom -- the same flap amount applies to the
    # left and right edges. Ignoring it (assuming front cover starts at
    # x=page_width) leaves out the flap and spine width, shifting front
    # cover content to the right of where it belongs. Softcover coversheets
    # have no such flap (coversheet_height == page_height), so this is 0
    # there and the threshold falls back to the previous behavior.
    flap = max(0.0, (coversheet_height - page_height) / 2.0)

    # Front cover occupies the rightmost page_width-wide slice of the
    # coversheet, inset by the flap; back cover occupies the leftmost
    # page_width-wide slice, also inset by the flap. Whatever remains
    # between them is the spine.
    back_x_start = flap
    front_x_threshold = coversheet_width - page_width - flap

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
        container_y = float(container.get('y', 0))
        container_width = float(container.get('width', 0))
        container_end = container_x + container_width

        # The vertical flap applies uniformly across the whole coversheet
        # width, so every container needs it subtracted from y regardless
        # of which side it lands on -- unlike x, this isn't conditional on
        # front vs. back. Skipping this (as a prior version of this
        # function did) leaves every container's y in coversheet-wide
        # coordinates instead of the trimmed cover's own, shifting
        # everything down by the flap amount -- harmless for containers
        # with lots of headroom, but enough to push one hugging the
        # bottom edge (e.g. a photo date stamp) off the trimmed page
        # entirely.
        adjusted_y = max(0.0, container_y - flap)

        # Clone container
        new_container = copy.deepcopy(container)
        new_container.set('y', str(adjusted_y))

        # Determine which cover(s) this container overlaps
        on_back = container_x < front_x_threshold
        on_front = container_end > front_x_threshold

        if on_back and on_front:
            # Container spans both covers - add to both with adjusted positions
            # Add to back cover (clip to back cover boundary)
            back_container = copy.deepcopy(container)
            back_width = front_x_threshold - container_x
            back_container.set('width', str(back_width))
            back_container.set('x', str(max(0.0, container_x - back_x_start)))
            back_container.set('y', str(adjusted_y))
            back_cover.append(back_container)

            # Add to front cover (clip to front cover boundary)
            front_container = copy.deepcopy(container)
            front_container.set('x', '0')  # Starts at left edge of front cover
            front_width = container_end - front_x_threshold
            front_container.set('width', str(front_width))
            front_container.set('y', str(adjusted_y))
            front_cover.append(front_container)
        elif container_x >= front_x_threshold:
            # Entirely on front cover - adjust x position
            adjusted_x = container_x - front_x_threshold
            new_container.set('x', str(adjusted_x))
            front_cover.append(new_container)
        else:
            # Entirely on back cover - adjust x position for the flap
            adjusted_x = max(0.0, container_x - back_x_start)
            new_container.set('x', str(adjusted_x))
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

def _hex_to_rgba(color, default=(0.0, 0.0, 0.0, 1.0)):
    """Parse a '#RRGGBB' or '#RRGGBBAA' color string into (r, g, b, a) floats in 0..1."""
    if not color or not color.startswith('#'):
        return default
    hex_digits = color[1:]
    alpha = 1.0
    if len(hex_digits) == 8:
        alpha = int(hex_digits[6:8], 16) / 255.0
        hex_digits = hex_digits[:6]
    if len(hex_digits) != 6:
        return default
    r = int(hex_digits[0:2], 16) / 255.0
    g = int(hex_digits[2:4], 16) / 255.0
    b = int(hex_digits[4:6], 16) / 255.0
    return (r, g, b, alpha)


def process_page(c, page_elem, blurb_file, page_width, page_height, page_label):
    """Process a single page and add to PDF."""
    # Set background color
    # Colors can be #RRGGBB (6 hex) or #RRGGBBAA (8 hex with alpha).
    # Alpha 00 = fully transparent, meaning "no background" — treat as white for PDF.
    color = page_elem.get('color', '#ffffff')
    if color.startswith('#'):
        r, g, b, alpha = _hex_to_rgba(color)
        if alpha == 0:
            # Fully transparent background — use white in PDF
            r, g, b = 1.0, 1.0, 1.0
        c.setFillColorRGB(r, g, b)
        c.rect(0, 0, page_width, page_height, fill=1, stroke=0)

    # Draw containers in their original document order, matching
    # Bookwright's own paint order: a later element sits on top of an
    # earlier one. Some pages genuinely rely on this -- a caption text
    # container placed after (or over) a decorative background image is
    # meant to be read on top of it, fully intact, not clipped or shrunk.
    #
    # Separately, some text/image container pairs sit a few points apart
    # by design (e.g. a heading in the gap above a photo grid) but the
    # text's actual rendered ink -- taller than its own declared box, or
    # wrapped one line further than Bookwright's own layout over a
    # font-metric difference of a fraction of a point -- ends up running
    # into the next container anyway, something Bookwright itself never
    # shows. Shrinking the text (never the other container, and never by
    # clipping) just enough that its ink clears it resolves that without
    # a visible size change. This is unrelated to document/paint order --
    # unlike an intentional on-top-of-a-background overlap (where the
    # container's own declared box already reaches the obstacle from the
    # start), an accidental one is recognizable because the box ITSELF
    # doesn't overlap; only the overflow does. So every other container on
    # the page is a candidate obstacle, regardless of whether it comes
    # before or after in document order -- process_text_container decides
    # per-obstacle whether shrinking would actually help.
    all_containers = list(page_elem.findall('.//container'))
    for idx, container in enumerate(all_containers):
        container_type = container.get('type')
        if container_type == 'image':
            process_image_container(c, container, blurb_file, page_height)
        elif container_type == 'text':
            # An image always paints its full declared container box, so
            # that box is a reliable obstacle rect. A text container's
            # declared box is often generously oversized for its actual
            # content (Bookwright doesn't size text boxes tightly, and
            # doesn't clip or shrink text that doesn't fill one -- see
            # process_text_container) -- so use ITS real rendered ink
            # extent instead, or an oversized, empty tail end of some
            # other text box would falsely register as an obstacle no
            # actual visible text ever occupies.
            obstacle_rects = []
            for other in all_containers:
                if other is container:
                    continue
                other_type = other.get('type')
                if other_type == 'image':
                    obstacle_rects.append((
                        float(other.get('x', 0)),
                        float(other.get('y', 0)),
                        float(other.get('width', 0)),
                        float(other.get('height', 0)),
                    ))
                elif other_type == 'text':
                    ox, oy, oright, obottom = _text_container_natural_ink_box(c, other)
                    obstacle_rects.append((ox, oy, oright - ox, obottom - oy))
            process_text_container(c, container, page_height, obstacle_rects)

def _rotation_angle_from_transform(transform):
    """Decode a container's 2x2 "a b c d" transform matrix into a rotation
    angle in degrees (counterclockwise, matching reportlab's c.rotate()).

    Used for both text and image containers -- either can carry a rotated
    transform (e.g. a photo tilted a few degrees for a scrapbook-style
    page, or spine text rotated 90 degrees).
    """
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
                    # The stored transform is defined in the archive's
                    # top-left-origin, y-down coordinate space. Rotating
                    # by +theta there looks like a rotation by -theta once
                    # mapped into PDF's bottom-left-origin, y-up space
                    # (flipping the y-axis flips the sense of rotation) --
                    # so the raw atan2 angle needs negating for arbitrary
                    # small-angle tilts (e.g. a scrapbook-style tilted
                    # photo) to lean the same way Bookwright shows it.
                    # The 90/180/-90 cases above are hand-verified special
                    # cases already in the correct final direction and
                    # don't go through this branch.
                    rotation_angle = -math.degrees(math.atan2(m_b, m_a))
        except (ValueError, AttributeError):
            pass
    return rotation_angle


# Bookwright's per-photo "Enhance" doesn't just brighten dark photos --
# measured directly against Blurb's own proof renders, a photo that
# already spans its full tonal range (dark rocks to bright overcast sky)
# comes back with its SKY PULLED DOWN and its GROUND/foreground PULLED UP
# *simultaneously* (sky 206.8->196.6, ground 111.8->120.3 in one measured
# example), while a photo that's dim throughout (e.g. a museum interior)
# comes back substantially brighter overall (~+25%). That's dynamic-range
# COMPRESSION toward a central tone, not a stretch or a flat brightness
# bump -- and it needs asymmetric treatment (shadows lifted more
# aggressively than highlights are pulled down) to match, since a single
# symmetric curve moving both ends toward the middle by the same amount
# undershoots how much darker photos get lifted.
#
# This LUT implements that: a piecewise gamma curve pivoting at 128,
# using a shallower gamma below the pivot (shadows/midtones lifted
# further) and a slightly less aggressive one above it (highlights pulled
# down more gently) -- unlike the shadow-only, image-adaptive gamma this
# replaced, this curve is a fixed function of input value alone, tuned
# once against 19 sample photos (matching Bookwright's measured
# brightness AND saturation shift) plus the sky/ground example above, not
# recomputed per image. Applying the same nonlinear curve independently
# to R, G, and B reduces saturation as a side effect (compressing a
# pixel's channels toward the pivot brings them closer together) --
# corrected by the saturation boost applied alongside it below.
#
# That boost was initially set to 1.8 to match Bookwright's own measured
# saturation increase against its proof PDF -- but the proof is itself a
# low-quality, heavily-compressed preview (its own words: "not optimized
# for high quality printing or digital distribution"), and 1.8 looked
# visibly over-saturated in the actual output despite fitting that
# number. The boost needed just to CANCEL the curve's own desaturation
# back to the original photo's own saturation varies per image (measured
# 1.1-1.6 across a few samples, since how hard the curve pulls a pixel
# toward the pivot depends on how far from the pivot it started) -- 1.3
# sits below that neutral range on average, a deliberately modest boost
# rather than trying to match the proof's own number.
_ENHANCE_PIVOT = 128
_ENHANCE_GAMMA_SHADOW = 0.55
_ENHANCE_GAMMA_HIGHLIGHT = 0.65
_ENHANCE_SATURATION_BOOST = 1.3


def _build_enhance_lut():
    lut = []
    p = _ENHANCE_PIVOT
    for i in range(256):
        if i <= p:
            v = p * ((i / p) ** _ENHANCE_GAMMA_SHADOW) if p > 0 else i
        else:
            u = (255 - i) / (255 - p) if p < 255 else 0
            v = 255 - (255 - p) * (u ** _ENHANCE_GAMMA_HIGHLIGHT)
        lut.append(int(max(0, min(255, v))))
    return lut * 3  # same curve on R, G, and B


_ENHANCE_LUT = _build_enhance_lut()


def _apply_enhance_curve(img):
    """Apply Bookwright-"Enhance" approximation: the pivot tone curve
    above, then a saturation boost to compensate for its desaturating
    side effect. img must already be in RGB mode (no alpha band)."""
    from PIL import ImageEnhance
    curved = img.point(_ENHANCE_LUT)
    return ImageEnhance.Color(curved).enhance(_ENHANCE_SATURATION_BOOST)


def process_image_container(c, container, blurb_file, page_height):
    """Process an image container and draw image on PDF matching .blurb positioning exactly."""
    # Get container dimensions and position
    container_x = float(container.get('x', 0))
    container_y = float(container.get('y', 0))
    container_width = float(container.get('width', 0))
    container_height = float(container.get('height', 0))

    # A container can itself be rotated a few degrees -- a common
    # scrapbook-style touch where a photo sits tilted on the page, drop
    # shadow and all, rather than perfectly axis-aligned. This is
    # completely separate from <image rotate=...> below, which rotates
    # the picture CONTENT inside an otherwise-rectangular, unrotated
    # container (e.g. fixing a sideways phone photo).
    rotation_angle = _rotation_angle_from_transform(container.get('transform', '1 0 0 1'))

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

        # Images with a real alpha channel (RGBA/LA, or P with a
        # transparency entry) must stay transparent in the PDF, not get
        # matted onto a solid color. A naive .convert('RGB') just drops
        # the alpha channel and keeps whatever RGB values sit underneath
        # the transparent pixels -- for many PNGs (e.g. clipart) that's
        # (0,0,0), which renders as solid black instead of transparent.
        # Preserve transparency by keeping the image as RGBA and saving
        # as PNG so ReportLab builds a soft mask (SMask) from the alpha
        # channel, so whatever is underneath in the PDF shows through.
        has_alpha = img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info)

        # Bookwright's "Enhance" (<image enhance="true">) -- see the
        # _ENHANCE_LUT block above for what this approximates and why.
        if image_elem.get('enhance') == 'true':
            if has_alpha:
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')
                alpha = img.getchannel('A')
                rgb = img.convert('RGB')
                enhanced_rgb = _apply_enhance_curve(rgb)
                # A die-cut/cutout PNG (an irregular shape on a
                # transparent field, common for clipart and torn-edge
                # photo treatments) can be MOSTLY transparent by pixel
                # count, with a soft, anti-aliased, partially-transparent
                # edge whose underlying RGB is dark (blending toward
                # black). The enhance curve is no longer measured from
                # the image's own statistics, but it would still happily
                # brighten that dark edge if applied to it, turning a
                # border that's invisible when blended at low opacity
                # into a visible halo around the cutout. Composite so the
                # curve only applies to meaningfully-opaque content (alpha
                # >= ~78%); a transparent or barely-visible edge pixel
                # keeps its original RGB untouched.
                opaque_mask = alpha.point(lambda a: 255 if a >= 200 else 0)
                img = PILImage.composite(enhanced_rgb, rgb, opaque_mask).convert('RGBA')
                img.putalpha(alpha)
            else:
                img = _apply_enhance_curve(img.convert('RGB'))

        img_buffer = BytesIO()
        if has_alpha:
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            img.save(img_buffer, format='PNG', optimize=False)
        else:
            if img.mode != 'RGB':
                img = img.convert('RGB')
            # Use quality=80 for balanced quality/speed (Phase 3)
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

        # Position everything relative to the container's own center, then
        # translate (and rotate, if any) into place on the page. For an
        # unrotated container this lands at exactly the same absolute
        # position as before; for a tilted one it pivots the image AND
        # its clip bounds together around the container's own center,
        # matching how Bookwright tilts a whole photo -- frame included --
        # rather than just rotating the picture inside a straight box
        # (that's what <image rotate=...> above is for instead).
        container_pdf_y = page_height - container_y - container_height
        center_x = container_x + container_width / 2
        center_y = container_pdf_y + container_height / 2
        local_left = -container_width / 2
        local_bottom = -container_height / 2
        local_abs_x = local_left + img_x
        local_abs_y = local_bottom + (container_height - img_y - scaled_height)

        c.saveState()
        c.translate(center_x, center_y)
        if rotation_angle:
            c.rotate(rotation_angle)

        # Create clipping path for container
        clip_path = c.beginPath()
        clip_path.rect(local_left, local_bottom, container_width, container_height)
        c.clipPath(clip_path, stroke=0)

        # Draw the image at the exact position specified in .blurb
        c.drawImage(image_reader, local_abs_x, local_abs_y,
                   width=scaled_width, height=scaled_height,
                   preserveAspectRatio=True, mask='auto')

        # A container can carry its own visible border/frame -- a
        # decorative rectangle (solid fill and/or stroked outline) drawn
        # over the container's own bounds, e.g. a thin black or white
        # keyline around a "polaroid-style" tilted photo. Only a minority
        # of image containers have one (most have this shape present but
        # turned off via show="false").
        border_shape = container.find('shape')
        if border_shape is not None and border_shape.get('show') == 'true':
            fill_r, fill_g, fill_b, fill_a = _hex_to_rgba(border_shape.get('fillColor', '#00000000'))
            stroke_r, stroke_g, stroke_b, stroke_a = _hex_to_rgba(border_shape.get('borderColor', '#000000'))
            border_width = float(border_shape.get('borderWidth', 0) or 0)
            do_fill = fill_a > 0
            do_stroke = border_width > 0 and stroke_a > 0
            if do_fill or do_stroke:
                border_path = c.beginPath()
                border_path.rect(local_left, local_bottom, container_width, container_height)
                if do_fill:
                    c.setFillColorRGB(fill_r, fill_g, fill_b)
                if do_stroke:
                    c.setStrokeColorRGB(stroke_r, stroke_g, stroke_b)
                    c.setLineWidth(border_width)
                c.drawPath(border_path, fill=do_fill, stroke=do_stroke)

        c.restoreState()

        # Free memory: close PIL image and BytesIO buffer
        img.close()
        img_buffer.close()
        del img, img_buffer, image_reader

    except Exception as e:
        print(f"    Warning: Could not draw image {src}: {e}")

# Inset applied on each side of a text container when word-wrapping and
# drawing. Bookwright's own text boxes carry essentially no internal
# padding -- e.g. a "piece of tile from the" line in a 117.35pt-wide box
# needs 117.35pt at its real size and still fits on one line in
# Bookwright's own proof (not wrapping "the" onto its own line the way
# any positive margin here does), and a "Day 1" heading in a 66.68pt
# box needs 64.04pt and stays on one line too. Both are consistent with
# a true margin at or extremely close to zero, not the 5pt this used to
# assume (which wrapped both of those onto an extra line).
TEXT_SIDE_MARGIN = 0

def _word_wrap_runs(c, runs, max_width):
    """Word-wrap a list of text runs into lines that fit within max_width.

    Each run has: text, font_size, bold, italic, underline, color.
    Returns a list of lines, where each line is a list of run fragments:
        [{"text": ..., "font_name": ..., "font_size": ..., "color": ...,
          "underline": ..., "width": ...}, ...]
    """
    lines = []
    current_line = []
    current_width = 0.0
    # Whether a real space belongs before the next word, carried across
    # run boundaries. A style change (e.g. an underlined word followed by
    # plain text) commonly splits one sentence across two runs with NO
    # actual space between them in the source markup -- e.g. an underlined
    # "Bousfield" run immediately followed by a ". John b.1783..." run --
    # so a space must never be assumed just because a new run started.
    # Conversely a space CAN be its own separate run (a whitespace-only
    # "spacer" span between two differently-styled runs), so it has to be
    # tracked across runs rather than decided run-by-run in isolation.
    pending_space = False

    for run in runs:
        font_name = resolve_font_name(bold=run["bold"], italic=run["italic"])
        font_size = run["font_size"]
        color = run["color"]
        underline = run.get("underline", False)
        raw_text = run["text"]

        if run.get("emoji"):
            # An emoji has no glyph to measure via stringWidth (it's
            # drawn as an inline image, not text -- see
            # _needs_emoji_fallback) and is never split into "words"; it's
            # one indivisible unit, sized to roughly match the
            # surrounding text's line height since Apple's emoji glyphs
            # come back squarish regardless of the character.
            emoji_width = font_size
            prefix = " " if current_line and pending_space else ""
            pending_space = False
            prefix_width = c.stringWidth(prefix, font_name, font_size) if prefix else 0.0
            fragment_width = prefix_width + emoji_width
            if current_width + fragment_width <= max_width or not current_line:
                current_line.append({
                    "text": prefix + raw_text,
                    "font_name": font_name,
                    "font_size": font_size,
                    "color": color,
                    "underline": False,
                    "emoji": raw_text,
                    "prefix_width": prefix_width,
                    "width": fragment_width,
                })
                current_width += fragment_width
            else:
                lines.append(current_line)
                current_line = [{
                    "text": raw_text,
                    "font_name": font_name,
                    "font_size": font_size,
                    "color": color,
                    "underline": False,
                    "emoji": raw_text,
                    "prefix_width": 0.0,
                    "width": emoji_width,
                }]
                current_width = emoji_width
            continue

        if raw_text[:1].isspace():
            pending_space = True
        words = raw_text.split()

        for i, word in enumerate(words):
            if i == 0:
                prefix = " " if current_line and pending_space else ""
            else:
                prefix = " "
            # A leading space only really belongs to a DIFFERENT run when
            # it's this run's very first word AND it exists specifically
            # because pending_space carried over from crossing a run
            # boundary (e.g. plain "...to the " followed by underlined
            # "Scar Cafe,"). A later word's leading space (i > 0) is just
            # the ordinary gap between two words already inside this same
            # run -- e.g. "Daniel Hill," -- and belongs to it like any
            # other character. Only the boundary case should ever be
            # excluded from this run's own underline.
            boundary_space = i == 0 and bool(prefix)
            pending_space = False

            test_text = prefix + word
            word_width = c.stringWidth(test_text, font_name, font_size)

            if current_width + word_width <= max_width or not current_line:
                # Word fits on current line (or line is empty, must add at least one word)
                current_line.append({
                    "text": test_text,
                    "font_name": font_name,
                    "font_size": font_size,
                    "color": color,
                    "underline": underline,
                    "boundary_space": boundary_space,
                    "emoji": None,
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
                    "underline": underline,
                    "boundary_space": False,
                    "emoji": None,
                    "width": word_width_no_prefix,
                }]
                current_width = word_width_no_prefix

        if raw_text[-1:].isspace():
            pending_space = True

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
                "underline": run.get("underline", False),
                "color": run["color"],
                "emoji": run.get("emoji", False),
            })

        # Word-wrap with margin
        wrapped_lines = _word_wrap_runs(c, scaled_runs, container_width - 2 * TEXT_SIDE_MARGIN)

        if not wrapped_lines and scaled_runs:
            # A paragraph whose only content was a zero-width space (see
            # parse_rich_text) is deliberately blank -- authored as
            # vertical space between two real paragraphs. It has a run
            # (so it survived the "no runs" filter) but no actual words,
            # so word-wrap produced no lines for it. Give it one blank
            # line at its own font size so it still takes up a line's
            # worth of height, rather than silently collapsing the gap.
            blank_font_size = max(r["font_size"] for r in scaled_runs)
            layout.append({
                "line_fragments": [],
                "alignment": para["alignment"],
                "line_height": blank_font_size * para.get("line_height_ratio", 1.08),
                "font_size": blank_font_size,
            })
            total_height += blank_font_size * para.get("line_height_ratio", 1.08)
            continue

        for line_frags in wrapped_lines:
            # Line height is driven by the tallest run actually ON this
            # line, not the tallest run anywhere in the paragraph. A
            # heading run (e.g. 16px) followed by several lines of plain
            # 12px body text should only give its OWN line the taller
            # leading -- charging every wrapped line of the paragraph for
            # it (as a single paragraph-wide max would) inflates the
            # measured height, which used to trigger the container's
            # overflow auto-shrink well before the text actually needed
            # it, and made lines wrap wider than Bookwright's own layout.
            line_font_size = max(frag["font_size"] for frag in line_frags)
            line_height = line_font_size * para.get("line_height_ratio", 1.08)
            layout.append({
                "line_fragments": line_frags,
                "alignment": para["alignment"],
                "line_height": line_height,
                "font_size": line_font_size,
            })
            total_height += line_height

    return total_height, layout


def _line_ink_horizontal_bounds(layout, x, area_width):
    """Return (left, right) spanning every line's own actual ink extent,
    honoring each line's own alignment (they need not all match -- a
    container can mix paragraphs). Left-aligned ink starts at the
    container's left edge; centered ink is centered within it; right-
    aligned ink ends at the container's right edge. Union of all lines
    since a shorter centered/right line sits inboard of a longer one.
    """
    lefts = []
    rights = []
    for item in layout:
        line_width = sum(frag["width"] for frag in item["line_fragments"])
        if item["alignment"] == "center":
            left = x + (area_width - line_width) / 2
        elif item["alignment"] == "right":
            left = x + area_width - line_width - TEXT_SIDE_MARGIN
        else:
            left = x + TEXT_SIDE_MARGIN
        lefts.append(left)
        rights.append(left + line_width)
    return min(lefts), max(rights)


def _text_container_natural_ink_box(c, container):
    """Return (left, top, right, bottom) of a text container's own natural,
    unshrunk rendered ink in top-down page coordinates.

    Used when a text container is being considered as an obstacle for
    another text container's overlap check. Its declared box is often
    taller than what it actually renders (Bookwright doesn't size text
    boxes tightly), so the declared box alone would flag overlaps with
    empty space no visible text ever reaches. Falls back to the full
    declared box for a rotated container, whose tight ink extent isn't
    reliably computable the same way (matches the restriction in
    process_text_container's own overlap check).
    """
    x = float(container.get('x', 0))
    y = float(container.get('y', 0))
    width = float(container.get('width', 0))
    height = float(container.get('height', 0))
    declared_box = (x, y, x + width, y + height)

    transform = container.get('transform', '1 0 0 1')
    if transform and transform != '1 0 0 1':
        return declared_box

    text_elem = container.find('text')
    if text_elem is None or not text_elem.text:
        return declared_box

    paragraphs = parse_rich_text(text_elem.text)
    if not paragraphs:
        return declared_box

    total_h, layout = _measure_layout(c, paragraphs, width, 1.0)
    if not layout:
        return declared_box

    ink_left, ink_right = _line_ink_horizontal_bounds(layout, x, width)
    return (ink_left, y, ink_right, y + total_h)


def process_text_container(c, container, page_height, obstacle_rects=None):
    """Process a text container and draw text on PDF with rich formatting.

    obstacle_rects: (x, y, width, height) rects of every other image OR
    text container on the page, regardless of document order.
    """
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
    rotation_angle = _rotation_angle_from_transform(transform)

    # Convert y coordinate (PDF origin is bottom-left, blurb is top-left)
    pdf_y = page_height - y - height

    # Determine effective text area for rotated containers
    if abs(rotation_angle) in (90, 270):
        text_area_width = height
        text_area_height = width
    else:
        text_area_width = width
        text_area_height = height

    # Unrotated text of any (uniform, per-line) alignment has a
    # reliable, computable ink bounding box -- left/center/right all
    # reduce to "where does this line's own ink actually sit" once each
    # line's own alignment is taken into account (see
    # _line_ink_horizontal_bounds). Only rotated containers (e.g. spine
    # text) don't map cleanly to an axis-aligned box.
    axis_aligned = rotation_angle == 0

    def overlaps_a_later_element(current_layout):
        if not obstacle_rects or not axis_aligned or not current_layout:
            return False
        ink_left, ink_right = _line_ink_horizontal_bounds(current_layout, x, width)
        ink_top = y
        ink_bottom = y + sum(item["line_height"] for item in current_layout)
        for (ix, iy, iw, ih) in obstacle_rects:
            ax0, ay0, ax1, ay1 = ix, iy, ix + iw, iy + ih
            if ink_right > ax0 and ink_left < ax1 and ink_bottom > ay0 and ink_top < ay1:
                # Shrinking only pulls the BOTTOM of top-anchored text back
                # up -- it can never move the top. So this only actually
                # resolves anything when our own top starts above the
                # obstacle's top (genuine room to shrink into before
                # reaching it). If our top already sits at or past the
                # obstacle's top edge, the two boxes were simply placed
                # adjacent by design (Bookwright's own rounding, not ours)
                # and no amount of shrinking closes that -- the loop below
                # would otherwise shrink all the way to min_scale for no
                # benefit, as this exact case did before this check.
                if ink_top < ay0:
                    return True
        return False

    def overflows_page_bottom(current_layout):
        # A top-anchored, unrotated container whose stored box runs a
        # little past the page's own bottom edge (e.g. a caption box near
        # the trim edge of a cover) is otherwise harmless -- the box's
        # empty tail end simply hangs off-page. But this renderer places
        # each line's baseline using a flat line-height offset from the
        # box's top rather than the font's real ascent, so it sits a
        # couple points lower than a proper text engine would put it.
        # For a container already hugging the edge, that's enough to push
        # actual visible ink off the page instead of just blank space.
        # Shrinking the text (same mechanism used for the later-image
        # overlap case above) keeps the ink on the page without clipping
        # or moving the container.
        if rotation_angle != 0 or not current_layout:
            return False
        ink_bottom = y + sum(item["line_height"] for item in current_layout)
        return ink_bottom > page_height + 0.5

    # Auto-scale: try scale=1.0 first, reduce only if the text's actual
    # rendered ink would intrude into a later container (and so would
    # otherwise be painted right over part of it, cutting the text), or
    # if its ink would run past the page's own bottom edge.
    #
    # Deliberately NOT a reason to shrink: the text's total height simply
    # exceeding the container's own declared height. Bookwright's own
    # proof output shows text overflowing past the bottom of its box
    # completely unshrunk and unclipped whenever nothing else sits there
    # -- the stored height is not a hard constraint the way an HTML
    # "overflow: hidden" box would be, just wherever the box happened to
    # be sized in the editor. Treating it as one here shrank text (and,
    # by fitting more words per line at the smaller size, visibly
    # rewrapped it narrower-looking-but-actually-wider than Bookwright's
    # own layout) in places nothing was actually wrong.
    #
    # Bookwright's own stored coordinates can have a text box overlap a
    # later container's -- or the page edge -- by a few points, pure
    # layout rounding rather than design intent, and Bookwright never
    # shows these as clipped either. Shrinking the text (rather than
    # clipping it or moving the other element) is enough to clear a
    # rounding-sized overlap without a visible size change.
    scale = 1.0
    min_scale = 0.5
    total_h, layout = _measure_layout(c, paragraphs, text_area_width, scale)

    while (overlaps_a_later_element(layout) or overflows_page_bottom(layout)) and scale > min_scale:
        scale -= 0.05
        total_h, layout = _measure_layout(c, paragraphs, text_area_width, scale)

    # No clipping to the container's own bounds: Bookwright doesn't clip
    # text there either (see above), it only ever needs to avoid actually
    # colliding with a later element or the page edge, which the
    # auto-scale step above already resolved. Still clip horizontally --
    # word-wrap already keeps lines within the container width, so this
    # is just a safety net, never a visible constraint in practice.
    c.saveState()
    clip_path = c.beginPath()
    clip_path.rect(x, -page_height, width, 3 * page_height)
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
                draw_x = origin_x + area_width - total_line_width - TEXT_SIDE_MARGIN
            else:
                draw_x = origin_x + TEXT_SIDE_MARGIN  # Left with small margin

            for frag in item["line_fragments"]:
                if frag.get("emoji"):
                    emoji_image = _get_emoji_image(frag["emoji"])
                    if emoji_image is not None:
                        reader, aspect = emoji_image
                        emoji_x = draw_x + frag.get("prefix_width", 0.0)
                        emoji_size = frag["font_size"]
                        # Sit the glyph a little above the baseline and a
                        # touch taller than the cap height, roughly how
                        # emoji sit relative to surrounding Latin text.
                        emoji_y = cursor_y - emoji_size * 0.15
                        if aspect >= 1:
                            w, h = emoji_size, emoji_size / aspect
                        else:
                            w, h = emoji_size * aspect, emoji_size
                        c.drawImage(reader, emoji_x, emoji_y, width=w, height=h,
                                    preserveAspectRatio=True, mask='auto')
                    draw_x += frag["width"]
                    continue
                c.setFillColorRGB(frag["color"][0], frag["color"][1], frag["color"][2])
                c.setFont(frag["font_name"], frag["font_size"])
                c.drawString(draw_x, cursor_y, frag["text"])
                if frag.get("underline"):
                    # A fragment's leading space, when it's a boundary
                    # space (see _word_wrap_runs), isn't really part of
                    # this run at all -- word-wrap injects it to satisfy
                    # the gap between two adjacent, differently-styled
                    # runs (e.g. plain "...to the " followed by an
                    # underlined "Scar Cafe,"), and the fragment inherits
                    # its OWN run's underline for that injected text.
                    # Bookwright never underlines that boundary space, so
                    # skip past it. An ordinary space between two words
                    # already inside the SAME underlined run (e.g. the gap
                    # in "Daniel Hill,") is real content of that run and
                    # keeps its underline like any other character.
                    lead_width = 0.0
                    if frag.get("boundary_space") and frag["text"][:1] == " ":
                        lead_width = c.stringWidth(" ", frag["font_name"], frag["font_size"])
                    visible_width = frag["width"] - lead_width
                    if visible_width > 0:
                        underline_y = cursor_y - frag["font_size"] * 0.08
                        c.setLineWidth(max(0.5, frag["font_size"] * 0.05))
                        c.setStrokeColorRGB(frag["color"][0], frag["color"][1], frag["color"][2])
                        c.line(draw_x + lead_width, underline_y, draw_x + frag["width"], underline_y)
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
