---
name: blurb
description: Read and write Bookwright .blurb files (SQLite archives) - also called photo albums, albums, or books
---

# Blurb File Handler Skill

This skill handles reading and writing .blurb files used by Blurb's Bookwright application.

## Terminology

**IMPORTANT**: The following terms are synonyms and refer to the same thing - a .blurb file:
- **blurb file** = **.blurb file** = **photo album** = **album** = **book**

When the user says:
- "create an album" → create a .blurb file
- "add images to the photo album" → add images to the .blurb file
- "create a book" → create a .blurb file
- "my album" → the .blurb file

All of these terms refer to the Bookwright .blurb file format, which is used to create physical photo books, printed albums, and ebooks through Blurb's services.

## File Format

.blurb files are SQLite 3 databases with the following structure:

### Tables
- **Files** - Stores archived files with columns:
  - `filepath` (TEXT, unique) - Path within the archive
  - `filecontent` (BLOB) - Binary file content
  - `filesize` (NUM) - Size in bytes (-1 if unknown)
  - `filedate` (TEXT) - Last modified date

- **ArchiveVersion** - Stores format version:
  - `version` (NUM) - Archive format version (typically 4)

### Typical Contents
- **`bbf2.xml`** - **MAIN FILE** containing all book pages, cover designs, and layout (this is the primary file to edit)
- `project_settings.json` - Project configuration (cover type, paper type, etc.)
- `media_registry.xml` - Media file references and image registry
- `project_image.jpg` - Project thumbnail/preview image
- `old_bbfs/bbf2_*.xml` - Version history/backup files (can be safely deleted)
- `images/*.png` - Image assets used in pages
- `thumbnails/*.png` - Thumbnail versions of images

**IMPORTANT**: To modify page content, edit the `bbf2.xml` file, NOT the `old_bbfs/` files.

## Book Structure in bbf2.xml

The bbf2.xml file has a specific structure that must be preserved:

```xml
<book>
  <info>
    <title><![CDATA[Book Title Here]]></title>  <!-- Book metadata title -->
    <author><![CDATA[Author Name]]></author>
    ...
  </info>
  <masterpage>
    <page number="-1" color="#ffffff"/>  <!-- Inside Back Cover -->
    <page number="-1" color="#ffffff"/>  <!-- Inside Front Cover -->
  </masterpage>
  <cover type="softcover">
    <spine>
      <container role="spineText">
        <text>...Title appears here...</text>  <!-- Spine text -->
      </container>
    </spine>
  </cover>
  <cover type="imagewrap">...</cover>
  <cover type="dustjacket">...</cover>
  <cover type="ebook">...</cover>
  <section name="">
    <page number="1">...</page>
    <page number="2">...</page>
    ...
    <page number="80">...</page>
  </section>
</book>
```

**Metadata Locations:**
- `<info><title>` - Book metadata (shown in "Book details/Project title" in Bookwright)
- `<info><author>` - Author metadata (shown in "Book details/Author Name" in Bookwright)
- `<spine>` elements in each cover type - Spine text visible on book spine (softcover, imagewrap, dustjacket)

### Protected Elements - NEVER MODIFY OR DELETE

**CRITICAL**: The following elements are essential for file validity and must NEVER be removed or altered:

1. **`<masterpage>` section** - Contains two pages (number="-1") for inside covers
   - Inside Back Cover (first page number="-1")
   - Inside Front Cover (second page number="-1")

2. **`<cover>` sections** - All cover types must remain:
   - softcover (with front, back, spine, frontflap, backflap)
   - imagewrap (with front, back, spine, frontflap, backflap)
   - dustjacket (with front, back, spine, frontflap, backflap)
   - ebook (with front, back, spine)

3. **Cover elements within each cover type:**
   - `<front>` - Front cover
   - `<back>` - Back cover
   - `<spine>` - Book spine
   - `<frontflap>` - Front flap (if applicable)
   - `<backflap>` - Back flap (if applicable)

**REFUSE** any request to delete or remove:
- Masterpage section or its pages
- Any cover section
- Front cover, back cover, inside covers, or outside covers
- Spine elements

These are structural requirements of the .blurb format. Removing them creates invalid files.

## Available Templates

Templates are located in `references/templates/` directory.

## Mandatory Input Gate (Create Operations)

Before creating any new `.blurb` file, the assistant MUST collect all required inputs:

1. Template (from `references/templates/`)
2. Book title
3. Author name

Rules:
- NEVER assume defaults for template, title, or author.
- NEVER run create/copy/modify commands for new book creation until all 3 are provided.
- If any field is missing, ask only for the missing fields and STOP.
- If the user asks to proceed without required fields, refuse and explain these are mandatory inputs.

Required prompt flow:
1. List templates dynamically from `references/templates/` if template is not provided.
2. Ask for template choice.
3. Ask for title if missing.
4. Ask for author if missing.
5. Confirm all values in one line.
6. Only then execute creation steps.

## Last-Run Option Memory (Creation Defaults)

To make repeated runs easier, persist the last confirmed create options to:

- `/tmp/blurb_last_create_options.json`

Expected schema:

```json
{
    "template": "references/templates/FamilyBook-StandardLandscape.blurb",
    "title": "My Album Title",
    "author": "Author Name",
    "saved_at": "2026-04-02T00:00:00Z"
}
```

When handling a new create request:

1. If the memory file exists, read it and offer:
     - "Use last options" (template/title/author), or
     - "Choose new options"
2. Even when memory exists, require explicit user confirmation before using saved values.
3. If the user chooses new options, run the mandatory input gate above.
4. After successful creation, overwrite the memory file with the newly confirmed values.
5. Do not silently reuse prior values without a user confirmation in the current request.

## Default Directories

Unless the user explicitly provides different paths:

- Default source images directory: `inputs/`
- Default output directory for created `.blurb` files: `outputs/`

Directory handling requirements:

- For create operations, always ensure the output directory exists before writing:
    - `mkdir -p outputs`
- For bulk image ingestion operations, use `inputs/` as the default source root when no source directory is specified.

**IMPORTANT**:
- **Always list available templates dynamically** by reading from the `references/templates/` directory
- Do NOT hard-code template names in the skill - always read from the directory
- Exception: When testing or generating sample files, skip the template listing
- When creating new .blurb files, always use one of these templates as the starting point
- **A title MUST be specified** for every new .blurb file created
- **An author MUST be specified** for every new .blurb file created
- If the user doesn't specify which template to use:
  1. List all available templates from `references/templates/`
  2. Ask them to choose from the available templates
- If the user doesn't specify a title, ask them for one
- If the user doesn't specify an author, ask them for one
- All created files should be placed in the `outputs/` directory unless the user specifies a different location
- Create the `outputs/` directory if it doesn't exist

## Anti-Patterns (Forbidden)

- Choosing a template automatically without user selection or explicit "use last options" confirmation.
- Reusing prior title/author without explicit confirmation in the current request.
- Starting batch/image processing before required creation metadata is confirmed.

**How to list available templates:**
```bash
# Find all .blurb files in references/templates directory
find references/templates -maxdepth 1 -type f -name "*.blurb" | sort
```

## Source Images Directory

The `inputs/` directory is used to store source images for creating books:

**Structure:**
- Images can be in the root of `inputs/` or in any subdirectory
- Subdirectories are searched recursively
- Supports common image formats: JPG, PNG, TIFF, HEIC (auto-converted)

**CRITICAL: Image File Handling (ALL Operations)**

These rules apply to **ALL** image addition operations (bulk, batch, test, sample, individual):

1. **Video files (.mp4, .mov, .avi, etc.)** - **ALWAYS refuse and explain**
2. **RAW files (.raw, .cr2, .nef, .arw, .dng, etc.)** - **ALWAYS refuse and explain**
3. **GIF files (.gif)** - **ALWAYS refuse and explain**
4. **HEIC files (.heic)** - **ALWAYS convert to JPG** (automatic, highest quality)

**When using inputs/ directory:**
- Search recursively through all subdirectories
- Use `find` command with `-type f` to locate all image files
- Apply all file handling rules above before adding any image

**Example: Find all images recursively**
```bash
# Find all image files (excluding videos, RAW, and GIF)
find inputs -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" -o -iname "*.heic" -o -iname "*.tiff" \) 2>/dev/null
```

**Example: Select random images**
```bash
# Get N random images from inputs directory
find inputs -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" -o -iname "*.heic" -o -iname "*.tiff" \) 2>/dev/null | sort -R | head -n 10
```

**Organization tips:**
- Organize images in subdirectories by date, event, or category
- Example structure:
  ```
  inputs/
    ├── 2024-01-15/
    │   ├── photo1.jpg
    │   └── photo2.jpg
    ├── vacation/
    │   ├── beach/
    │   │   └── sunset.jpg
    │   └── city/
    │       └── skyline.jpg
    └── family/
        └── portraits.jpg
  ```
- The recursive search will find all images regardless of subdirectory depth
- Subdirectory names and structure don't affect the random selection

## ⚠️ BEFORE MODIFYING THIS SKILL

**READ THIS FIRST** if you plan to update the image insertion code:

### Pre-Update Checklist

Before making ANY changes to the bulk image addition code (Section 5c):

1. **Read the bug history** in the "CRITICAL - DO NOT CHANGE WITHOUT TESTING" section
2. **Understand why past bugs occurred** - don't repeat the same mistakes
3. **Look for ⚠️ CRITICAL comments** in the code - these mark bug-prone areas
4. **Plan verification** - how will you test your changes work?
5. **Create a test case** - make a sample .blurb with 2-3 images to verify

### Key Points to Remember

**MUST preserve these for images to display:**
- Image `src` attribute = filename ONLY (`"GUID.jpg"` not `"images/GUID.jpg"`)
- Image `autolayout` attribute = `"fill"` (REQUIRED)
- Random selection = INSIDE the loop (for variety)
- Archive filepath = full path (`"images/GUID.jpg"`)
- XML src = filename only (`"GUID.jpg"`)

**After making changes:**
1. Test with actual .blurb file creation (2-3 images minimum)
2. Open in Bookwright and verify images display
3. Run verification commands from "Verification and Testing" section
4. Check all items in the testing checklist

**If images don't display after your changes:**
- You broke something critical - revert your changes
- Compare your code to the working version
- Check the bug history to see if you repeated a known bug

## Operations

When this skill is invoked, support the following operations based on user intent:

### CRITICAL: Handling Deletion Requests

**REFUSE and EXPLAIN** if the user requests to:
- Delete or remove the front cover, back cover, inside covers, or outside covers
- Delete or modify the `<masterpage>` section
- Delete or modify any `<cover>` sections (softcover, imagewrap, dustjacket, ebook)
- Remove spine elements

**Note:** Template pages in `<section>` are automatically deleted after bulk image insertion (5c). This is the only supported page deletion path — it removes an even number of pages and renumbers the rest.

**Response template when refusing:**
```
I cannot delete the [front/back/inside/outside] cover or [masterpage/cover sections] from the .blurb file.
These are structural requirements of the Blurb book format. Removing them would create an invalid
file that cannot be opened in Bookwright.

Instead, I can:
- Add new pages with your content to the book
- Modify the content within existing pages (keeping the page structure)
- Add or update images and text in the book's content pages

What would you like to do instead?
```

### CRITICAL: Handling HEIC Files

**AUTOMATICALLY CONVERT** if the user provides HEIC files:
- Detect .HEIC or .heic file extensions
- Convert to JPG using highest quality settings before adding to archive
- Update the file path to use .jpg extension
- Inform the user of the automatic conversion

**Conversion commands:**
- macOS: `sips -s format jpeg -s formatOptions best input.heic --out output.jpg`
- Cross-platform: `convert input.heic -quality 100 output.jpg` (requires ImageMagick)

**Response template when converting:**
```
I detected that [filename] is a HEIC file. HEIC format is not supported by Blurb books.

I've automatically converted it to JPG using highest quality settings and added it to the archive as [converted_filename].

The conversion preserves maximum image quality while ensuring compatibility with Bookwright.
```

### CRITICAL: Handling Video Files

**REFUSE AND EXPLAIN** if the user tries to add video files:
- Detect video file extensions: .mp4, .mov, .avi, .m4v, .mkv, .webm, .flv, .wmv, .mpeg, .mpg
- **NEVER add video files** to the archive
- Blurb books are for static content only (images and text)

**Common video extensions to detect:**
```bash
if [[ "$filename" =~ \.(mp4|mov|avi|m4v|mkv|webm|flv|wmv|mpeg|mpg|MP4|MOV|AVI|M4V|MKV|WEBM|FLV|WMV|MPEG|MPG)$ ]]; then
  # Refuse and explain
fi
```

**Response template when refusing:**
```
I cannot add [filename] to the .blurb file because it is a video file.

Blurb books only support static content:
- Images: JPG, PNG, TIFF (static images only)
- Text: Text containers with formatted content

Video files (.mp4, .mov, .avi, etc.) are not supported because:
- Blurb creates printed photo books (physical books cannot play videos)
- The Bookwright format only supports static images and text
- Even for ebooks, Blurb's format does not include video playback

If you want to include content from the video, I can help you:
- Extract a still frame from the video and add it as an image
- Create a QR code that links to the video online
- Add text describing the video or providing a URL

What would you like to do instead?
```

### CRITICAL: Handling RAW Image Files

**REFUSE AND EXPLAIN** if the user tries to add RAW image files:
- Detect RAW file extensions: .raw, .cr2, .nef, .arw, .dng, .orf, .rw2, .pef, .raf, .crw, .sr2, .mrw, .dcr, .x3f, .erf, .kdc, .nrw, .srf
- **NEVER add RAW files** to the archive
- RAW files must be processed/converted to standard formats first

**Common RAW extensions to detect:**
```bash
if [[ "$filename" =~ \.(raw|cr2|nef|arw|dng|orf|rw2|pef|raf|crw|sr2|mrw|dcr|x3f|erf|kdc|nrw|srf|RAW|CR2|NEF|ARW|DNG|ORF|RW2|PEF|RAF|CRW|SR2|MRW|DCR|X3F|ERF|KDC|NRW|SRF)$ ]]; then
  # Refuse and explain
fi
```

**Response template when refusing:**
```
I cannot add [filename] to the .blurb file because it is a RAW image file.

Blurb books only support processed image formats:
- Supported: JPG, PNG, TIFF
- Not supported: RAW formats (.raw, .cr2, .nef, .arw, .dng, etc.)

RAW files are not supported because:
- RAW files are unprocessed camera data, not displayable images
- Blurb's Bookwright application cannot render RAW files
- RAW files are typically very large and would bloat the book file
- RAW files need to be developed/processed first

To use this image in your book, please:
1. Open the RAW file in a photo editor (Lightroom, Photoshop, Photos, etc.)
2. Process/develop the RAW file with your desired adjustments
3. Export as JPG (recommended), PNG, or TIFF
4. Add the exported file to your Blurb book

What would you like to do instead?
```

### CRITICAL: Handling GIF Files

**REFUSE AND EXPLAIN** if the user tries to add GIF files:
- Detect .GIF or .gif file extensions
- **NEVER add GIF files** to the archive
- GIF files may contain animations and have quality/compatibility issues

**GIF extension detection:**
```bash
if [[ "$filename" =~ \.(gif|GIF)$ ]]; then
  # Refuse and explain
fi
```

**Response template when refusing:**
```
I cannot add [filename] to the .blurb file because it is a GIF file.

Blurb books only support these image formats:
- Supported: JPG, PNG, TIFF
- Not supported: GIF

GIF files are not supported because:
- GIF format may contain animations (not suitable for print)
- GIF uses limited color palette (256 colors max), resulting in poor quality for photos
- GIF is primarily designed for web graphics, not print-quality photos
- Modern formats (JPG, PNG) provide better quality and compatibility

To use this image in your book, please:
1. Open the GIF file in an image editor (Photoshop, GIMP, Preview, etc.)
2. If it's animated, choose the frame you want to use
3. Export/Save as JPG (for photos) or PNG (for graphics with transparency)
4. Add the exported file to your Blurb book

What would you like to do instead?
```

## Operations

When this skill is invoked, support the following operations based on user intent:

**Key Operations:**
- List/inspect .blurb file contents
- Extract files from archive
- Add/update individual files and images
- **Add multiple images from inputs/ directory** (bulk operation, one per page, inserts at beginning)
- **Add batch of 1-6 images** (batch operation, multiple per page, appends to end)
- Add new pages to book
- Update book title, author, and spine text
- Create new .blurb files from templates
- **Export to PDF** (delegate to the `blurb-to-pdf` skill)
- Delete files from archive
- Search for files

**Detailed Operations:**

### 1. List Contents
Show all files in a .blurb archive with their sizes and dates.

```bash
sqlite3 "path/to/file.blurb" "SELECT filepath, filesize, filedate FROM Files ORDER BY filepath;"
```

### 2. View Project Info
Extract and display project settings and metadata.

```bash
# Get version
sqlite3 "path/to/file.blurb" "SELECT version FROM ArchiveVersion;"

# Get project settings
sqlite3 "path/to/file.blurb" "SELECT filecontent FROM Files WHERE filepath='project_settings.json';"

# Count files
sqlite3 "path/to/file.blurb" "SELECT COUNT(*) FROM Files;"
```

### 3. Extract File
Extract a specific file from the archive to the filesystem.

```bash
sqlite3 "path/to/file.blurb" "SELECT filecontent FROM Files WHERE filepath='<internal/path>';" > output_file
```

### 4. Extract All Files
Extract all files maintaining directory structure.

```bash
# For each file in the archive, create directories and extract content
sqlite3 "path/to/file.blurb" "SELECT filepath FROM Files;" | while read filepath; do
  mkdir -p "output_dir/$(dirname "$filepath")"
  sqlite3 "path/to/file.blurb" "SELECT filecontent FROM Files WHERE filepath='$filepath';" > "output_dir/$filepath"
done
```

### 5. Add/Update File
Insert or replace a file in the archive.

**Image Layout Options:**

