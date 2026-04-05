---
name: blurb-to-pdf
description: Convert Bookwright .blurb files to PDF with covers, content pages, images, and text preserved. Use when the user asks for PDF output from a .blurb album.
---

# Blurb To PDF Skill

This skill converts a .blurb file (Bookwright SQLite archive) into a PDF.

## Scope

Use this skill only for PDF conversion. For editing .blurb archive contents, page templates, or metadata, use the `blurb` skill.

## Requirements

- Python 3
- `reportlab` and `pillow`
- `sqlite3` CLI (available by default on macOS)

Install dependencies:

```bash
pip3 install --user --break-system-packages reportlab pillow
```

## Usage

```bash
python3 .claude/skills/blurb-to-pdf/blurb_to_pdf.py "path/to/file.blurb"
```

Output:

- Creates `path/to/file.pdf`
- Overwrites an existing PDF at that path

## Operational Guardrails

- Run one conversion at a time.
- Do not run concurrent PDF conversions for multiple albums.
- Large albums can take several minutes.

## What Is Included

- Front and back covers
- All content pages in section order
- Image containers with transforms and clipping
- Text containers with alignment and rotation
- Page background colors
- PDF metadata from book title/author

## What Is Excluded

- Inside cover pages from `masterpage`
- Pure spine-only elements