When adding images to containers, the `autolayout` attribute controls how images are scaled and positioned:

- **`autolayout='fill'`** (Default, Recommended)
  - **Fill to Frame** behavior in Bookwright
  - Scales and crops image to completely fill the container
  - Maintains aspect ratio while ensuring no empty space
  - May crop edges of image if aspect ratios don't match
  - Best for professional photo book appearance
  - **This is the default setting for all images added by the /blurb skill**

- **`autolayout='fit'`**
  - **Fit to Frame** behavior in Bookwright
  - Scales image to fit entirely within container
  - Maintains aspect ratio with possible empty space (letterboxing/pillarboxing)
  - No cropping, entire image visible
  - May result in white space around image

**Important**: As of 2026-02-19, all images are added with `autolayout='fill'` unconditionally to ensure consistent fill-to-frame behavior across all pages.

**CRITICAL: Video files are NOT supported**
- **NEVER add video files** (.mp4, .mov, .avi, .m4v, .mkv, .webm, .flv, .wmv, .mpeg, .mpg)
- Blurb books only support static images and text
- If user requests to add a video file, refuse and explain (see "Handling Video Files" section)

**CRITICAL: RAW image files are NOT supported**
- **NEVER add RAW files** (.raw, .cr2, .nef, .arw, .dng, .orf, .rw2, .pef, .raf, etc.)
- RAW files are unprocessed camera data and cannot be rendered by Bookwright
- If user requests to add a RAW file, refuse and explain (see "Handling RAW Image Files" section)
- User must process/export RAW files to JPG, PNG, or TIFF first

**CRITICAL: GIF files are NOT supported**
- **NEVER add GIF files** (.gif, .GIF)
- GIF format may contain animations and has quality/compatibility issues
- If user requests to add a GIF file, refuse and explain (see "Handling GIF Files" section)
- User must export GIF to JPG (for photos) or PNG (for graphics)

**CRITICAL: HEIC files are NOT supported**
- **NEVER add .HEIC or .heic files directly** to the archive
- If user requests to add a HEIC file, convert it to JPG first using highest quality settings
- Then add the converted JPG file

**For non-image files:**
```bash
# Prepare SQL with file content
sqlite3 "path/to/file.blurb" "INSERT OR REPLACE INTO Files (filepath, filecontent, filesize, filedate) VALUES ('path/in/archive', readfile('source/file'), <size>, datetime('now'));"
```

**For image files (with video/RAW/GIF detection, HEIC conversion, and media registry):**
```bash
# FIRST: Check if file is a video (NOT supported)
if [[ "$source_file" =~ \.(mp4|mov|avi|m4v|mkv|webm|flv|wmv|mpeg|mpg|MP4|MOV|AVI|M4V|MKV|WEBM|FLV|WMV|MPEG|MPG)$ ]]; then
  echo "ERROR: Video files are not supported in Blurb books."
  echo "File: $source_file"
  echo ""
  echo "Blurb books only support static content (images and text)."
  echo "Suggestions:"
  echo "  - Extract a still frame from the video as an image"
  echo "  - Create a QR code linking to the video online"
  echo "  - Add text with a description or URL"
  exit 1
fi

# SECOND: Check if file is a RAW image (NOT supported)
if [[ "$source_file" =~ \.(raw|cr2|nef|arw|dng|orf|rw2|pef|raf|crw|sr2|mrw|dcr|x3f|erf|kdc|nrw|srf|RAW|CR2|NEF|ARW|DNG|ORF|RW2|PEF|RAF|CRW|SR2|MRW|DCR|X3F|ERF|KDC|NRW|SRF)$ ]]; then
  echo "ERROR: RAW image files are not supported in Blurb books."
  echo "File: $source_file"
  echo ""
  echo "RAW files must be processed/exported first."
  echo "Steps:"
  echo "  1. Open the RAW file in a photo editor (Lightroom, Photoshop, Photos, etc.)"
  echo "  2. Process/develop the RAW file with your desired adjustments"
  echo "  3. Export as JPG (recommended), PNG, or TIFF"
  echo "  4. Add the exported file to your Blurb book"
  exit 1
fi

# THIRD: Check if file is a GIF (NOT supported)
if [[ "$source_file" =~ \.(gif|GIF)$ ]]; then
  echo "ERROR: GIF files are not supported in Blurb books."
  echo "File: $source_file"
  echo ""
  echo "GIF files must be converted first."
  echo "Steps:"
  echo "  1. Open the GIF file in an image editor (Photoshop, GIMP, Preview, etc.)"
  echo "  2. If animated, choose the frame you want"
  echo "  3. Export as JPG (for photos) or PNG (for graphics)"
  echo "  4. Add the exported file to your Blurb book"
  exit 1
fi

# FOURTH: Check if file is HEIC and convert
if [[ "$source_file" =~ \.(heic|HEIC)$ ]]; then
  # Convert HEIC to JPG with highest quality
  converted_file="${source_file%.*}.jpg"

  # On macOS, use sips (built-in, highest quality)
  sips -s format jpeg -s formatOptions best "$source_file" --out "$converted_file"

  # Alternative: Use ImageMagick if available (cross-platform)
  # convert "$source_file" -quality 100 "$converted_file"

  # Use the converted file
  source_file="$converted_file"
  archive_path="${archive_path%.*}.jpg"  # Update extension in archive path

  echo "Converted HEIC to JPG: $converted_file"
fi

# Get image dimensions
img_width=$(sips -g pixelWidth "$source_file" 2>/dev/null | awk '/pixelWidth:/ {print $2}')
img_height=$(sips -g pixelHeight "$source_file" 2>/dev/null | awk '/pixelHeight:/ {print $2}')

# Extract GUID from archive path (e.g., images/UUID.jpg -> UUID)
guid=$(basename "$archive_path" | sed 's/\.[^.]*$//')
ext="${archive_path##*.}"

# Add the image to the archive
filesize=$(wc -c < "$source_file")
sqlite3 "path/to/file.blurb" "INSERT OR REPLACE INTO Files (filepath, filecontent, filesize, filedate) VALUES ('$archive_path', readfile('$source_file'), $filesize, datetime('now'));"

# CRITICAL: Register image in media_registry.xml
# Images MUST be registered in media_registry.xml for Bookwright to display them
sqlite3 "path/to/file.blurb" "SELECT writefile('/tmp/media_registry.xml', filecontent) FROM Files WHERE filepath='media_registry.xml';"

# Add media entry before </images> closing tag
modified_date=$(date -u +%Y-%m-%dT%H:%M:%S)
sed -i.bak "/<\/images>/i\\
<media modified=\"$modified_date\" height=\"$img_height\" dateTaken=\"\" webImportAlbum=\"\" enhanceable=\"UNKNOWN\" validated=\"true\" guid=\"$guid\" ext=\"$ext\" width=\"$img_width\" importBatchNum=\"1\" cameraModel=\"unknown\" designerImage=\"false\" cameraMake=\"unknown\" src=\"$archive_path\" webImportSource=\"\"/>" /tmp/media_registry.xml

# Update archive with modified media_registry.xml
sqlite3 "path/to/file.blurb" "UPDATE Files SET filecontent=readfile('/tmp/media_registry.xml'), filesize=$(wc -c < /tmp/media_registry.xml), filedate=datetime('now') WHERE filepath='media_registry.xml';"

# Clean up
rm /tmp/media_registry.xml /tmp/media_registry.xml.bak 2>/dev/null
```

### 5a. Add New Page to Book
**IMPORTANT**:
- Always ADD pages to existing content
- Template pages in `<section>` are automatically cleaned up after bulk image insertion (5c) — do not manually delete them
- Only add pages within the `<section>` area - NEVER modify `<masterpage>` or `<cover>` sections
- Do NOT delete or alter cover pages (front, back, inside, outside covers)

To add a new page, insert it before the closing `</section>` tag in `bbf2.xml`.

**Process:**
```bash
# 1. Extract bbf2.xml to a temporary file
sqlite3 "path/to/file.blurb" "SELECT filecontent FROM Files WHERE filepath='bbf2.xml';" > /tmp/bbf2_temp.xml

# 2. Find the last page number
last_page=$(grep -o '<page number="[0-9]*"' /tmp/bbf2_temp.xml | tail -1 | grep -o '[0-9]*')
new_page=$((last_page + 1))

# 3. Insert new page before </section> tag using sed
sed -i.bak "/<\\/section>/i\\
<page number=\"$new_page\" color=\"#ffffff\">\\
<container type=\"text\" height=\"200\" x=\"246\" y=\"197\" width=\"200\" id=\"page-$new_page\">\\
<text valign=\"middle\" rotate=\"0\"><![CDATA[<p class=\"align-center line-height-qt\"><span class=\"font-avenir\" data-ascent=\"42.4px\" data-descent=\"15.8px\" style=\"font-size:60px;color:#000000;\">Your Text Here</span></p>]]></text>\\
</container>\\
</page>" /tmp/bbf2_temp.xml

# 4. Update the archive with modified content
sqlite3 "path/to/file.blurb" "UPDATE Files SET filecontent=readfile('/tmp/bbf2_temp.xml'), filesize=$(wc -c < /tmp/bbf2_temp.xml), filedate=datetime('now') WHERE filepath='bbf2.xml';"

# 5. Clean up
rm /tmp/bbf2_temp.xml /tmp/bbf2_temp.xml.bak
```

**XML Structure in bbf2.xml:**
- Content pages are in `<section><page number="N">` elements (numbers 1-80 in template)
- Text is in `<container type="text"><text>` with CDATA and HTML-like markup
- Images are in `<container type="image"><image src="...">` elements
- Always insert new pages BEFORE `</section>` closing tag (page 81+)
- Keep all existing template pages intact

**Protected areas (DO NOT MODIFY):**
- `<masterpage>` - Contains inside cover pages (page number="-1")
- `<cover>` sections - All cover types and their front/back/spine elements

### 5b. Update Book Title and Author
Update the title and author in an existing .blurb file. This sets:
1. Book metadata (`<info><title>` and `<info><author>`)
2. Spine text on all cover types (softcover, imagewrap, dustjacket) - title only

**Process:**
```bash
# Set the desired title and author
BOOK_TITLE="My Book Title"
BOOK_AUTHOR="Author Name"

# Extract bbf2.xml
sqlite3 "path/to/file.blurb" "SELECT filecontent FROM Files WHERE filepath='bbf2.xml';" > /tmp/bbf2_temp.xml

# Update the book title in metadata
sed -i.bak 's|<title><!\[CDATA\[.*\]\]></title>|<title><![CDATA['"$BOOK_TITLE"']]></title>|' /tmp/bbf2_temp.xml

# Update the author in metadata
sed -i.bak 's|<author><!\[CDATA\[.*\]\]></author>|<author><![CDATA['"$BOOK_AUTHOR"']]></author>|' /tmp/bbf2_temp.xml

# Update spine text on all cover types
# This replaces the placeholder (zero-width space) with the book title
sed -i.bak 's|color:#000000;">​</span>|color:#000000;">'"$BOOK_TITLE"'</span>|g' /tmp/bbf2_temp.xml

# Update the archive
sqlite3 "path/to/file.blurb" "UPDATE Files SET filecontent=readfile('/tmp/bbf2_temp.xml'), filesize=$(wc -c < /tmp/bbf2_temp.xml), filedate=datetime('now') WHERE filepath='bbf2.xml';"

# Clean up
rm /tmp/bbf2_temp.xml /tmp/bbf2_temp.xml.bak
```

### 5c. Add Multiple Images to Book (Intelligent Batching)
Add multiple images from the `inputs/` directory to a .blurb file using intelligent batching to match template pages with multiple image containers.

**NEW BEHAVIOR - Intelligent Batching:**
Instead of one image per page, this method now groups images into batches of 1-5 and finds template pages with matching numbers of containers. This creates a more varied and efficient layout.

**Process Overview:**
1. Find all images in `inputs/` directory (recursively, with captions if available)
2. Extract bbf2.xml and analyze template to find available container counts (1-6 per page)
3. **Split images into batches** based on available template page layouts
4. For each batch:
   - Find a template page with matching number of containers
   - If multiple pages match, pick one at random
   - Fill ALL containers on the page with batch images
5. Add all images to archive with unique GUIDs
6. Insert new pages at the beginning (page 1+), renumbering existing pages
7. Update archive

**IMPORTANT**:
- Groups images into batches of 1-5 based on available template layouts
- Each batch fills ONE page with multiple images
- Creates layout variety by using different template pages
- More efficient than one image per page

**Image Selection:**
```bash
# Find all images in inputs directory recursively
# Exclude videos, RAW, GIF files
find inputs -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" -o -iname "*.heic" -o -iname "*.tiff" \) | sort
```

**Find Template Page with Empty Image Containers:**
```bash
# Extract bbf2.xml
sqlite3 "path/to/file.blurb" "SELECT filecontent FROM Files WHERE filepath='bbf2.xml';" > /tmp/bbf2_temp.xml

# Find pages in <section> with empty image containers
# Look for <container type="image"> without src attribute or with placeholder images
# Exclude <masterpage> and <cover> sections

# Use Python/xmllint to parse and find:
# - Pages within <section name=""> (not <masterpage> or <cover>)
# - Containers with type="image"
# - Empty or placeholder images (no src or src="")

# Example: Get page numbers with empty image containers
python3 << 'EOF'
import xml.etree.ElementTree as ET
import random

tree = ET.parse('/tmp/bbf2_temp.xml')
root = tree.getroot()

# Find section (not masterpage or cover)
section = root.find('.//section[@name=""]')
if not section:
    print("ERROR: No section found")
    exit(1)

pages_with_empty_containers = []

for page in section.findall('page'):
    page_num = page.get('number')
    if not page_num:
        continue

    # Find empty image containers
    empty_count = 0
    for container in page.findall('.//container[@type="image"]'):
        image = container.find('image')
        if image is None or not image.get('src') or image.get('src') == '':
            empty_count += 1

    if empty_count > 0:
        pages_with_empty_containers.append((page_num, empty_count))

if not pages_with_empty_containers:
    print("ERROR: No pages with empty image containers found")
    exit(1)

# Pick one at random
selected = random.choice(pages_with_empty_containers)
print(f"{selected[0]}|{selected[1]}")  # page_number|empty_container_count
EOF
```

**Complete Implementation with Intelligent Batching:**

```python
#!/usr/bin/env python3
"""
Add multiple images from inputs/ directory using intelligent batching.
Groups images into batches of 1-5 based on available template page layouts.
"""

import os
import sys
import xml.etree.ElementTree as ET
import subprocess
import random
import copy
import uuid
from collections import defaultdict
from datetime import datetime

def find_images_in_inputs():
    """Find all images in inputs directory recursively."""
    result = subprocess.run([
        'find', 'inputs', '-type', 'f',
        '(', '-iname', '*.jpg', '-o', '-iname', '*.jpeg', '-o', '-iname', '*.png',
        '-o', '-iname', '*.heic', '-o', '-iname', '*.tiff', ')'
    ], capture_output=True, text=True)

    images = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
    return sorted(images)

def analyze_template_pages(blurb_file):
    """Analyze template to find available container counts per page."""
    print("Analyzing template pages...")

    # Extract bbf2.xml
    subprocess.run(['sqlite3', blurb_file,
                   "SELECT filecontent FROM Files WHERE filepath='bbf2.xml';"],
                  stdout=open('/tmp/bbf2_analyze.xml', 'wb'))

    tree = ET.parse('/tmp/bbf2_analyze.xml')
    root = tree.getroot()

    section = root.find('.//section[@name=""]')
    if section is None:
        print("ERROR: No section found")
        return {}

    # Group pages by container count
    pages_by_count = defaultdict(list)

    for page in section.findall('page'):
        page_num = page.get('number')
        if not page_num:
            continue

        containers = page.findall('.//container[@type="image"]')
        count = len(containers)

        if 1 <= count <= 6:
            pages_by_count[count].append(page)

    print(f"Template analysis:")
    for count in sorted(pages_by_count.keys()):
        print(f"  {count} containers: {len(pages_by_count[count])} pages available")

    return dict(pages_by_count)

def create_batches(images, available_counts):
    """Intelligently split images into batches based on available template pages."""
    if not available_counts:
        print("ERROR: No template pages with 1-6 image containers found")
        return []

    batches = []
    remaining = list(images)

    # Available batch sizes sorted by preference (larger first for efficiency)
    batch_sizes = sorted(available_counts.keys(), reverse=True)

    while remaining:
        # Try to use the largest available batch size
        for size in batch_sizes:
            if len(remaining) >= size:
                batches.append(remaining[:size])
                remaining = remaining[size:]
                break
        else:
            # If no perfect fit, use the smallest available size
            size = min(batch_sizes)
            batches.append(remaining[:size])
            remaining = remaining[size:]

    print(f"\nCreated {len(batches)} batches from {len(images)} images:")
    batch_summary = defaultdict(int)
    for batch in batches:
        batch_summary[len(batch)] += 1
    for size in sorted(batch_summary.keys()):
        print(f"  {batch_summary[size]} batches of {size} images")

    return batches

def bulk_add_with_batching(blurb_file):
    """Add all images from inputs/ using intelligent batching."""

    # Step 1: Find all images
    print("Step 1: Finding images in inputs directory...")
    images = find_images_in_inputs()

    if not images:
        print("ERROR: No images found in inputs directory")
        return False

    print(f"Found {len(images)} images\n")

    # Step 2: Analyze template
    pages_by_count = analyze_template_pages(blurb_file)

    if not pages_by_count:
        print("ERROR: No suitable template pages found")
        return False

    # Step 3: Create intelligent batches
    batches = create_batches(images, pages_by_count)

    # Step 4: Process each batch
    print("\nStep 4: Processing batches and adding to archive...")
    all_batch_data = []

    for batch_num, batch_images in enumerate(batches, 1):
        batch_size = len(batch_images)
        print(f"\nBatch {batch_num}/{len(batches)}: {batch_size} images")

        # Process images in this batch
        batch_image_data = []
        for img_file in batch_images:
            # Add image to archive and collect metadata
            img_data = process_image(blurb_file, img_file)
            if img_data:
                batch_image_data.append(img_data)
                print(f"  ✓ {os.path.basename(img_file)}")

        if batch_image_data:
            all_batch_data.append((batch_size, batch_image_data))

    # Step 5: Update media_registry.xml
    print("\nStep 5: Updating media_registry.xml...")
    update_media_registry(blurb_file, all_batch_data)

    # Step 6: Create pages for each batch
    print("\nStep 6: Creating pages with intelligent layouts...")
    create_pages_for_batches(blurb_file, all_batch_data, pages_by_count)

    total_images = sum(len(batch_data) for _, batch_data in all_batch_data)
    print(f"\n✅ Successfully added {total_images} images in {len(batches)} pages")
    return True

def process_image(blurb_file, image_file):
    """Process a single image: add to archive, get dimensions and caption."""
    # Skip unsupported formats
    if image_file.lower().endswith(('.mp4', '.mov', '.avi', '.gif', '.raw', '.cr2', '.nef')):
        return None

    guid = str(uuid.uuid4()).upper()
    ext = os.path.splitext(image_file)[1][1:]
    archive_path = f"images/{guid}.{ext}"

    # Get dimensions
    result = subprocess.run(['sips', '-g', 'pixelWidth', '-g', 'pixelHeight', image_file],
                          capture_output=True, text=True)
    width = height = 0
    for line in result.stdout.split('\n'):
        if 'pixelWidth:' in line:
            width = int(line.split(':')[1].strip())
        elif 'pixelHeight:' in line:
            height = int(line.split(':')[1].strip())

    # Add to archive
    filesize = os.path.getsize(image_file)
    subprocess.run(['sqlite3', blurb_file,
                   f"INSERT OR REPLACE INTO Files (filepath, filecontent, filesize, filedate) VALUES ('{archive_path}', readfile('{image_file}'), {filesize}, datetime('now'));"])

    # Get caption
    result = subprocess.run(['exiftool', '-XMP:Description', '-s3', image_file],
                          capture_output=True, text=True)
    caption = result.stdout.strip()

    return {
        'guid': guid,
        'ext': ext,
        'width': width,
        'height': height,
        'path': archive_path,
        'caption': caption,
        'basename': os.path.basename(image_file)
    }

def update_media_registry(blurb_file, all_batch_data):
    """Update media_registry.xml with all images."""
    # Extract existing media_registry.xml
    subprocess.run(['sqlite3', blurb_file,
                   "SELECT writefile('/tmp/media_registry.xml', filecontent) FROM Files WHERE filepath='media_registry.xml';"])

    # Try to parse existing file, rebuild if corrupted
    try:
        tree = ET.parse('/tmp/media_registry.xml')
        root = tree.getroot()
        images_elem = root.find('.//images')
    except ET.ParseError:
        print("  Warning: media_registry.xml corrupted, rebuilding...")
        # Create new clean structure
        root = ET.Element('medialist')
        images_elem = ET.SubElement(root, 'images')
        ET.SubElement(root, 'videos')
        ET.SubElement(root, 'audio')
        ET.SubElement(root, 'text')
        tree = ET.ElementTree(root)

    if images_elem is None:
        images_elem = ET.SubElement(root, 'images')

    # Add all new images
    for _, batch_data in all_batch_data:
        for img in batch_data:
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

    tree.write('/tmp/media_registry.xml', encoding='utf-8', xml_declaration=True)
    filesize = os.path.getsize('/tmp/media_registry.xml')
    subprocess.run(['sqlite3', blurb_file,
                   f"UPDATE Files SET filecontent=readfile('/tmp/media_registry.xml'), filesize={filesize}, filedate=datetime('now') WHERE filepath='media_registry.xml';"])

def create_pages_for_batches(blurb_file, all_batch_data, pages_by_count):
    """Create pages for each batch using matching template pages."""
    # Extract bbf2.xml
    subprocess.run(['sqlite3', blurb_file,
                   "SELECT filecontent FROM Files WHERE filepath='bbf2.xml';"],
                  stdout=open('/tmp/bbf2_work.xml', 'wb'))

    tree = ET.parse('/tmp/bbf2_work.xml')
    root = tree.getroot()

    section = root.find('.//section[@name=""]')
    if section is None:
        print("ERROR: No section found")
        return

    new_pages = []
    page_num = 1

    for batch_size, batch_data in all_batch_data:
        # Pick random template page with matching container count
        if batch_size not in pages_by_count:
            print(f"  WARNING: No template for batch size {batch_size}, skipping")
            continue

        template_page = random.choice(pages_by_count[batch_size])
        new_page = copy.deepcopy(template_page)
        new_page.set('number', str(page_num))

        # Fill ALL containers on the page
        containers = new_page.findall('.//container[@type="image"]')
        for container, img in zip(containers, batch_data):
            # ⚠️ CRITICAL: Extract ONLY filename from path
            filename = img['path'].split('/')[-1]

            image_elem = container.find('image')
            if image_elem is not None:
                # ⚠️ CRITICAL: Use filename ONLY, not full path (Bug #1)
                image_elem.set('src', filename)
                # ⚠️ CRITICAL: Always set autolayout="fill" for fill-to-frame behavior (Bug #2)
                image_elem.set('autolayout', 'fill')
            else:
                # Create new image element
                image_elem = ET.SubElement(container, 'image')
                image_elem.set('src', filename)
                image_elem.set('rotate', '0')
                image_elem.set('flip', 'none')
                image_elem.set('x', '0')
                image_elem.set('y', '0')
                image_elem.set('scale', '1.0')
                # ⚠️ CRITICAL: Always set autolayout="fill" for fill-to-frame behavior (Bug #2)
                image_elem.set('autolayout', 'fill')

        # Add captions
        text_containers = new_page.findall('.//container[@type="text"]')
        for container, img in zip(text_containers, batch_data):
            if img['caption']:
                text_elem = container.find('text')
                if text_elem is not None:
                    text_elem.clear()
                    text_elem.text = f'<![CDATA[<p class="align-center line-height-qt"><span class="font-avenir" style="font-size:20px;color:#000000;">{img["caption"]}</span></p>]]>'

        new_pages.append(new_page)
        print(f"  Page {page_num}: {batch_size} images (template with {batch_size} containers)")
        page_num += 1

    # Renumber existing pages
    for page in section.findall('page'):
        old_num = page.get('number')
        if old_num and old_num.isdigit():
            page.set('number', str(int(old_num) + len(new_pages)))

    # Insert new pages at beginning
    for new_page in reversed(new_pages):
        section.insert(0, new_page)

    # Delete original template pages (only from <section>, not covers/masterpages)
    # Only delete even numbers of pages to maintain spread alignment
    all_section_pages = section.findall('page')
    old_template_pages = all_section_pages[len(new_pages):]
    delete_count = len(old_template_pages)
    if delete_count % 2 != 0:
        delete_count -= 1

    if delete_count > 0:
        print(f"Removing {delete_count} original template pages...")
        for page in old_template_pages[:delete_count]:
            section.remove(page)
        kept = len(old_template_pages) - delete_count
        if kept > 0:
            print(f"  Kept {kept} template page(s) to maintain even page count")

    # Renumber all remaining pages sequentially
    for idx, page in enumerate(section.findall('page'), start=1):
        page.set('number', str(idx))

    # Save
    tree.write('/tmp/bbf2_updated.xml', encoding='utf-8', xml_declaration=True)
    filesize = os.path.getsize('/tmp/bbf2_updated.xml')
    subprocess.run(['sqlite3', blurb_file,
                   f"UPDATE Files SET filecontent=readfile('/tmp/bbf2_updated.xml'), filesize={filesize}, filedate=datetime('now') WHERE filepath='bbf2.xml';"])

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 bulk_add.py <blurb_file>")
        sys.exit(1)

    blurb_file = sys.argv[1]
    success = bulk_add_with_batching(blurb_file)
    sys.exit(0 if success else 1)
```

**Key Implementation Details:**

1. **Intelligent Batching Algorithm**:
   - Analyzes template to find available container counts (1-6 per page)
   - Groups images into batches that match available template layouts
   - Prefers larger batches for efficiency
   - Example: If template has pages with 1, 2, 4 containers, it will create batches of 4, 2, and 1

2. **Template Page Matching**:
   - For each batch, finds template pages with EXACTLY matching container count
   - If multiple pages match, picks one at random for variety
   - Fills ALL containers on the page (not just first)

3. **Image Container Filling**:
   - Extracts just the filename from the archive path (e.g., "images/GUID.jpg" → "GUID.jpg")
   - Sets `<image src="filename">` attribute with ONLY the filename (not the full path)
   - Sets `autolayout="fill"` to ensure image scales properly in container
   - If no `<image>` element exists, creates one with all required attributes

4. **Caption Placement**:
   - Extracts `XMP:Description` from image metadata
   - Places in adjacent `<container type="text">` elements as formatted HTML

5. **Page Insertion and Template Cleanup**:
   - Inserts new pages at position 0 in `<section>`
   - Renumbers all existing pages (shifts by number of new pages)
   - **Deletes original template pages** after insertion (only from `<section>`, never covers/masterpages)
   - Only deletes an even number of template pages to maintain spread alignment
   - If odd number of template pages, keeps 1 to stay even
   - Renumbers all remaining pages sequentially (1, 2, 3, ...)

6. **Benefits Over Old Method**:
   - ✅ More efficient: Creates fewer pages by grouping images
   - ✅ Better layouts: Uses template pages with multiple containers
   - ✅ More variety: Different batch sizes create visual interest
   - ✅ Smarter: Adapts to whatever template layouts are available
import xml.etree.ElementTree as ET
import random
import sys

try:
    tree = ET.parse('/tmp/bbf2_work.xml')
    root = tree.getroot()

    # Find section (not masterpage or cover)
    section = root.find('.//section[@name=""]')
    if not section:
        print("ERROR: No section found", file=sys.stderr)
        sys.exit(1)

    pages_with_empty = []

    for page in section.findall('page'):
        page_num = page.get('number')
        if not page_num:
            continue

        # Find image containers (empty or with placeholders)
        containers = []
        for container in page.findall('.//container[@type="image"]'):
            containers.append(container)

        if len(containers) > 0:
            pages_with_empty.append((page_num, len(containers)))

    if not pages_with_empty:
        print("ERROR: No pages with image containers found", file=sys.stderr)
        sys.exit(1)

    # Pick one at random
    selected = random.choice(pages_with_empty)
    print(f"{selected[0]}|{selected[1]}")

except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
PYEOF
)

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to find template page"
    cat /tmp/bbf2_work.xml
    exit 1
fi

template_page=$(echo "$template_info" | cut -d'|' -f1)
containers_per_page=$(echo "$template_info" | cut -d'|' -f2)

echo "Using template page: $template_page (with $containers_per_page image containers)"

# Step 4: Calculate pages needed
total_images=${#image_files[@]}
pages_needed=$(( (total_images + containers_per_page - 1) / containers_per_page ))
echo "Need $pages_needed pages for $total_images images"

# Step 5: Add all images to archive
echo "Step 4: Adding images to archive..."
declare -a image_guids
declare -a image_captions

for image_file in "${image_files[@]}"; do
    # Skip videos, RAW, GIF (safety check)
    if [[ "$image_file" =~ \.(mp4|mov|avi|m4v|mkv|webm|flv|wmv|mpeg|mpg|gif|GIF)$ ]]; then
        echo "Skipping unsupported file: $image_file"
        continue
    fi

    if [[ "$image_file" =~ \.(raw|cr2|nef|arw|dng|orf|rw2|pef|raf|crw|sr2|mrw|dcr|x3f|erf|kdc|nrw|srf)$ ]]; then
        echo "Skipping RAW file: $image_file"
        continue
    fi

    # Convert HEIC if needed
    source_file="$image_file"
    if [[ "$image_file" =~ \.(heic|HEIC)$ ]]; then
        echo "Converting HEIC: $(basename "$image_file")"
        temp_jpg="/tmp/$(uuidgen).jpg"
        sips -s format jpeg -s formatOptions best "$image_file" --out "$temp_jpg" 2>/dev/null
        source_file="$temp_jpg"
    fi

    # Generate GUID
    guid=$(uuidgen)
    ext="${source_file##*.}"
    archive_path="images/${guid}.${ext}"

    # Get dimensions
    img_width=$(sips -g pixelWidth "$source_file" 2>/dev/null | awk '/pixelWidth:/ {print $2}')
    img_height=$(sips -g pixelHeight "$source_file" 2>/dev/null | awk '/pixelHeight:/ {print $2}')

    # Add to archive
    filesize=$(wc -c < "$source_file")
    sqlite3 "$BLURB_FILE" "INSERT OR REPLACE INTO Files (filepath, filecontent, filesize, filedate) VALUES ('$archive_path', readfile('$source_file'), $filesize, datetime('now'));"

    # Get caption from image metadata
    caption=$(exiftool -XMP:Description -s3 "$image_file" 2>/dev/null)

    # Store GUID and caption
    image_guids+=("$guid|$ext|$img_width|$img_height|$archive_path")
    image_captions+=("$caption")

    # Clean up temp file
    if [[ "$source_file" == /tmp/* ]]; then
        rm "$source_file"
    fi

    echo "  Added: $(basename "$image_file") -> $guid"
done

# Step 6: Update media_registry.xml
echo "Step 5: Updating media_registry.xml..."
sqlite3 "$BLURB_FILE" "SELECT writefile('/tmp/media_registry.xml', filecontent) FROM Files WHERE filepath='media_registry.xml';"

for image_info in "${image_guids[@]}"; do
    IFS='|' read -r guid ext width height src <<< "$image_info"
    modified_date=$(date -u +%Y-%m-%dT%H:%M:%S)

    sed -i.bak "/<\/images>/i\\
<media modified=\"$modified_date\" height=\"$height\" dateTaken=\"\" webImportAlbum=\"\" enhanceable=\"UNKNOWN\" validated=\"true\" guid=\"$guid\" ext=\"$ext\" width=\"$width\" importBatchNum=\"1\" cameraModel=\"unknown\" designerImage=\"false\" cameraMake=\"unknown\" src=\"$src\" webImportSource=\"\"/>" /tmp/media_registry.xml
done

sqlite3 "$BLURB_FILE" "UPDATE Files SET filecontent=readfile('/tmp/media_registry.xml'), filesize=$(wc -c < /tmp/media_registry.xml), filedate=datetime('now') WHERE filepath='media_registry.xml';"
rm /tmp/media_registry.xml /tmp/media_registry.xml.bak 2>/dev/null

# Step 7: Clone template pages and fill with images
echo "Step 6: Creating pages with images..."
python3 << 'PYFILL'
import xml.etree.ElementTree as ET
import sys
import copy
import random

# Load XML
tree = ET.parse('/tmp/bbf2_work.xml')
root = tree.getroot()

# Load image data from files
with open('/tmp/image_guids.txt', 'r') as f:
    image_guids = [line.strip().split('|') for line in f]

with open('/tmp/image_captions.txt', 'r') as f:
    captions = [line.strip() for line in f]

# Find section
section = root.find('.//section[@name=""]')
if section is None:
    print("ERROR: No section found", file=sys.stderr)
    sys.exit(1)

# Find all pages with image containers (potential templates)
template_pages = []
for page in section.findall('page'):
    page_num = page.get('number')
    if not page_num:
        continue

    # Find image containers
    image_containers = page.findall('.//container[@type="image"]')
    if len(image_containers) > 0:
        template_pages.append(page)

if not template_pages:
    print("ERROR: No pages with image containers found", file=sys.stderr)
    sys.exit(1)

print(f"Found {len(template_pages)} template pages to choose from")

# Create new pages - pick random template for EACH page
new_pages = []
for idx, (guid_data, caption) in enumerate(zip(image_guids, captions)):
    guid, ext, width, height, path = guid_data
    page_num = idx + 1

    # ⚠️ CRITICAL: Pick random INSIDE loop for variety (Bug #3 - was outside loop)
    template_page = random.choice(template_pages)

    # Clone template page
    new_page = copy.deepcopy(template_page)
    new_page.set('number', str(page_num))

    # Find and fill image containers with the new image
    filled = False
    for container in new_page.findall('.//container[@type="image"]'):
        if filled:
            break  # Only fill first image container

        # ⚠️ CRITICAL: Extract ONLY filename from path (Bug #1 - was using full path)
        # Bookwright expects src="GUID.jpg" NOT src="images/GUID.jpg"
        filename = path.split('/')[-1]

        image_elem = container.find('image')
        if image_elem is not None:
            # ⚠️ CRITICAL: Use filename ONLY, not full path (Bug #1)
            image_elem.set('src', filename)
            # ⚠️ CRITICAL: Always set autolayout="fill" for fill-to-frame behavior (Bug #2)
            image_elem.set('autolayout', 'fill')
            filled = True
        else:
            # No image element exists, create one with all required attributes
            image_elem = ET.SubElement(container, 'image')
            # ⚠️ CRITICAL: Use filename ONLY, not full path (Bug #1)
            image_elem.set('src', filename)
            image_elem.set('rotate', '0')
            image_elem.set('flip', 'none')
            image_elem.set('x', '0')
            image_elem.set('y', '0')
            image_elem.set('scale', '1.0')
            # ⚠️ CRITICAL: autolayout="fill" is REQUIRED for display (Bug #2)
            image_elem.set('autolayout', 'fill')
            filled = True

    # Find text containers and add caption if we have one
    if caption:
        for container in new_page.findall('.//container[@type="text"]'):
            text_elem = container.find('text')
            if text_elem is not None:
                # Replace text content with caption
                # Clear existing content
                text_elem.clear()
                text_elem.text = f'<![CDATA[<p class="align-center line-height-qt"><span class="font-avenir" style="font-size:20px;color:#000000;">{caption}</span></p>]]>'
                break  # Only fill first text container

    new_pages.append(new_page)
    if (idx + 1) % 10 == 0:
        print(f"  Created page {idx + 1}/{len(image_guids)}")

print(f"Created {len(new_pages)} new pages with random templates")

# Renumber existing pages (shift by number of new pages)
print("Renumbering existing pages...")
for page in section.findall('page'):
    page_num = page.get('number')
    if page_num and page_num.isdigit():
        old_num = int(page_num)
        new_num = old_num + len(new_pages)
        page.set('number', str(new_num))

# Insert new pages at the beginning
print("Inserting new pages at beginning...")
for idx, new_page in enumerate(reversed(new_pages)):
    section.insert(0, new_page)

# Delete original template pages (only from <section>, not covers/masterpages)
# Only delete even numbers of pages to maintain spread alignment
all_section_pages = section.findall('page')
old_template_pages = all_section_pages[len(new_pages):]
delete_count = len(old_template_pages)
if delete_count % 2 != 0:
    delete_count -= 1

if delete_count > 0:
    print(f"Removing {delete_count} original template pages...")
    for page in old_template_pages[:delete_count]:
        section.remove(page)
    kept = len(old_template_pages) - delete_count
    if kept > 0:
        print(f"  Kept {kept} template page(s) to maintain even page count")

# Renumber all remaining pages sequentially
for idx, page in enumerate(section.findall('page'), start=1):
    page.set('number', str(idx))

print(f"Pages 1-{len(new_pages)}: New images with random layouts")
remaining_template = len(section.findall('page')) - len(new_pages)
if remaining_template > 0:
    print(f"Pages {len(new_pages)+1}+: {remaining_template} remaining template page(s)")

# Write back
tree.write('/tmp/bbf2_updated.xml', encoding='utf-8', xml_declaration=True)
print("Successfully created pages with images and captions")
PYFILL

# Step 8: Update archive with modified bbf2.xml
echo "Step 7: Updating archive..."
sqlite3 "$BLURB_FILE" "UPDATE Files SET filecontent=readfile('/tmp/bbf2_updated.xml'), filesize=$(wc -c < /tmp/bbf2_updated.xml), filedate=datetime('now') WHERE filepath='bbf2.xml';"

# Clean up
rm /tmp/bbf2_work.xml /tmp/bbf2_updated.xml 2>/dev/null

echo ""
echo "Successfully added ${#image_guids[@]} images across $pages_needed pages"
```

**Key Implementation Details:**

1. **Random Template Selection**: For EACH new page, uses Python's `random.choice()` to pick from pages with image containers - creates variety in layouts
2. **Image Container Filling**:
   - Finds first `<container type="image">` in the cloned page
   - Extracts just the filename from the archive path (e.g., "images/GUID.jpg" → "GUID.jpg")
   - Sets `<image src="filename">` attribute with ONLY the filename (not the full path)
   - Sets `autolayout="fill"` to ensure image scales properly in container
   - If no `<image>` element exists, creates one with all required attributes (rotate, flip, x, y, scale, autolayout)
3. **Caption Placement**:
   - Extracts `XMP:Description` from image metadata
   - Places in first `<container type="text">` element as formatted HTML
4. **Page Insertion**:
   - Inserts new pages at position 0 in `<section>`
   - Renumbers all existing pages (shifts by number of new pages)
5. **GUID Management**: Generates unique GUIDs for each image using `uuidgen`

**CRITICAL - DO NOT CHANGE WITHOUT TESTING:**

This section documents bugs that have occurred multiple times when updating the image insertion code. **READ THIS BEFORE MAKING ANY CHANGES:**

**Bug History:**

1. **Bug: Images not displaying in Bookwright** (Fixed 2026-02-19)
   - **Symptom**: Pages created but images not visible in Bookwright application
   - **Cause**: Image `src` attribute set to full path `"images/GUID.jpg"` instead of just filename `"GUID.jpg"`
   - **Fix**: Extract filename from path: `filename = path.split('/')[-1]`
   - **Why**: Bookwright expects `src="GUID.jpg"` not `src="images/GUID.jpg"`

2. **Bug: Images not filling containers - aspect ratio scaling** (Fixed 2026-02-19)
   - **Symptom**: Images not filling containers properly, especially when aspect ratios don't match
   - **Root Cause**: Missing or incorrect `scale`, `x`, and `y` attributes for fill behavior
   - **Key Insight**: `autolayout='fill'` alone is NOT sufficient - requires calculated scale/position values
   - **Fix**: Calculate proper scale and position for fill behavior:
     ```python
     # Calculate scale to fill container (larger of the two ratios)
     scale_x = container_width / img_width
     scale_y = container_height / img_height
     fill_scale = max(scale_x, scale_y)  # Ensures image covers entire container

     # Calculate centering offsets
     scaled_img_width = img_width * fill_scale
     scaled_img_height = img_height * fill_scale
     x_offset = (container_width - scaled_img_width) / 2
     y_offset = (container_height - scaled_img_height) / 2

     # Set all required attributes
     image_elem.set('rotate', '0')
     image_elem.set('flip', 'none')
     image_elem.set('x', str(x_offset))
     image_elem.set('y', str(y_offset))
     image_elem.set('scale', str(fill_scale))
     image_elem.set('src', filename)
     image_elem.set('autolayout', 'fill')
     ```
   - **Why**: Bookwright requires rotate, flip, x, y, scale, src, AND autolayout='fill' for proper fill behavior
   - **Important**: Using `scale='1'` or `x='0', y='0'` without calculation causes images to not fill properly
   - **Autolayout Options**:
     - `'fill'` - Fill to frame (with calculated scale/position, crops to fit while maintaining aspect ratio)
     - `'fit'` - Fit to frame (with calculated scale/position, may show empty space)

3. **Bug: Same template repeated for all pages** (Fixed earlier)
   - **Symptom**: All 59 pages used identical layout instead of variety
   - **Cause**: Random template selected ONCE before loop, not per iteration
   - **Fix**: Move `template_page = random.choice(template_pages)` INSIDE the for loop
   - **Why**: Each page needs its own random selection for variety

**Required for images to display:**
- ✅ Image `src` uses ONLY filename: `"GUID.jpg"` NOT `"images/GUID.jpg"`
- ✅ Image element MUST have `autolayout="fill"` attribute
- ✅ Image element should have these attributes: rotate, flip, x, y, scale, autolayout
- ✅ Random template picked for EACH page (inside loop, not outside)
- ✅ Archive path uses full path `"images/GUID.jpg"` for file storage
- ✅ XML src uses just filename `"GUID.jpg"` for display

**Testing checklist before committing changes:**
1. Create a test .blurb file with 2-3 images
2. Verify images appear in Bookwright (not just XML)
3. Check `src` attribute in XML is filename only (not path)
4. Check `autolayout="fill"` exists on all image elements
5. Verify random templates are used (not repeated)

**Important Notes:**
- Always backup the .blurb file before running this operation
- Test on a copy first
- The random template selection provides visual variety across pages
- NEVER change the image insertion code without testing in Bookwright

### 5d. Add Batch of Images to Book (1-6 images per page) - DEFAULT FOR SMALL BATCHES

Add a small batch of 1-6 images to an existing .blurb file by finding a template page with the matching number of image placeholders.

**THIS IS THE DEFAULT METHOD when user specifies 1-6 images.**

**Use Case:** Adding images in small batches (1-6 at a time) where multiple images should appear on the same page together.

**When to Use This Method:**
- User says "add 5 images" or "add 3 random images" → Use 5d
- User says "add ALL images from inputs" → Use 5c

**Differences from 5c (Bulk Addition):**
- **5c (Bulk)**: Adds ALL images from inputs/, one image per page, inserts at beginning, for 10+ images
- **5d (Batch - DEFAULT FOR 1-6)**: Adds 1-6 specific images, multiple images per page, appends to end

**Process Overview:**
1. User specifies 1-6 images to add
2. Count the number of images in the batch (N)
3. Search template pages for pages with exactly N image containers
4. If multiple pages match, pick one at random
5. Copy the selected page to the END of the book
6. Fill ALL N image containers on the page with the batch images
7. Add captions if available
8. Update archive

**IMPORTANT:**
- Match the number of images to the number of containers on the page
- Fill ALL containers on the page (not just the first)
- Append to END of book (not beginning)

**Implementation:**

```python
#!/usr/bin/env python3
"""
Add a batch of 1-6 images to an existing .blurb file.
Usage: python3 add_batch.py <blurb_file> <image1> [image2] [image3] ...
"""

import sys
import xml.etree.ElementTree as ET
import subprocess
import random
import copy
import os
import uuid

def add_batch_to_blurb(blurb_file, image_files):
    """Add a batch of 1-6 images to a .blurb file on a matching template page."""

    if not (1 <= len(image_files) <= 6):
        print(f"ERROR: Batch must contain 1-6 images, got {len(image_files)}")
        return False

    batch_size = len(image_files)
    print(f"Adding batch of {batch_size} images to {blurb_file}")

    # Step 1: Add images to archive
    print("\nStep 1: Adding images to archive...")
    image_data = []

    for image_file in image_files:
        guid = str(uuid.uuid4()).upper()
        ext = os.path.splitext(image_file)[1][1:]
        archive_path = f"images/{guid}.{ext}"

        # Get dimensions
        result = subprocess.run(['sips', '-g', 'pixelWidth', '-g', 'pixelHeight', image_file],
                              capture_output=True, text=True)
        width = height = 0
        for line in result.stdout.strip().split('\n'):
            if 'pixelWidth:' in line:
                width = int(line.split(':')[1].strip())
            elif 'pixelHeight:' in line:
                height = int(line.split(':')[1].strip())

        # Add to archive
        filesize = os.path.getsize(image_file)
        subprocess.run(['sqlite3', blurb_file,
                       f"INSERT OR REPLACE INTO Files (filepath, filecontent, filesize, filedate) VALUES ('{archive_path}', readfile('{image_file}'), {filesize}, datetime('now'));"])

        # Get caption
        result = subprocess.run(['exiftool', '-XMP:Description', '-s3', image_file],
                              capture_output=True, text=True)
        caption = result.stdout.strip()

        image_data.append({
            'guid': guid,
            'ext': ext,
            'width': width,
            'height': height,
            'path': archive_path,
            'caption': caption,
            'basename': os.path.basename(image_file)
        })

        print(f"  ✓ {os.path.basename(image_file)} -> {guid}")

    # Step 2: Update media_registry.xml
    print("\nStep 2: Updating media_registry.xml...")
    subprocess.run(['sqlite3', blurb_file,
                   "SELECT writefile('/tmp/media_registry.xml', filecontent) FROM Files WHERE filepath='media_registry.xml';"])

    from datetime import datetime
    for img in image_data:
        modified_date = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        subprocess.run(['sed', '-i', '', '-e',
                       f'/<\\/images>/i\\\n<media modified="{modified_date}" height="{img["height"]}" dateTaken="" webImportAlbum="" enhanceable="UNKNOWN" validated="true" guid="{img["guid"]}" ext="{img["ext"]}" width="{img["width"]}" importBatchNum="1" cameraModel="unknown" designerImage="false" cameraMake="unknown" src="{img["path"]}" webImportSource=""/>',
                       '/tmp/media_registry.xml'])

    filesize = os.path.getsize('/tmp/media_registry.xml')
    subprocess.run(['sqlite3', blurb_file,
                   f"UPDATE Files SET filecontent=readfile('/tmp/media_registry.xml'), filesize={filesize}, filedate=datetime('now') WHERE filepath='media_registry.xml';"])
    print("  ✓ Media registry updated")

    # Step 3: Find template page with matching number of containers
    print(f"\nStep 3: Finding template page with {batch_size} image containers...")
    subprocess.run(['sqlite3', blurb_file,
                   "SELECT filecontent FROM Files WHERE filepath='bbf2.xml';"],
                  stdout=open('/tmp/bbf2_work.xml', 'wb'))

    tree = ET.parse('/tmp/bbf2_work.xml')
    root = tree.getroot()

    section = root.find('.//section[@name=""]')
    if section is None:
        print("ERROR: No section found")
        return False

    # Find all pages with exactly batch_size image containers
    matching_pages = []
    for page in section.findall('page'):
        page_num = page.get('number')
        if not page_num:
            continue

        image_containers = page.findall('.//container[@type="image"]')
        if len(image_containers) == batch_size:
            matching_pages.append(page)

    if not matching_pages:
        print(f"ERROR: No template pages found with exactly {batch_size} image containers")
        print(f"Available container counts in template:")
        container_counts = {}
        for page in section.findall('page'):
            count = len(page.findall('.//container[@type="image"]'))
            if count > 0:
                container_counts[count] = container_counts.get(count, 0) + 1
        for count, num_pages in sorted(container_counts.items()):
            print(f"  {count} containers: {num_pages} pages")
        return False

    # Pick random page from matches
    template_page = random.choice(matching_pages)
    print(f"  ✓ Found {len(matching_pages)} matching pages")
    print(f"  ✓ Selected template page {template_page.get('number')} (has {batch_size} containers)")

    # Step 4: Clone page and fill with images
    print("\nStep 4: Creating new page with images...")
    new_page = copy.deepcopy(template_page)

    # Find the highest existing page number
    max_page_num = 0
    for page in section.findall('page'):
        page_num = page.get('number')
        if page_num and page_num.isdigit():
            max_page_num = max(max_page_num, int(page_num))

    new_page_num = max_page_num + 1
    new_page.set('number', str(new_page_num))

    # ⚠️ CRITICAL: Fill ALL image containers on the page (not just first)
    image_containers = new_page.findall('.//container[@type="image"]')
    for idx, (container, img) in enumerate(zip(image_containers, image_data)):
        # ⚠️ CRITICAL: Extract ONLY filename from path (Bug #1 - was using full path)
        filename = img['path'].split('/')[-1]

        image_elem = container.find('image')
        if image_elem is not None:
            # ⚠️ CRITICAL: Use filename ONLY, not full path (Bug #1)
            image_elem.set('src', filename)
            # ⚠️ CRITICAL: Always set autolayout="fill" for fill-to-frame behavior (Bug #2)
            image_elem.set('autolayout', 'fill')
        else:
            # Create new image element with all required attributes
            image_elem = ET.SubElement(container, 'image')
            # ⚠️ CRITICAL: Use filename ONLY, not full path (Bug #1)
            image_elem.set('src', filename)
            image_elem.set('rotate', '0')
            image_elem.set('flip', 'none')
            image_elem.set('x', '0')
            image_elem.set('y', '0')
            image_elem.set('scale', '1.0')
            # ⚠️ CRITICAL: autolayout="fill" is REQUIRED for display (Bug #2)
            image_elem.set('autolayout', 'fill')

        print(f"  ✓ Container {idx+1}: {img['basename']}")

    # Add captions to adjacent text containers if available
    text_containers = new_page.findall('.//container[@type="text"]')
    for idx, (text_container, img) in enumerate(zip(text_containers, image_data)):
        if img['caption']:
            text_elem = text_container.find('text')
            if text_elem is not None:
                text_elem.clear()
                text_elem.text = f'<![CDATA[<p class="align-center line-height-qt"><span class="font-avenir" style="font-size:20px;color:#000000;">{img["caption"]}</span></p>]]>'
                print(f"  ✓ Added caption: {img['caption'][:50]}...")

    # Step 5: Append page to end of book
    print(f"\nStep 5: Appending page {new_page_num} to end of book...")
    section.append(new_page)

    # Write updated XML
    tree.write('/tmp/bbf2_updated.xml', encoding='utf-8', xml_declaration=True)

    # Update archive
    filesize = os.path.getsize('/tmp/bbf2_updated.xml')
    subprocess.run(['sqlite3', blurb_file,
                   f"UPDATE Files SET filecontent=readfile('/tmp/bbf2_updated.xml'), filesize={filesize}, filedate=datetime('now') WHERE filepath='bbf2.xml';"])

    print(f"\n✅ Successfully added {batch_size} images on page {new_page_num}")
    return True


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python3 add_batch.py <blurb_file> <image1> [image2] [image3] ...")
        sys.exit(1)

    blurb_file = sys.argv[1]
    image_files = sys.argv[2:]

    if not os.path.exists(blurb_file):
        print(f"ERROR: Blurb file not found: {blurb_file}")
        sys.exit(1)

    for img in image_files:
        if not os.path.exists(img):
            print(f"ERROR: Image file not found: {img}")
            sys.exit(1)

    success = add_batch_to_blurb(blurb_file, image_files)
    sys.exit(0 if success else 1)
```

**Key Implementation Details:**

1. **Container Matching**: Searches for template pages with EXACTLY the same number of image containers as images in the batch
2. **Random Selection**: If multiple pages have the correct number of containers, picks one at random
3. **Fill All Containers**: Fills ALL image containers on the page (not just the first)
4. **Append to End**: Adds the new page at the end of the book (after highest page number)
5. **Proper Image Attributes**: Uses filename-only for `src`, includes `autolayout="fill"`

**Usage Examples:**

```bash
# Add single image
python3 add_batch.py "outputs/My Album.blurb" "photo1.jpg"

# Add 2 images (will find page with 2 image containers)
python3 add_batch.py "outputs/My Album.blurb" "photo1.jpg" "photo2.jpg"

# Add 3 images (will find page with 3 image containers)
python3 add_batch.py "outputs/My Album.blurb" "photo1.jpg" "photo2.jpg" "photo3.jpg"

# Add 6 images (will find page with 6 image containers)
python3 add_batch.py "outputs/My Album.blurb" "img1.jpg" "img2.jpg" "img3.jpg" "img4.jpg" "img5.jpg" "img6.jpg"
```

**When to Use 5c vs 5d:**

**IMPORTANT DECISION RULE:**
- **1-6 images specified → Use 5d (Batch Addition) - THIS IS THE DEFAULT**
- **"All images" or 10+ images → Use 5c (Bulk Addition)**

**Use 5d (Batch Addition) - DEFAULT FOR SMALL BATCHES** when:
- User specifies 1-6 specific images (e.g., "add 5 images", "add 3 random images")
- Want multiple images on the same page together
- Want pages appended to the end
- Want to match template layouts with specific container counts
- Building a book incrementally over time
- **Examples:** "add 5 random images", "add photo1.jpg photo2.jpg photo3.jpg"

**Use 5c (Bulk Addition)** when:
- User says "add ALL images from inputs" or doesn't specify a small count
- Adding many images (10+) from a directory
- Want one image per page (each image on separate page)
- Want pages inserted at the beginning
- Want random variety in page layouts
- **Examples:** "add all images from inputs", "populate the book with images"

**Error Handling:**

If no template pages have the matching number of containers:
```
ERROR: No template pages found with exactly 3 image containers
Available container counts in template:
  1 containers: 24 pages
  2 containers: 18 pages
  4 containers: 12 pages
  6 containers: 6 pages
```

This tells you what batch sizes are supported by your template.

**Testing Checklist:**

Before using this operation:
1. Verify template has pages with the batch size you need
2. Test with a copy of the .blurb file first
3. Open in Bookwright and verify images display correctly
4. Check that page is appended to end (not inserted)
5. Check that ALL containers are filled (not just first)

### 5e. Orientation-Aware Batch Addition (RECOMMENDED for /image-batcher integration)

When adding batches of images using the `/image-batcher` skill, the script automatically matches portrait and landscape images to appropriate template pages and containers.

**Key Features:**
- **Automatic orientation detection**: Determines if each image is portrait (height > width) or landscape (width >= height)
- **Smart template matching**: Analyzes template pages to find containers with portrait or landscape orientations
- **Best-fit scoring**: Selects template pages that best match the batch's portrait/landscape mix
- **Intelligent placement**: Places portrait images in portrait containers and landscape images in landscape containers

**How It Works:**

1. **Image Analysis**: When processing each image, the script:
   ```python
   orientation = 'portrait' if height > width else 'landscape'
   ```

2. **Template Analysis**: For each template page with N containers, the script analyzes container dimensions:
   ```python
   for container in containers:
       width = float(container.get('width', 0))
       height = float(container.get('height', 0))
       if height > width:
           orientation = 'portrait'
       else:
           orientation = 'landscape'
   ```

3. **Scoring Algorithm**: Calculates match score between batch and template:
   ```python
   def calculate_orientation_score(batch_images, container_orientations):
       batch_portrait = sum(1 for img in batch_images if img['orientation'] == 'portrait')
       batch_landscape = len(batch_images) - batch_portrait

       template_portrait = sum(1 for o in container_orientations if o == 'portrait')
       template_landscape = len(container_orientations) - template_portrait

       portrait_diff = abs(batch_portrait - template_portrait)
       landscape_diff = abs(batch_landscape - template_landscape)
       total_diff = portrait_diff + landscape_diff

       score = 100 - (total_diff * 10)  # 100 = perfect match
       return max(0, score)
   ```

4. **Template Selection**: Chooses template page with highest score:
   - Score 100 = Perfect match (e.g., 2 portrait images → 2 portrait containers)
   - Score 90 = 1 orientation mismatch
   - Score 80 = 2 orientation mismatches
   - Lower scores for larger mismatches

5. **Image Placement**: Places images in containers matching their orientation:
   ```python
   portrait_images = [img for img in batch if img['orientation'] == 'portrait']
   landscape_images = [img for img in batch if img['orientation'] == 'landscape']

   for container, container_orient in zip(containers, orientations):
       if container_orient == 'portrait' and portrait_images:
           img = portrait_images.pop(0)
       elif container_orient == 'landscape' and landscape_images:
           img = landscape_images.pop(0)
       # ... place image in container
   ```

**Example Output:**

When processing batches, you'll see orientation match information:
```
Batch 1/20: 2026-01-03 (4 images)
  ✓ image1.jpg
  ✓ image2.jpg
  ✓ image3.jpg
  ✓ image4.jpg
  📐 Batch: 0P/4L → Template: 0P/4L (score: 100)
  → Created page 1 with 4 images

Batch 8/20: 2026-01-18 (2 images)
  ✓ portrait1.jpg
  ✓ portrait2.jpg
  📐 Batch: 2P/0L → Template: 2P/0L (score: 100)
  → Created page 8 with 2 images
```

**Perfect Match Examples:**
- 4 landscape images → Template with 4 landscape containers (score: 100)
- 2 portrait images → Template with 2 portrait containers (score: 100)
- 1 portrait + 2 landscape → Template with 1P/2L containers (score: 100)

**Partial Match Examples:**
- 5 landscape images → Template with 1P/4L containers (score: 80)
  - Best available match when no 5L template exists
  - Portrait container will hold a landscape image (with appropriate cropping)

**Integration with /image-batcher:**

The updated `/tmp/add_batches_to_blurb.py` script includes orientation-aware features by default. When using the `/image-batcher` workflow:

1. Initialize batcher: `python3 .claude/skills/image-batcher/batcher.py init inputs/`
2. Create album from template
3. Run: `python3 /tmp/add_batches_to_blurb.py "outputs/My Album.blurb"`
4. Script automatically:
   - Detects image orientations
   - Finds best matching templates
   - Places images in appropriate containers
   - Reports match scores

**Benefits:**
- **Better visual composition**: Portrait photos in vertical spaces, landscapes in horizontal spaces
- **Reduced cropping**: Images fit better in appropriately-oriented containers
- **Professional layouts**: Matches how professional photo books are designed
- **Automatic optimization**: No manual template selection needed

**Script Location:**
The orientation-aware script is maintained at `/tmp/add_batches_to_blurb.py` and integrates seamlessly with the image-batcher workflow.

### 6. Create New Archive
Create a new .blurb file based on a template from `references/templates/`.

**REQUIRED: Title and Author must be specified**
Every new .blurb file MUST have a title and author. If not provided by the user, ask for them.

**Default template:** `references/templates/2020 empty photo album.blurb`
- This is the preferred template — use it automatically unless the user specifies a different one.
- It has 186 pages, 494 image containers (1-9 per page), and the widest variety of layouts.

**If user explicitly asks to choose a template**, list available templates and ask:
1. First, list all available templates from the directory:
```bash
# Find all .blurb files in references/templates
find references/templates -maxdepth 1 -type f -name "*.blurb" -exec basename {} \; | sort
```
2. Present the list to the user
3. Use the AskUserQuestion tool to prompt for template selection with the dynamically discovered options

**If title not specified, ask the user:**
Ask for the book title - this will be used in:
- Book metadata (Book details/Project title)
- Spine text on all cover types

**If author not specified, ask the user:**
Ask for the book author - this will be used in:
- Book metadata (Book details/Author Name)

**Then create from template:**
```bash
# Ensure outputs directory exists
mkdir -p outputs

# Copy the chosen template to outputs directory (unless user specified a different path)
cp "references/templates/2020 empty photo album.blurb" "outputs/new_file.blurb"

# Extract bbf2.xml to modify title, author, and spine text
sqlite3 "outputs/new_file.blurb" "SELECT filecontent FROM Files WHERE filepath='bbf2.xml';" > /tmp/bbf2_temp.xml

# Set the book title in metadata
sed -i.bak 's|<title><!\[CDATA\[.*\]\]></title>|<title><![CDATA['"$BOOK_TITLE"']]></title>|' /tmp/bbf2_temp.xml

# Set the author in metadata
sed -i.bak 's|<author><!\[CDATA\[.*\]\]></author>|<author><![CDATA['"$BOOK_AUTHOR"']]></author>|' /tmp/bbf2_temp.xml

# Set spine text on all cover types (softcover, imagewrap, dustjacket)
# Replace the placeholder (zero-width space) with the book title
sed -i.bak 's|color:#000000;">​</span>|color:#000000;">'"$BOOK_TITLE"'</span>|g' /tmp/bbf2_temp.xml

# Update the archive with modified bbf2.xml
sqlite3 "outputs/new_file.blurb" "UPDATE Files SET filecontent=readfile('/tmp/bbf2_temp.xml'), filesize=$(wc -c < /tmp/bbf2_temp.xml), filedate=datetime('now') WHERE filepath='bbf2.xml';"

# Clean up
rm /tmp/bbf2_temp.xml /tmp/bbf2_temp.xml.bak
```

**IMPORTANT**:
- Keep ALL template content intact initially (pages, images, settings)
- Add new pages using the methods in sections 5a-5e
- Template pages in `<section>` are automatically cleaned up after bulk image insertion (5c) — this deletes an even number of original template pages and renumbers the rest
- Do NOT manually delete template pages outside of the automated cleanup
- Never delete `<masterpage>` or `<cover>` sections — these are structural requirements

**Default output location**: `outputs/` directory (create if it doesn't exist)
**Never create from scratch** - always use a template to ensure proper structure and compatibility.

### 7. Delete File
Remove a file from the archive.

**WARNING**: Do NOT delete:
- `bbf2.xml` - Main content file (NEVER delete, only modify)
- `project_settings.json` - Required configuration
- `media_registry.xml` - Required registry file

You can safely delete:
- Individual images in `images/` or `thumbnails/`
- Backup files in `old_bbfs/` (though keeping them is recommended)

```bash
sqlite3 "path/to/file.blurb" "DELETE FROM Files WHERE filepath='<internal/path>';"
```

**Deleting Pages from bbf2.xml:**

**Exception — Template page cleanup after image insertion:**
After inserting new image pages via bulk addition (5c), original template pages in `<section>` are automatically deleted. This is safe because:
- Only `<section>` content pages are removed (never `<masterpage>` or `<cover>`)
- Only an even number of pages are deleted (to maintain spread alignment)
- Pages are renumbered sequentially after deletion

**For all other cases**, do not delete pages by removing them from bbf2.xml. If you must remove content:
- Keep the `<page>` structure intact
- Remove only the `<container>` elements inside the page
- **NEVER remove**: `<masterpage>` pages, `<cover>` sections, or their sub-elements

### 8. Search Files
Find files matching a pattern.

```bash
sqlite3 "path/to/file.blurb" "SELECT filepath, filesize FROM Files WHERE filepath LIKE '%pattern%';"
```

### 9. Export to PDF
Delegate PDF conversion to the separate `blurb-to-pdf` skill.

**⚠️ IMPORTANT: Conversion Time**
- PDF conversion can take **several minutes** for large albums
- Albums with 50+ pages may take 5-15 minutes depending on image count and sizes
- Images requiring rotation or flipping take longer to process (uses PIL for image transformations)
- The script shows progress indicators and time estimates
- Do not interrupt the process - wait for completion

**⚠️ CRITICAL: No Parallel PDF Generation**
- When converting multiple .blurb files to PDF, ALWAYS run conversions **one at a time, sequentially**
- NEVER launch multiple `blurb_to_pdf.py` processes simultaneously (no parallel Bash calls, no background processes)
- Wait for each PDF conversion to fully complete before starting the next one
- PDF conversion is CPU-intensive and memory-intensive — running multiple conversions in parallel causes resource contention, slower overall completion, and potential failures
- Use a sequential loop or chain conversions with `&&` if converting multiple files

**Requirements:**
- Python 3 with reportlab library
- Install with: `pip3 install --user --break-system-packages reportlab`

**Process:**
```bash
# Convert .blurb file to PDF
python3 .claude/skills/blurb-to-pdf/blurb_to_pdf.py "path/to/file.blurb"

# Output will be created at: path/to/file.pdf (same directory and name)
```

**What's Included:**
- **Front Cover**: First page of PDF (from first cover type found: softcover, imagewrap, or dustjacket)
  - Supports both separate `<front>` element format and `<coversheet>` format
  - For coversheet format: automatically splits coversheet into front and back covers
  - **Includes all images and text on the front cover**
  - Text that spans from spine onto front cover is included (clipped to cover boundary)
- **Content Pages**: All pages from the section (pages 1-N)
- **Back Cover**: Last page of PDF (from same cover type as front)
  - Supports both separate `<back>` element format and `<coversheet>` format
  - **Includes all images and text on the back cover**
  - Text that spans from spine onto back cover is included (clipped to cover boundary)
- **Images**: Embedded from archive at correct positions and sizes
  - **EXIF orientation applied automatically** (fixes camera rotation metadata)
  - Preserves aspect ratios with fill-to-frame behavior
  - Respects rotation, flip, scale, and position attributes from .blurb file
  - Uses clipping paths to crop images to container boundaries
- **Text**: All text containers with content, colors, font sizes, and rotation preserved
  - **Text rotation support**: Automatically detects and applies rotation transforms from .blurb file
    - 90° counterclockwise rotation (spine text reading upward)
    - 90° clockwise rotation (spine text reading downward)
    - 180° rotation and arbitrary angles supported
  - **Spine text included on covers**: Text containers marked as "spineText" that extend onto front or back covers are included
  - Text containers spanning multiple covers are automatically split and clipped to each cover's boundary
  - Maintains exact positioning, orientation, and styling from .blurb file
- **Background Colors**: Each page uses the exact background color from the .blurb file
- **Page Size**: Matches the original .blurb page dimensions
- **Metadata**: PDF title and author from book info

**NOT Included:**
- **Inside Covers**: Inside cover pages from masterpage section are skipped (not included in PDF)
- **Pure Spine Elements**: Text/images that are entirely on the spine (not extending onto covers) are not included

**Features:**
- Automatically extracts images from the SQLite archive
- Preserves page layouts and positioning
- Handles both image and text containers
- Creates PDF with same filename as .blurb file
- Overwrites existing PDF files without prompting
- **Shows progress with page counts and time estimates**
- **Displays elapsed time on completion**

**Example Output:**
```bash
# Convert photo album to PDF
python3 .claude/skills/blurb-to-pdf/blurb_to_pdf.py "outputs/My Photo Album.blurb"

# Output:
# Converting: My Photo Album.blurb
# Output: My Photo Album.pdf
#
# Extracting book structure...
# Title: My Photo Album
# Author: Jane Doe
#
# Page size: 8.00" × 8.00"
# Aspect ratio: 1.000:1
#
# Total pages to process: 102
# ⚠️  Large album detected: PDF conversion may take several minutes
#    Estimated time: 204 - 408 seconds
#
# [1/102] Processing front cover (softcover)...
#
# Processing 100 content pages...
# [2/102] Page 1
# [3/102] Page 2
# ...
# [10/102] Page 8 (9% complete, ~380s remaining)
# [20/102] Page 18 (19% complete, ~340s remaining)
# ...
# [101/102] Page 100
#
# [102/102] Processing back cover (softcover)...
# [102/102] Saving PDF...
#
# ✅ Created PDF with 102 pages
#    Output: outputs/My Photo Album.pdf
#    Time elapsed: 6m 42s
```

**Progress Indicators:**
- Shows `[current/total]` page count for all pages
- For albums with 50+ pages: shows progress percentage and estimated time remaining every 10 pages
- For smaller albums: shows progress for every page
- Displays total elapsed time on completion

**Image Handling:**
- **EXIF orientation**: Automatically reads and applies EXIF orientation metadata (matches Bookwright behavior)
- **Exact positioning**: Uses the exact x, y, scale values from the .blurb file
- **Rotation support**: Applies the `rotate` attribute (0, 90, 180, 270 degrees)
- **Flip support**: Applies the `flip` attribute (none, horizontal, vertical, both)
- **Cropping**: Images are cropped to container boundaries exactly as in Bookwright
- **Aspect ratio preservation**: All images maintain their original aspect ratio
- **Full quality**: Images embedded at original resolution
- **Matches Bookwright**: PDF output matches the exact appearance in Bookwright application

**Notes:**
- PDF page size matches the .blurb page dimensions
- Images preserve orientation and aspect ratio (no stretching or distortion)
- Background colors match the .blurb file exactly for each page
- Text colors and font sizes are extracted from HTML styles and preserved
- Text rendering is simplified (no full HTML/CSS support, basic formatting only)
- Only processes first cover type found (softcover, imagewrap, or dustjacket)
- **Cover format support**:
  - Handles both separate `<front>`/`<back>` element format (used in templates)
  - Handles `<coversheet>` format (single wide element split into front/back)
  - Automatically detects and processes the appropriate format
- Spine is not included (not applicable to PDF format)
- Inside covers from masterpage are NOT included in PDF (front and back covers only)

### PDF Conversion Technical Details

This section documents the internal mechanisms, optimizations, and edge case handling in the PDF conversion process.

#### Performance Optimizations

The PDF converter implements three phases of optimization to reduce conversion time:

**Phase 1: Conditional EXIF Processing**
- Only applies EXIF orientation transformations if the orientation tag exists and is not 1 (normal)
- Skips unnecessary image transformations when images are already correctly oriented
- **Performance impact**: ~14% faster (1m 45s → 1m 30s)

**Phase 2: Batch Image Extraction**
- Pre-extracts all unique images from the SQLite archive in a single pass before processing pages
- Caches extracted images in `/tmp/blurb_img_*.jpg` files
- Avoids repeated SQLite queries for the same image across multiple pages
- Implementation:
  ```python
  # Extract all unique image paths upfront
  preextract_all_images(blurb_file, unique_image_paths)

  # Later: Check cache first before querying database
  if image_path in _image_temp_cache:
      temp_path = _image_temp_cache[image_path]
  ```
- **Performance impact**: ~26% faster vs baseline (1m 45s → 1m 18s)

**Phase 3: JPEG Quality Optimization**
- Reduces JPEG quality from 95 to 80 (still high quality for print)
- Uses `optimize=False` to skip expensive optimization passes
- Trades minor quality loss for significant speed improvement
- **Performance impact**: ~44% faster vs baseline (1m 45s → 59s)
- **File size impact**: ~53% smaller PDFs (332 MB → 155 MB)

**Combined Performance**: All three phases together provide 44% speedup while maintaining acceptable quality.

**Memory Optimizations**:
- PIL images and BytesIO buffers are explicitly closed after each image is drawn to free pixel data
- Garbage collection is forced every 10 pages to reclaim lingering objects
- Temp image files are kept on disk during conversion (for reuse across pages) and cleaned up in a single pass at the end

**Conversion Time Examples**:
- 122 pages (2026 Photo Album): 1m 39s
- 148 pages (2000-2002 Photos): 56s
- 188 pages (2006-2007 Photos): 47s
- 296 pages (2003-2005 Photos): 1m 14s
- 304 pages (2007-2008 Photos): 1m 18s
- 442 pages (2008-2009 Photos): 2m 6s

#### Text Rendering

The PDF converter implements sophisticated text rendering to ensure text fits properly in containers without overflow or cropping.

**Auto-Sizing Algorithm**:
1. Word-wraps text at the current font size
2. Checks if all wrapped lines fit in the container height
3. If not, reduces font size by 1pt and tries again
4. Continues until text fits or reaches minimum size (6pt or 50% of original)
5. Truncates remaining lines if still doesn't fit at minimum size

**Line Height Calculation**:
- Uses `font_size × 1.3` instead of `font_size + 2`
- The 1.3x multiplier provides proper typographic spacing
- Ensures enough room for line-to-line readability

**Descender Spacing**:
- Reserves `font_size × 0.3` of extra space at the bottom of text containers
- Prevents clipping of descenders (the "swoopy bits" on letters like g, y, p, q, j)
- Descender space is accounted for when:
  - Calculating if lines fit: `total_height = len(lines) × line_height + descender_space`
  - Truncating lines: `max_lines = int((height - descender_space) / line_height)`

**Implementation Details**:
```python
# Calculate line height with proper spacing
line_height = actual_font_size * 1.3

# Reserve space for descenders on last line
descender_space = actual_font_size * 0.3

# Check if text fits (including descender space)
total_height = len(lines) * line_height + descender_space
if total_height <= height:
    break  # Text fits!

# Truncate if needed (accounting for descenders)
max_lines = int((height - descender_space) / line_height)
```

**Text Clipping**:
- All text containers use ReportLab clipping paths to prevent overflow
- Clipping is applied with `c.clipPath()` before drawing text
- Graphics state is saved/restored to isolate clipping effects

**Rotated Text Handling**:
- Supports 90° counterclockwise (spine text reading upward)
- Supports 90° clockwise (spine text reading downward)
- Supports 180° rotation and arbitrary angles
- Rotation uses translation + rotation transforms to position correctly

#### Image Rendering

**Autolayout Modes**:

The .blurb format supports two image autolayout modes:

1. **`autolayout='fill'`** (Fill to Frame):
   - Scales image to completely fill the container
   - Maintains aspect ratio while ensuring no empty space
   - May crop edges if aspect ratios don't match
   - Calculation:
     ```python
     scale_x = container_width / img_width
     scale_y = container_height / img_height
     img_scale = max(scale_x, scale_y)  # Use larger scale

     # Center the image
     scaled_width = img_width * img_scale
     scaled_height = img_height * img_scale
     img_x = (container_width - scaled_width) / 2
     img_y = (container_height - scaled_height) / 2
     ```

2. **`autolayout='fit'`** or explicit scale:
   - Uses explicit scale, x, y values from .blurb file
   - Image is positioned and scaled exactly as specified
   - May result in empty space (letterboxing/pillarboxing)

**EXIF Orientation**:
- Conditionally applied only if orientation tag exists and is not 1 (normal)
- Uses PIL's `ImageOps.exif_transpose()` for automatic correction
- Handles all 8 EXIF orientation values (rotate + flip combinations)

**Image Extraction**:
- Phase 2 optimization pre-extracts all images to `/tmp/blurb_img_*.jpg`
- Cache prevents repeated SQLite queries for duplicate images
- Temporary files are reused across page processing

#### Fallback Mechanisms

The PDF converter includes several fallback mechanisms to handle variations in .blurb file formats:

**Cover Detection Fallback**:

Different .blurb files use different cover formats. The converter tries multiple approaches:

1. **Standard types first**: Look for covers with `type="softcover"`, `type="imagewrap"`, or `type="dustjacket"`
2. **Fallback to any cover**: If no standard types found, check for ANY `<cover>` element
3. **Format variations**:
   - Separate `<front>` and `<back>` elements (used in templates)
   - Single `<coversheet>` element (automatically split into front/back)
   - Covers with `type="None"` (non-standard but encountered in older files)

```python
# First: Try standard cover types
for cover_type in ['softcover', 'imagewrap', 'dustjacket']:
    cover = root.find(f'.//cover[@type="{cover_type}"]')
    if cover is not None:
        front_cover = cover.find('front')
        back_cover = cover.find('back')
        if front_cover is not None or back_cover is not None:
            break

# Fallback: Accept any cover element
if front_cover is None and back_cover is None:
    covers = root.findall('.//cover')
    for cover in covers:
        # Try coversheet format
        coversheet = cover.find('coversheet')
        if coversheet is not None:
            front_cover, back_cover = split_coversheet(coversheet, width, height)
            break
        # Try front/back format
        front = cover.find('front')
        back = cover.find('back')
        if front is not None or back is not None:
            front_cover = front
            back_cover = back
            break
```

**Section Detection Fallback**:

Different .blurb files have different section attributes:

1. **Standard format**: Section with `name=""` (empty string)
2. **Fallback format**: Section with `name=None` or no name attribute

```python
# Try standard format first
section = root.find('.//section[@name=""]')

# Fallback: Find ANY section element
if section is None:
    section = root.find('.//section')
```

This handles albums where the section element uses `name=None` instead of `name=""`.

**Why These Fallbacks Are Needed**:
- .blurb format evolved over time (different Bookwright versions)
- User-created albums may have variations from templates
- Older albums may use deprecated element structures
- Ensures maximum compatibility with all .blurb files

#### Error Handling

**Missing Images**:
- Prints warning: `Warning: Could not draw image <path>: [Errno 2] No such file or directory`
- Continues processing remaining pages (non-fatal error)
- Common cause: Image referenced in XML but not in archive

**Missing Sections**:
- Attempts multiple fallback patterns before failing
- Provides clear error message if no section found

**Text Overflow**:
- Auto-sizing prevents text from extending beyond containers
- Clipping paths ensure text stays within bounds even if auto-sizing fails
- Truncation as last resort if text is too large even at minimum font size

**Empty Elements**:
- Gracefully skips pages with no content
- Handles missing text gracefully (no crash)
- Continues processing if individual images fail to load

## Usage Patterns

### Inspect a .blurb file
```bash
sqlite3 "references/2020 Photo Album.blurb" "
SELECT 'Archive Version: ' || version FROM ArchiveVersion;
SELECT 'Total Files: ' || COUNT(*) FROM Files;
SELECT 'Total Size: ' || SUM(filesize) || ' bytes' FROM Files WHERE filesize > 0;
"
```

### View all images
```bash
sqlite3 "path/to/file.blurb" "SELECT filepath FROM Files WHERE filepath LIKE 'images/%' OR filepath LIKE 'thumbnails/%';"
```

### Extract project thumbnail
```bash
sqlite3 "path/to/file.blurb" "SELECT filecontent FROM Files WHERE filepath='project_image.jpg';" > thumbnail.jpg
```

## Best Practices

1. **Always backup** before modifying .blurb files
2. **Never delete template content** - Keep all existing pages, images, and files intact
3. **NEVER modify covers** - Do not alter or remove `<masterpage>` or `<cover>` sections (front/back/inside covers, spine)
4. **NEVER add video files** - Refuse video files (.mp4, .mov, .avi, etc.) - Blurb only supports static images and text
5. **NEVER add RAW files** - Refuse RAW image files (.raw, .cr2, .nef, .arw, .dng, etc.) - Must be processed/exported first
6. **NEVER add GIF files** - Refuse GIF files (.gif) - Must be exported to JPG or PNG first
7. **NEVER add HEIC files** - Always convert .HEIC/.heic files to .JPG using highest quality settings before adding
8. **Add pages at the end** - Insert new pages within `<section>` before the closing `</section>` tag only
9. **Refuse invalid requests** - If asked to delete covers or protected pages, refuse and explain why
10. **Verify integrity** after modifications using sqlite3's integrity_check
11. **Maintain structure** - Keep all template files (images/, thumbnails/, old_bbfs/, etc.)
12. **Set proper dates** - Use ISO 8601 format for filedate
13. **Update filesize** - Calculate and set actual file sizes when modifying files
14. **Check version** - Ensure compatibility with archive version 4
15. **Use inputs directory** - Pull images from `inputs/` directory recursively (always apply file handling rules: refuse video/RAW/GIF, convert HEIC)

## Error Handling

- Check if file exists before operations
- Verify it's a valid SQLite database
- Handle binary data carefully (use readfile/writefile functions)
- Check for successful operations with exit codes
- **Video files**: Always detect and refuse video files before adding to archive
  - Common extensions: .mp4, .mov, .avi, .m4v, .mkv, .webm, .flv, .wmv, .mpeg, .mpg
  - Refuse with explanation that Blurb only supports static content
  - Suggest alternatives: extract still frame, create QR code, add URL text
- **RAW image files**: Always detect and refuse RAW files before adding to archive
  - Common extensions: .raw, .cr2, .nef, .arw, .dng, .orf, .rw2, .pef, .raf, .crw, .sr2, .mrw, .dcr, .x3f, .erf, .kdc, .nrw, .srf
  - Refuse with explanation that RAW files are unprocessed camera data
  - Instruct user to process in photo editor and export as JPG/PNG/TIFF
- **GIF files**: Always detect and refuse GIF files before adding to archive
  - Extension: .gif
  - Refuse with explanation that GIF has quality/compatibility issues and may contain animations
  - Instruct user to export as JPG (for photos) or PNG (for graphics)
- **HEIC files**: Always detect and convert .HEIC/.heic files before adding to archive
  - Use `sips` on macOS or `convert` (ImageMagick) for conversion
  - Use highest quality settings (sips: `best`, ImageMagick: `quality 100`)
  - Update file extension to .jpg in archive path
  - Inform user of automatic conversion

## Examples

### Example 1: Quick inspection
```bash
echo "=== Blurb File Info ==="
sqlite3 "references/templates/2020 empty photo album.blurb" "
SELECT 'Version: ' || version FROM ArchiveVersion;
SELECT '';
SELECT 'Files in archive:';
SELECT filepath || ' (' || filesize || ' bytes)' FROM Files ORDER BY filepath;
"
```

### Example 2: Extract all XML layouts
```bash
mkdir -p extracted_layouts
sqlite3 "path/to/file.blurb" "SELECT filepath FROM Files WHERE filepath LIKE '%.xml';" | while read filepath; do
  sqlite3 "path/to/file.blurb" "SELECT filecontent FROM Files WHERE filepath='$filepath';" > "extracted_layouts/$(basename "$filepath")"
done
```

### Example 2a: Add image to archive (with video/RAW/GIF detection, HEIC conversion, and media registry)
```bash
# Function to add image with video/RAW/GIF detection, HEIC conversion, and media registry
add_image_to_blurb() {
  local blurb_file="$1"
  local source_image="$2"
  local archive_path="$3"  # Path inside archive (e.g., "images/UUID.jpg")

  # FIRST: Check if file is a video (NOT supported)
  if [[ "$source_image" =~ \.(mp4|mov|avi|m4v|mkv|webm|flv|wmv|mpeg|mpg|MP4|MOV|AVI|M4V|MKV|WEBM|FLV|WMV|MPEG|MPG)$ ]]; then
    echo "ERROR: Video files are not supported in Blurb books."
    echo "File: $source_image"
    echo ""
    echo "Blurb books only support static images and text."
    echo "Suggestions:"
    echo "  - Extract a still frame from the video using: ffmpeg -i video.mp4 -ss 00:00:01 -vframes 1 frame.jpg"
    echo "  - Create a QR code linking to the video online"
    echo "  - Add text with a description or URL"
    return 1
  fi

  # SECOND: Check if file is a RAW image (NOT supported)
  if [[ "$source_image" =~ \.(raw|cr2|nef|arw|dng|orf|rw2|pef|raf|crw|sr2|mrw|dcr|x3f|erf|kdc|nrw|srf|RAW|CR2|NEF|ARW|DNG|ORF|RW2|PEF|RAF|CRW|SR2|MRW|DCR|X3F|ERF|KDC|NRW|SRF)$ ]]; then
    echo "ERROR: RAW image files are not supported in Blurb books."
    echo "File: $source_image"
    echo ""
    echo "RAW files must be processed/exported first."
    echo "Steps:"
    echo "  1. Open in photo editor (Lightroom, Photoshop, Photos, etc.)"
    echo "  2. Process/develop with your desired adjustments"
    echo "  3. Export as JPG (recommended), PNG, or TIFF"
    echo "  4. Add the exported file to your Blurb book"
    return 1
  fi

  # THIRD: Check if file is a GIF (NOT supported)
  if [[ "$source_image" =~ \.(gif|GIF)$ ]]; then
    echo "ERROR: GIF files are not supported in Blurb books."
    echo "File: $source_image"
    echo ""
    echo "GIF files must be converted first."
    echo "Steps:"
    echo "  1. Open in image editor (Photoshop, GIMP, Preview, etc.)"
    echo "  2. If animated, choose the frame you want"
    echo "  3. Export as JPG (for photos) or PNG (for graphics)"
    echo "  4. Add the exported file to your Blurb book"
    return 1
  fi

  # FOURTH: Check if file is HEIC and convert if needed
  if [[ "$source_image" =~ \.(heic|HEIC)$ ]]; then
    echo "Converting HEIC to JPG with highest quality..."
    converted_file="${source_image%.*}.jpg"

    # On macOS, use sips (built-in)
    sips -s format jpeg -s formatOptions best "$source_image" --out "$converted_file"

    # Update variables to use converted file
    source_image="$converted_file"
    archive_path="${archive_path%.*}.jpg"  # Change extension in archive path

    echo "Converted to: $converted_file"
  fi

  # Get image dimensions
  img_width=$(sips -g pixelWidth "$source_image" 2>/dev/null | awk '/pixelWidth:/ {print $2}')
  img_height=$(sips -g pixelHeight "$source_image" 2>/dev/null | awk '/pixelHeight:/ {print $2}')

  # Extract GUID from archive path (e.g., images/UUID.jpg -> UUID)
  guid=$(basename "$archive_path" | sed 's/\.[^.]*$//')
  ext="${archive_path##*.}"

  # Add image to archive
  filesize=$(wc -c < "$source_image")
  sqlite3 "$blurb_file" "INSERT OR REPLACE INTO Files (filepath, filecontent, filesize, filedate) VALUES ('$archive_path', readfile('$source_image'), $filesize, datetime('now'));"

  # CRITICAL: Register image in media_registry.xml
  # Extract media_registry.xml
  sqlite3 "$blurb_file" "SELECT writefile('/tmp/media_registry.xml', filecontent) FROM Files WHERE filepath='media_registry.xml';"

  # Add media entry before </images> closing tag
  modified_date=$(date -u +%Y-%m-%dT%H:%M:%S)
  sed -i.bak "/<\/images>/i\\
<media modified=\"$modified_date\" height=\"$img_height\" dateTaken=\"\" webImportAlbum=\"\" enhanceable=\"UNKNOWN\" validated=\"true\" guid=\"$guid\" ext=\"$ext\" width=\"$img_width\" importBatchNum=\"1\" cameraModel=\"unknown\" designerImage=\"false\" cameraMake=\"unknown\" src=\"$archive_path\" webImportSource=\"\"/>" /tmp/media_registry.xml

  # Update archive with modified media_registry.xml
  sqlite3 "$blurb_file" "UPDATE Files SET filecontent=readfile('/tmp/media_registry.xml'), filesize=$(wc -c < /tmp/media_registry.xml), filedate=datetime('now') WHERE filepath='media_registry.xml';"

  # Clean up
  rm /tmp/media_registry.xml /tmp/media_registry.xml.bak 2>/dev/null

  echo "Added $source_image to $blurb_file as $archive_path (${img_width}x${img_height})"
}

# Usage examples
add_image_to_blurb "outputs/My Album.blurb" "photo.heic" "images/$(uuidgen).jpg"  # Will convert HEIC to JPG
add_image_to_blurb "outputs/My Album.blurb" "photo.jpg" "images/$(uuidgen).jpg"   # Normal JPG
add_image_to_blurb "outputs/My Album.blurb" "photo.cr2" "images/photo.jpg"         # Will refuse RAW file
add_image_to_blurb "outputs/My Album.blurb" "photo.gif" "images/photo.jpg"         # Will refuse GIF file
add_image_to_blurb "outputs/My Album.blurb" "video.mp4" "images/video.jpg"         # Will refuse video file
```

### Example 3: Create new file with title and custom page
```bash
# Set book title and author
BOOK_TITLE="My Photo Album 2024"
BOOK_AUTHOR="Jane Smith"

# Ensure outputs directory exists
mkdir -p outputs

# Copy template to start a new project (keeps all template content)
cp "references/templates/2020 empty photo album.blurb" "outputs/My New Album.blurb"

# Extract bbf2.xml
sqlite3 "outputs/My New Album.blurb" "SELECT filecontent FROM Files WHERE filepath='bbf2.xml';" > /tmp/bbf2_temp.xml

# Set the book title in metadata
sed -i.bak 's|<title><!\[CDATA\[.*\]\]></title>|<title><![CDATA['"$BOOK_TITLE"']]></title>|' /tmp/bbf2_temp.xml

# Set the author in metadata
sed -i.bak 's|<author><!\[CDATA\[.*\]\]></author>|<author><![CDATA['"$BOOK_AUTHOR"']]></author>|' /tmp/bbf2_temp.xml

# Set spine text on all cover types
sed -i.bak 's|color:#000000;">​</span>|color:#000000;">'"$BOOK_TITLE"'</span>|g' /tmp/bbf2_temp.xml

# Insert new page before </section> tag
sed -i.bak '/<\/section>/i\
<page number="81" color="#ffffff">\
<container type="text" height="200" x="246" y="197" width="200" id="custom-page">\
<text valign="middle" rotate="0"><![CDATA[<p class="align-center line-height-qt"><span class="font-avenir" data-ascent="42.4px" data-descent="15.8px" style="font-size:60px;color:#000000;">My Custom Page</span></p>]]></text>\
</container>\
</page>' /tmp/bbf2_temp.xml

# Update archive
sqlite3 "outputs/My New Album.blurb" "UPDATE Files SET filecontent=readfile('/tmp/bbf2_temp.xml'), filesize=$(wc -c < /tmp/bbf2_temp.xml), filedate=datetime('now') WHERE filepath='bbf2.xml';"

# Clean up
rm /tmp/bbf2_temp.xml /tmp/bbf2_temp.xml.bak
```

### Example 4: Create test/sample file with random images from inputs directory
```bash
# Set book title and author
BOOK_TITLE="Sample Photo Album"
BOOK_AUTHOR="Test Author"

# Ensure directories exist
mkdir -p outputs inputs

# Copy template
cp "references/templates/2020 empty photo album.blurb" "outputs/Sample Album.blurb"

# Extract bbf2.xml and set title/author
sqlite3 "outputs/Sample Album.blurb" "SELECT filecontent FROM Files WHERE filepath='bbf2.xml';" > /tmp/bbf2_temp.xml
sed -i.bak 's|<title><!\[CDATA\[.*\]\]></title>|<title><![CDATA['"$BOOK_TITLE"']]></title>|' /tmp/bbf2_temp.xml
sed -i.bak 's|<author><!\[CDATA\[.*\]\]></author>|<author><![CDATA['"$BOOK_AUTHOR"']]></author>|' /tmp/bbf2_temp.xml
sed -i.bak 's|color:#000000;">​</span>|color:#000000;">'"$BOOK_TITLE"'</span>|g' /tmp/bbf2_temp.xml

# Update archive with metadata
sqlite3 "outputs/Sample Album.blurb" "UPDATE Files SET filecontent=readfile('/tmp/bbf2_temp.xml'), filesize=$(wc -c < /tmp/bbf2_temp.xml), filedate=datetime('now') WHERE filepath='bbf2.xml';"
rm /tmp/bbf2_temp.xml /tmp/bbf2_temp.xml.bak

# Find all image files recursively in inputs directory (excluding videos, RAW, GIF)
echo "Finding images in inputs directory..."
mapfile -t image_files < <(find inputs -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" -o -iname "*.heic" -o -iname "*.tiff" \) 2>/dev/null | sort -R)

# Check if any images were found
if [ ${#image_files[@]} -eq 0 ]; then
  echo "No images found in inputs directory"
  exit 1
fi

echo "Found ${#image_files[@]} images"

# Add first 10 random images to the archive
count=0
declare -a added_images  # Track added images for media registry
for image_file in "${image_files[@]}"; do
  if [ $count -ge 10 ]; then
    break
  fi

  # Skip if file is a video (extra safety check)
  if [[ "$image_file" =~ \.(mp4|mov|avi|m4v|mkv|webm|flv|wmv|mpeg|mpg)$ ]]; then
    echo "Skipping video file: $image_file"
    continue
  fi

  # Skip if file is a RAW image (extra safety check)
  if [[ "$image_file" =~ \.(raw|cr2|nef|arw|dng|orf|rw2|pef|raf|crw|sr2|mrw|dcr|x3f|erf|kdc|nrw|srf)$ ]]; then
    echo "Skipping RAW file: $image_file"
    continue
  fi

  # Skip if file is a GIF (extra safety check)
  if [[ "$image_file" =~ \.(gif|GIF)$ ]]; then
    echo "Skipping GIF file: $image_file"
    continue
  fi

  # Generate unique GUID for this image
  guid=$(uuidgen)
  filename=$(basename "$image_file")
  ext="${filename##*.}"
  archive_path="images/${guid}.${ext}"

  # Convert HEIC to JPG if needed
  source_file="$image_file"
  if [[ "$image_file" =~ \.(heic|HEIC)$ ]]; then
    echo "Converting HEIC to JPG: $filename"
    temp_jpg="/tmp/$(uuidgen).jpg"
    sips -s format jpeg -s formatOptions best "$image_file" --out "$temp_jpg" 2>/dev/null
    source_file="$temp_jpg"
    ext="jpg"
    archive_path="images/${guid}.jpg"
  fi

  # Get image dimensions
  img_width=$(sips -g pixelWidth "$source_file" 2>/dev/null | awk '/pixelWidth:/ {print $2}')
  img_height=$(sips -g pixelHeight "$source_file" 2>/dev/null | awk '/pixelHeight:/ {print $2}')

  # Add image to archive
  filesize=$(wc -c < "$source_file")
  sqlite3 "outputs/Sample Album.blurb" "INSERT OR REPLACE INTO Files (filepath, filecontent, filesize, filedate) VALUES ('$archive_path', readfile('$source_file'), $filesize, datetime('now'));"

  # Store image info for media registry
  added_images+=("$guid|$ext|$img_width|$img_height|$archive_path")

  echo "Added: $filename as $archive_path (${img_width}x${img_height})"

  # Clean up temp file if created
  if [[ "$source_file" == /tmp/* ]]; then
    rm "$source_file"
  fi

  ((count++))
done

# Register all images in media_registry.xml
echo "Registering $count images in media_registry.xml..."
sqlite3 "outputs/Sample Album.blurb" "SELECT writefile('/tmp/media_registry.xml', filecontent) FROM Files WHERE filepath='media_registry.xml';"

for image_info in "${added_images[@]}"; do
  IFS='|' read -r guid ext width height src <<< "$image_info"
  modified_date=$(date -u +%Y-%m-%dT%H:%M:%S)

  # Insert media entry before </images> closing tag
  sed -i.bak "/<\/images>/i\\
<media modified=\"$modified_date\" height=\"$height\" dateTaken=\"\" webImportAlbum=\"\" enhanceable=\"UNKNOWN\" validated=\"true\" guid=\"$guid\" ext=\"$ext\" width=\"$width\" importBatchNum=\"1\" cameraModel=\"unknown\" designerImage=\"false\" cameraMake=\"unknown\" src=\"$src\" webImportSource=\"\"/>" /tmp/media_registry.xml
done

# Update archive with modified media_registry.xml
sqlite3 "outputs/Sample Album.blurb" "UPDATE Files SET filecontent=readfile('/tmp/media_registry.xml'), filesize=$(wc -c < /tmp/media_registry.xml), filedate=datetime('now') WHERE filepath='media_registry.xml';"

# Clean up
rm /tmp/media_registry.xml /tmp/media_registry.xml.bak 2>/dev/null

echo "Sample album created with $count images: outputs/Sample Album.blurb"
```

## Workflow

When invoked with `/blurb` or when user mentions "photo album", "album", or "book":

1. **Determine user intent** from arguments or context
   - Recognize synonyms: "album", "photo album", "book" all refer to .blurb files
   - Understand requests like "create an album", "add to my photo album", etc.
2. **For create operations (NOT test/sample files):**
   - Check if output path is specified, otherwise use `outputs/` directory
   - Create the output directory if it doesn't exist
   - **Check if title is specified (REQUIRED)**
   - If title not specified, ask user for the book title
   - **Check if author is specified (REQUIRED)**
   - If author not specified, ask user for the book author
   - Check if template is specified
   - If not specified:
     - **List all available templates** from `references/templates/` directory using:
       ```bash
       find references/templates -maxdepth 1 -type f -name "*.blurb" -exec basename {} \; | sort
       ```
     - Present the list to the user
     - Use AskUserQuestion to let user choose from available templates
   - Copy the selected template to the output location
   - Set the title in book metadata (`<info><title>`)
   - Set the author in book metadata (`<info><author>`)
   - Set the title in all spine text elements (softcover, imagewrap, dustjacket)
2a. **For operations using inputs/ directory:**
   - Check if user wants to use images from `inputs/` directory
   - Use `find` to search recursively: `find inputs -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" -o -iname "*.heic" -o -iname "*.tiff" \)`
   - Randomize order with `sort -R` and limit with `head -n N` (for test/sample files)
   - **CRITICAL: Apply file handling rules to ALL images before adding** (see section 3 below)
   - Generate unique archive path using `uuidgen`
   - Add to archive with proper filesize and date
   - Report how many images were added
3. **For ALL image/file addition operations - FILE HANDLING FIRST:**
   - **CRITICAL: These checks apply to ALL image operations** (bulk, batch, test, sample, individual)

   **ALWAYS perform these checks BEFORE adding any image:**
   1. **Check if file is a video format** (.mp4, .mov, .avi, .m4v, .mkv, .webm, .flv, .wmv, .mpeg, .mpg)
      - If video, **REFUSE and explain** that Blurb only supports static content
      - Suggest alternatives (extract still frame, create QR code, add URL text)

   2. **Check if file is a RAW format** (.raw, .cr2, .nef, .arw, .dng, .orf, .rw2, .pef, .raf, etc.)
      - If RAW, **REFUSE and explain** that RAW files must be processed/exported first
      - Instruct user to open in photo editor, process, and export as JPG/PNG/TIFF

   3. **Check if file is a GIF format** (.gif, .GIF)
      - If GIF, **REFUSE and explain** that GIF files have quality/compatibility issues
      - Instruct user to export as JPG (for photos) or PNG (for graphics)

   4. **Check if file is HEIC format** (.heic or .HEIC extension)
      - If HEIC, **AUTOMATICALLY convert to JPG** using highest quality settings
      - Inform user of conversion
      - Update archive path to use .jpg extension
      - Add the converted JPG to the archive

3a. **After file validation - CHOOSE METHOD:**
   - **CRITICAL DECISION**: Determine which method to use based on request:

   **Use BATCH METHOD (Section 5d) when:**
   - User specifies 1-6 specific images (e.g., "add 5 images", "add these 3 photos")
   - User wants images on SAME page together
   - Example: "add 5 random images", "add photo1.jpg photo2.jpg photo3.jpg"
   - Process: Find template page with N containers, fill all containers on ONE page

   **Use BULK METHOD (Section 5c) when:**
   - User says "add ALL images from inputs", "add many images", "populate the book"
   - User wants 10+ images
   - User wants one image per page
   - Example: "add all images from inputs folder", "add images to fill the book"
   - Process: Create one page per image, insert at beginning

4. **Implementation: Bulk image addition (add multiple images):**
   - Find all images in `inputs/` directory recursively
   - **Apply file handling rules from section 3** (refuse video/RAW/GIF, convert HEIC)
   - Extract bbf2.xml from the .blurb file
   - Parse XML to find all pages in `<section>` with image containers (exclude `<masterpage>` and `<cover>`)
   - For each validated image:
     - Generate unique GUID
     - Add to archive with dimensions
     - Extract caption from XMP:Description metadata
   - Update media_registry.xml with all new images
   - For each image, create a new page:
     - **Pick a random template page** (different for each page to create variety)
     - Clone the selected template page
     - Find first `<container type="image">` in cloned page
     - Set or create `<image src="path">` with the new GUID path
     - Place caption in first `<container type="text">` as HTML
   - Insert new pages at beginning of section (position 0)
   - Renumber all existing pages (shift by number of new pages)
   - Update archive with modified bbf2.xml
   - Report: number of images added, number of pages created

5. **Implementation: Batch image addition (add 1-6 images on same page):**
   - **This is the DEFAULT method when user specifies 1-6 images**
   - Examples: "add 5 random images", "add these 3 photos", "add photo1.jpg photo2.jpg"
   - User specifies 1-6 specific images to add
   - **Apply file handling rules from section 3** (refuse video/RAW/GIF, convert HEIC)
   - Count the batch size (N = number of images)
   - Extract bbf2.xml from the .blurb file
   - Parse XML to find template pages with EXACTLY N image containers
   - If multiple pages match, pick one at random
   - If NO pages match, report error showing available container counts
   - For each validated image:
     - Generate unique GUID
     - Add to archive with dimensions
     - Extract caption from XMP:Description metadata
   - Update media_registry.xml with all new images
   - Clone the selected template page
   - Fill ALL N image containers on the page (not just first):
     - Set `<image src="filename">` for each container (filename only, not path)
     - Ensure `autolayout="fill"` attribute is set
   - Place captions in adjacent text containers
   - Find highest page number in book
   - Append new page to END of book (highest_page + 1)
   - Update archive with modified bbf2.xml
   - Report: batch size added, page number created, all images on ONE page together

6. **For read/modify operations:**
   - Validate the .blurb file exists and is readable
7. **Execute** the appropriate SQLite commands
8. **Format output** in a readable way
9. **Report** success or errors clearly
10. **Suggest** next steps if applicable
11. **Run integrity check** (MANDATORY final step — see "Integrity Check" section below)

## Verification and Testing

After adding images to a .blurb file, verify they will display correctly in Bookwright:

### Quick Verification Commands

**1. Check image src attributes (must be filename only, not path):**
```bash
# Extract and verify image src attributes
sqlite3 "outputs/My Book.blurb" "SELECT filecontent FROM Files WHERE filepath='bbf2.xml';" > /tmp/verify.xml

python3 << 'VERIFY'
import xml.etree.ElementTree as ET
tree = ET.parse('/tmp/verify.xml')
root = tree.getroot()
section = root.find('.//section[@name=""]')

print("Checking first 5 pages:")
for page in list(section.findall('page'))[:5]:
    page_num = page.get('number')
    for container in page.findall('.//container[@type="image"]'):
        image = container.find('image')
        if image is not None:
            src = image.get('src')
            autolayout = image.get('autolayout')

            # Verify src is filename only
            if '/' in src:
                print(f"❌ FAIL Page {page_num}: src='{src}' (contains path, should be filename only)")
            else:
                print(f"✅ OK Page {page_num}: src='{src}'")

            # Verify autolayout exists
            if autolayout != 'fill':
                print(f"   ⚠️  WARNING: autolayout='{autolayout}' (should be 'fill')")

            break
VERIFY
```

**Expected output:**
```
✅ OK Page 1: src='GUID.jpg'
✅ OK Page 2: src='GUID.jpg'
✅ OK Page 3: src='GUID.jpg'
```

**2. Verify images exist in archive:**
```bash
# List all image files in archive
sqlite3 "outputs/My Book.blurb" "SELECT filepath FROM Files WHERE filepath LIKE 'images/%' ORDER BY filepath;"
```

**3. Verify media registry entries:**
```bash
# Check media_registry.xml contains entries for all images
sqlite3 "outputs/My Book.blurb" "SELECT filecontent FROM Files WHERE filepath='media_registry.xml';" | grep -o '<media.*guid=' | wc -l
```

### Testing Checklist

Before considering image addition complete:

- [ ] Images appear in Bookwright application (open file and check visually)
- [ ] All `src` attributes use filename only (`"GUID.jpg"` not `"images/GUID.jpg"`)
- [ ] All image elements have `autolayout="fill"` attribute
- [ ] Image files exist in archive at `images/GUID.jpg` paths
- [ ] Media registry contains entries for all images
- [ ] Random templates used (pages don't all look identical)
- [ ] File size increased appropriately (images are large)

### Common Failure Modes

**Symptom: Images don't appear in Bookwright**
- Check: `src` attribute - should be `"GUID.jpg"` not `"images/GUID.jpg"`
- Check: `autolayout` attribute - must be `"fill"`
- Check: Image files exist in archive - run verification command #2
- Check: Media registry entries - run verification command #3

**Symptom: All pages look identical**
- Check: Random selection happens inside loop (see Bug #3)
- Look at template page numbers in output - should vary

**Symptom: Empty pages created**
- Check: Image src is actually set (not empty or missing)
- Check: Image element exists in container (not just container)

## Integrity Check (MANDATORY Final Step)

**CRITICAL**: After ANY operation that creates or modifies a .blurb file, run this integrity check before reporting success. If any check fails, fix the issue before finishing.

Run the following Python script against the completed .blurb file. Replace `BLURB_PATH` with the actual output path.

```bash
python3 << 'INTEGRITY_CHECK'
import sqlite3, sys, json, os

BLURB_PATH = "outputs/REPLACE_ME.blurb"
errors = []
warnings = []

def err(msg):
    errors.append(msg)
    print(f"  FAIL: {msg}")

def warn(msg):
    warnings.append(msg)
    print(f"  WARN: {msg}")

def ok(msg):
    print(f"  OK:   {msg}")

print(f"\n{'='*60}")
print(f"BLURB INTEGRITY CHECK: {os.path.basename(BLURB_PATH)}")
print(f"{'='*60}")

# ── 1. SQLite validity ──────────────────────────────────────
print("\n[1] SQLite database validity")
try:
    conn = sqlite3.connect(BLURB_PATH)
    conn.execute("PRAGMA integrity_check")
    ok("SQLite database is valid")
except Exception as e:
    err(f"SQLite database is corrupt: {e}")
    sys.exit(1)

# ── 2. Required tables ──────────────────────────────────────
print("\n[2] Required tables")
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
for t in ("Files", "ArchiveVersion"):
    if t in tables:
        ok(f"Table '{t}' exists")
    else:
        err(f"Table '{t}' is missing")

# ── 3. Archive version ──────────────────────────────────────
print("\n[3] Archive version")
row = conn.execute("SELECT version FROM ArchiveVersion LIMIT 1").fetchone()
if row and row[0] == 4:
    ok(f"Archive version is {row[0]}")
elif row:
    warn(f"Archive version is {row[0]} (expected 4)")
else:
    err("ArchiveVersion table is empty")

# ── 4. Required archive files ───────────────────────────────
print("\n[4] Required archive files")
filepaths = [r[0] for r in conn.execute("SELECT filepath FROM Files").fetchall()]
for req in ("bbf2.xml", "project_settings.json", "media_registry.xml"):
    if req in filepaths:
        ok(f"'{req}' present in archive")
    else:
        err(f"'{req}' missing from archive")

# ── 5. bbf2.xml parse and structure ─────────────────────────
print("\n[5] bbf2.xml structure")
import xml.etree.ElementTree as ET
bbf2_blob = conn.execute("SELECT filecontent FROM Files WHERE filepath='bbf2.xml'").fetchone()
if not bbf2_blob:
    err("Cannot read bbf2.xml content")
    sys.exit(1)

bbf2_text = bbf2_blob[0] if isinstance(bbf2_blob[0], str) else bbf2_blob[0].decode("utf-8")
try:
    root = ET.fromstring(bbf2_text)
    ok("bbf2.xml parses as valid XML")
except ET.ParseError as e:
    err(f"bbf2.xml is not valid XML: {e}")
    sys.exit(1)

# Root element
if root.tag == "book":
    ok("Root element is <book>")
else:
    err(f"Root element is <{root.tag}> (expected <book>)")

# ── 6. Metadata ─────────────────────────────────────────────
print("\n[6] Book metadata")
info = root.find("info")
if info is not None:
    title_el = info.find("title")
    author_el = info.find("author")
    title = (title_el.text or "").strip() if title_el is not None else ""
    author = (author_el.text or "").strip() if author_el is not None else ""
    if title:
        ok(f"Title: '{title}'")
    else:
        err("Title is empty or missing")
    if author:
        ok(f"Author: '{author}'")
    else:
        err("Author is empty or missing")
else:
    err("<info> section is missing")

# ── 7. Protected elements ───────────────────────────────────
print("\n[7] Protected structural elements")

# Masterpage
masterpage = root.find("masterpage")
if masterpage is not None:
    mp_pages = masterpage.findall("page")
    if len(mp_pages) >= 2:
        ok(f"<masterpage> has {len(mp_pages)} pages (inside covers)")
    else:
        err(f"<masterpage> has {len(mp_pages)} pages (expected >= 2)")
else:
    err("<masterpage> section is missing")

# Covers — detect by type= attribute or sku= attribute pattern
# Some templates use sku="PHBK-...-IW-..." instead of type="imagewrap", etc.
sku_to_cover = {"-IW-": "imagewrap", "-SC-": "softcover", "-DJ-": "dustjacket"}
found_covers = set()
for c in root.findall("cover"):
    ct = c.get("type", "")
    if ct:
        found_covers.add(ct)
    sku = c.get("sku", "")
    for pattern, cover_name in sku_to_cover.items():
        if pattern in sku:
            found_covers.add(cover_name)

required_covers = ["softcover", "imagewrap", "dustjacket"]
for ct in required_covers:
    if ct in found_covers:
        ok(f"<cover type=\"{ct}\"> present")
    else:
        err(f"<cover type=\"{ct}\"> is missing")

# Ebook is optional — not all templates include it
if "ebook" in found_covers:
    ok('<cover type="ebook"> present')
else:
    warn('<cover type="ebook"> not found (optional)')

# ── 8. Section and page numbering ───────────────────────────
print("\n[8] Content section and page numbering")
section = root.find('.//section[@name=""]')
if section is None:
    section = root.find("section")
if section is not None:
    ok("<section> present")
    pages = section.findall("page")
    if len(pages) > 0:
        ok(f"{len(pages)} content pages found")
    else:
        warn("Section has 0 content pages")

    # Check sequential numbering
    page_nums = []
    for p in pages:
        n = p.get("number")
        if n is not None:
            try:
                page_nums.append(int(n))
            except ValueError:
                err(f"Non-integer page number: '{n}'")
    if page_nums:
        expected = list(range(1, len(page_nums) + 1))
        if page_nums == expected:
            ok(f"Pages numbered sequentially 1–{len(page_nums)}")
        else:
            # Check for gaps or duplicates
            dupes = [n for n in page_nums if page_nums.count(n) > 1]
            if dupes:
                err(f"Duplicate page numbers: {sorted(set(dupes))}")
            if page_nums != sorted(page_nums):
                err("Pages are not in ascending order")
            if sorted(page_nums) != expected:
                warn(f"Page numbers are not sequential 1–N (found {page_nums[0]}–{page_nums[-1]}, {len(page_nums)} pages)")
else:
    err("<section> is missing")

# ── 9. Image references ─────────────────────────────────────
print("\n[9] Image reference integrity")
image_elements = root.findall('.//section//container[@type="image"]/image')
archive_images = set(f for f in filepaths if f.startswith("images/"))
src_issues = 0
autolayout_issues = 0
missing_from_archive = []
referenced_srcs = set()

for img in image_elements:
    src = img.get("src", "")
    if not src:
        continue
    referenced_srcs.add(src)

    # src must be filename only (not a path)
    if "/" in src:
        if src_issues < 5:
            err(f"Image src contains path: '{src}' (must be filename only)")
        src_issues += 1
    else:
        # Check image exists in archive
        archive_path = f"images/{src}"
        if archive_path not in archive_images:
            missing_from_archive.append(src)

    # autolayout must be 'fill'
    al = img.get("autolayout", "")
    if al != "fill":
        if autolayout_issues < 5:
            warn(f"Image '{src}' has autolayout='{al}' (should be 'fill')")
        autolayout_issues += 1

if src_issues > 5:
    print(f"  ... and {src_issues - 5} more src path issues")
if autolayout_issues > 5:
    print(f"  ... and {autolayout_issues - 5} more autolayout issues")
if missing_from_archive:
    for m in missing_from_archive[:5]:
        err(f"Image referenced but not in archive: '{m}'")
    if len(missing_from_archive) > 5:
        print(f"  ... and {len(missing_from_archive) - 5} more missing images")
if not src_issues and not missing_from_archive:
    ok(f"{len(referenced_srcs)} image references all valid")
if not autolayout_issues and referenced_srcs:
    ok("All images have autolayout='fill'")

# ── 10. Media registry ──────────────────────────────────────
print("\n[10] Media registry")
mr_blob = conn.execute("SELECT filecontent FROM Files WHERE filepath='media_registry.xml'").fetchone()
if mr_blob:
    mr_text = mr_blob[0] if isinstance(mr_blob[0], str) else mr_blob[0].decode("utf-8")
    try:
        mr_root = ET.fromstring(mr_text)
        media_entries = mr_root.findall(".//media")
        registry_guids = set()
        for m in media_entries:
            g = m.get("guid", "")
            if g:
                registry_guids.add(g)
        ok(f"{len(media_entries)} media entries in registry")

        # Cross-check: images in pages should have media registry entries
        page_guids = set()
        for img in image_elements:
            g = img.get("guid", "")
            if g:
                page_guids.add(g)

        missing_registry = page_guids - registry_guids
        if missing_registry:
            for m in list(missing_registry)[:5]:
                err(f"Image guid '{m}' used in pages but missing from media registry")
            if len(missing_registry) > 5:
                print(f"  ... and {len(missing_registry) - 5} more missing entries")
        else:
            ok("All page image GUIDs have media registry entries")
    except ET.ParseError as e:
        err(f"media_registry.xml is not valid XML: {e}")
else:
    err("media_registry.xml content is empty or unreadable")

# ── 11. Filesize consistency ─────────────────────────────────
print("\n[11] Archive file sizes")
size_mismatches = 0
for row in conn.execute("SELECT filepath, filesize, length(filecontent) FROM Files"):
    fpath, declared, actual = row
    if declared is not None and declared != -1 and declared != actual:
        if size_mismatches < 3:
            warn(f"'{fpath}': declared size {declared} != actual {actual}")
        size_mismatches += 1
if size_mismatches > 3:
    print(f"  ... and {size_mismatches - 3} more size mismatches")
if size_mismatches == 0:
    ok("All file sizes are consistent")

# ── 12. Forbidden file types in archive ──────────────────────
print("\n[12] Forbidden file types")
forbidden_exts = {".mp4", ".mov", ".avi", ".m4v", ".mkv", ".webm", ".flv", ".wmv",
                  ".mpeg", ".mpg", ".raw", ".cr2", ".nef", ".arw", ".dng", ".orf",
                  ".rw2", ".pef", ".raf", ".crw", ".sr2", ".gif", ".heic"}
found_forbidden = []
for fp in filepaths:
    ext = os.path.splitext(fp)[1].lower()
    if ext in forbidden_exts:
        found_forbidden.append(fp)
if found_forbidden:
    for ff in found_forbidden[:5]:
        err(f"Forbidden file in archive: '{ff}'")
    if len(found_forbidden) > 5:
        print(f"  ... and {len(found_forbidden) - 5} more forbidden files")
else:
    ok("No forbidden file types in archive")

# ── 13. Spine text matches title ─────────────────────────────
print("\n[13] Spine text consistency")
if title:
    spine_covers = ["softcover", "imagewrap", "dustjacket"]
    for cover in root.findall("cover"):
        ct = cover.get("type", "")
        # Also detect cover type by SKU pattern
        sku = cover.get("sku", "")
        if not ct or ct not in spine_covers:
            for pat, cname in {"-IW-": "imagewrap", "-SC-": "softcover", "-DJ-": "dustjacket"}.items():
                if pat in sku:
                    ct = cname
                    break
        if ct not in spine_covers:
            continue
        # Look for spineText in both <spine> and <coversheet> elements
        spine_parents = []
        spine = cover.find("spine")
        if spine is not None:
            spine_parents.append(spine)
        coversheet = cover.find("coversheet")
        if coversheet is not None:
            spine_parents.append(coversheet)
        if not spine_parents:
            continue
        found_title = False
        for parent in spine_parents:
            for cont in parent.findall('.//container[@role="spineText"]'):
                text_el = cont.find("text")
                if text_el is not None and text_el.text:
                    spine_text = text_el.text.strip()
                    import re
                    raw = re.sub(r'<[^>]+>', '', spine_text).strip()
                    if title.lower() in raw.lower():
                        found_title = True
        if found_title:
            ok(f"{ct} spine contains title")
        else:
            warn(f"{ct} spine may not contain title '{title}'")

# ── Summary ─────────────────────────────────────────────────
conn.close()
print(f"\n{'='*60}")
print(f"RESULTS: {len(errors)} errors, {len(warnings)} warnings")
if errors:
    print("INTEGRITY CHECK FAILED — fix errors before delivering file")
else:
    print("INTEGRITY CHECK PASSED")
print(f"{'='*60}\n")

sys.exit(1 if errors else 0)
INTEGRITY_CHECK
```

### When to Run

- After creating a new .blurb file from a template
- After adding images (bulk or batch)
- After setting title and author
- After any modification to bbf2.xml, media_registry.xml, or archive contents
- **Always the LAST step before reporting success to the user**

### What It Checks

| # | Check | Severity |
|---|-------|----------|
| 1 | SQLite database is valid (not corrupt) | Error |
| 2 | Required tables exist (Files, ArchiveVersion) | Error |
| 3 | Archive version is 4 | Warning |
| 4 | Required files present (bbf2.xml, project_settings.json, media_registry.xml) | Error |
| 5 | bbf2.xml parses as valid XML with `<book>` root | Error |
| 6 | Title and author are non-empty | Error |
| 7 | Protected elements present (masterpage, 3 required covers by type/sku; ebook optional) | Error/Warning |
| 8 | Content pages numbered sequentially without gaps or duplicates | Error/Warning |
| 9 | Image `src` attributes are filename-only; images exist in archive; `autolayout="fill"` set | Error/Warning |
| 10 | Media registry entries exist for all image GUIDs used in pages | Error |
| 11 | Declared file sizes match actual blob sizes | Warning |
| 12 | No forbidden file types in archive (video, RAW, GIF, HEIC) | Error |
| 13 | Spine text contains the book title on all spine-bearing cover types | Warning |

### Handling Failures

- **Errors**: Must be fixed before the file is delivered. Go back and correct the issue, then re-run the integrity check.
- **Warnings**: Report to the user but do not block delivery. These indicate potential issues that may or may not matter.
- **If the check passes**: Report "Integrity check passed" along with the summary line.

### Example Output

```
============================================================
BLURB INTEGRITY CHECK: My Album 2026-03-09 14:30.blurb
============================================================

[1] SQLite database validity
  OK:   SQLite database is valid

[2] Required tables
  OK:   Table 'Files' exists
  OK:   Table 'ArchiveVersion' exists

[3] Archive version
  OK:   Archive version is 4

[4] Required archive files
  OK:   'bbf2.xml' present in archive
  OK:   'project_settings.json' present in archive
  OK:   'media_registry.xml' present in archive

[5] bbf2.xml structure
  OK:   bbf2.xml parses as valid XML
  OK:   Root element is <book>

[6] Book metadata
  OK:   Title: 'My Album'
  OK:   Author: 'John Wilson'

[7] Protected structural elements
  OK:   <masterpage> has 2 pages (inside covers)
  OK:   <cover type="softcover"> present
  OK:   <cover type="imagewrap"> present
  OK:   <cover type="dustjacket"> present
  WARN: <cover type="ebook"> not found (optional)

[8] Content section and page numbering
  OK:   <section> present
  OK:   42 content pages found
  OK:   Pages numbered sequentially 1–42

[9] Image reference integrity
  OK:   38 image references all valid
  OK:   All images have autolayout='fill'

[10] Media registry
  OK:   38 media entries in registry
  OK:   All page image GUIDs have media registry entries

[11] Archive file sizes
  OK:   All file sizes are consistent

[12] Forbidden file types
  OK:   No forbidden file types in archive

[13] Spine text consistency
  OK:   softcover spine contains title
  OK:   imagewrap spine contains title
  OK:   dustjacket spine contains title

============================================================
RESULTS: 0 errors, 1 warning
INTEGRITY CHECK PASSED
============================================================
```

## Notes

- **REQUIRED**: Every new .blurb file must have a title and author specified
  - Title is set in `<info><title>` for book metadata (Book details/Project title)
  - Author is set in `<info><author>` for book metadata (Book details/Author Name)
  - Title is set in spine text on all cover types (softcover, imagewrap, dustjacket)
  - If user doesn't provide a title or author, ask for them before creating the file
- **Source Images**: Use `inputs/` directory for source images
  - Place source images in `inputs/` directory or subdirectories
  - When creating test/sample files, pull random images from `inputs/` recursively
  - Use `find inputs -type f \( -iname "*.jpg" ... \)` to locate images
  - Automatically converts HEIC and filters out video, RAW, and GIF files
  - Generate unique filenames using `uuidgen` to avoid conflicts
- **CRITICAL**: Video files are NOT supported - must be refused
  - **NEVER add video files** (.mp4, .mov, .avi, .m4v, .mkv, .webm, .flv, .wmv, .mpeg, .mpg)
  - Blurb books only support static content: images (JPG, PNG, TIFF) and text
  - Printed books cannot play videos; Blurb's format does not support video playback
  - **REFUSE** any request to add video files and explain why
  - Suggest alternatives: extract still frame, create QR code linking to video, add URL text
- **CRITICAL**: RAW image files are NOT supported - must be refused
  - **NEVER add RAW files** (.raw, .cr2, .nef, .arw, .dng, .orf, .rw2, .pef, .raf, .crw, .sr2, .mrw, .dcr, .x3f, .erf, .kdc, .nrw, .srf, etc.)
  - RAW files are unprocessed camera data and cannot be rendered by Bookwright
  - RAW files must be processed/developed in a photo editor first
  - **REFUSE** any request to add RAW files and explain why
  - Instruct user to: (1) Open in photo editor, (2) Process/develop, (3) Export as JPG/PNG/TIFF
- **CRITICAL**: GIF files are NOT supported - must be refused
  - **NEVER add GIF files** (.gif, .GIF)
  - GIF format may contain animations and has quality/compatibility issues (limited to 256 colors)
  - GIF is designed for web graphics, not print-quality photos
  - **REFUSE** any request to add GIF files and explain why
  - Instruct user to: (1) Open in image editor, (2) Choose frame if animated, (3) Export as JPG (photos) or PNG (graphics)
- **CRITICAL**: HEIC files are NOT supported - must be converted to JPG first
  - **NEVER add .HEIC or .heic files** directly to the archive
  - Always detect HEIC files and convert to JPG using highest quality settings
  - On macOS: use `sips -s format jpeg -s formatOptions best` command
  - Cross-platform: use `convert -quality 100` (ImageMagick)
  - Update file extension to .jpg in the archive path after conversion
  - Inform user that automatic conversion was performed
- **CRITICAL**: Never delete or modify cover pages - this creates invalid files
  - `<masterpage>` section with inside covers (page number="-1") must remain
  - All `<cover>` sections (softcover, imagewrap, dustjacket, ebook) must remain
  - Front cover, back cover, spine elements are structural requirements
  - **REFUSE** any request to delete covers, inside covers, or outside covers
- **CRITICAL**: Never delete template pages, images, or content within `<section>` - this creates invalid files
- **Always ADD content** to templates, don't remove existing content
- Only add new pages within `<section>` area (numbered 81+)
- **Two Ways to Add Images**:
  1. **Bulk Image Addition (Section 5c)** - For adding many images from a directory:
     - Adds ALL images from `inputs/` directory
     - **One image per page** (each image gets its own page)
     - Picks a random template page for EACH new page (creates layout variety)
     - **Inserts pages at the BEGINNING** of the book
     - Automatically renumbers existing pages
     - Best for: Initial book population, adding 10+ images at once
     - **Fixed**: Images properly inserted, random template per page
  2. **Batch Image Addition (Section 5d)** - For adding small groups together:
     - Adds 1-6 specific images as a batch
     - **Multiple images per page** (all images share one page)
     - Finds template page with matching number of containers
     - **Appends page to the END** of the book
     - No renumbering needed
     - Best for: Incremental additions, multiple images that belong together
     - Example: Add 3 vacation photos on a single page with 3 containers
- All newly created .blurb files are saved to the `outputs/` directory by default
- .blurb files can be quite large (>1GB for photo albums with many images)
- Use BLOB handling carefully - binary data must not be corrupted
- The `old_bbfs/` directory contains versioned page layouts (keep these)
- Image optimization settings are in project_settings.json
- Always test modifications on copies first
- Templates contain 80 content pages - new pages should be numbered 81+
