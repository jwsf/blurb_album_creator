#!/usr/bin/env python3
"""
Create a new .blurb file from a template.
Copies the template, sets title, author, and spine text.

CRITICAL: Uses string-based XML manipulation to preserve CDATA wrappers,
XML declaration format, and other formatting that Bookwright requires.

Usage:
    python3 create_blurb.py --template <template.blurb> --title <title> \
                             --author <author> --output <output.blurb>

    python3 create_blurb.py --template "references/templates/FamilyBook-StandardLandscape.blurb" \
                             --title "2021 Photos" --author "Your Name" \
                             --output "outputs/2021 Photos 2026-04-04 08:43.blurb"
"""

import argparse
import os
import re
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


ZERO_WIDTH_SPACE = "\u200b"


def read_bbf2(blurb_file):
    """Extract bbf2.xml content from the archive as a string."""
    conn = sqlite3.connect(blurb_file)
    row = conn.execute(
        "SELECT filecontent FROM Files WHERE filepath='bbf2.xml'"
    ).fetchone()
    conn.close()
    if not row:
        print("ERROR: bbf2.xml not found in archive")
        sys.exit(1)
    raw = row[0]
    return raw if isinstance(raw, str) else raw.decode("utf-8")


def write_bbf2(blurb_file, xml_text):
    """Write updated bbf2.xml back into the archive."""
    data = xml_text.encode("utf-8")
    filesize = len(data)
    conn = sqlite3.connect(blurb_file)
    conn.execute(
        "UPDATE Files SET filecontent=?, filesize=?, filedate=datetime('now') "
        "WHERE filepath='bbf2.xml'",
        (data, filesize),
    )
    conn.commit()
    conn.close()


def set_title(xml, title):
    """Replace the <info><title> CDATA value."""
    return re.sub(
        r'<title><!\[CDATA\[.*?\]\]></title>',
        f'<title><![CDATA[{title}]]></title>',
        xml,
        count=1,
        flags=re.DOTALL,
    )


def set_author(xml, author):
    """Replace the <info><author> CDATA value."""
    return re.sub(
        r'<author><!\[CDATA\[.*?\]\]></author>',
        f'<author><![CDATA[{author}]]></author>',
        xml,
        count=1,
        flags=re.DOTALL,
    )


def set_spine_text(xml, title):
    """Replace zero-width space placeholder in all spine text containers."""
    return xml.replace(
        f'color:#000000;">{ZERO_WIDTH_SPACE}</span>',
        f'color:#000000;">{title}</span>',
    )


def save_last_options(template, title, author):
    """Persist creation options to /tmp for future default suggestions."""
    import json
    options = {
        "template": template,
        "title": title,
        "author": author,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    with open("/tmp/blurb_last_create_options.json", "w") as f:
        json.dump(options, f, indent=2)


def create_blurb(template, title, author, output):
    """Create a new .blurb file from a template with the given metadata."""

    # Validate inputs
    if not os.path.exists(template):
        print(f"ERROR: Template not found: {template}")
        sys.exit(1)

    output_dir = os.path.dirname(output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # Remove any stale WAL/SHM files at the output path before copying
    for ext in ("", "-shm", "-wal"):
        stale = output + ext
        if os.path.exists(stale):
            os.remove(stale)

    print(f"Template:  {template}")
    print(f"Title:     {title}")
    print(f"Author:    {author}")
    print(f"Output:    {output}")
    print()

    # Copy template
    shutil.copy2(template, output)
    print(f"Copied template → {os.path.basename(output)}")

    # Read, update, write bbf2.xml
    xml = read_bbf2(output)
    xml = set_title(xml, title)
    xml = set_author(xml, author)
    xml = set_spine_text(xml, title)
    write_bbf2(output, xml)
    print("Updated title, author, and spine text")

    # Persist options for next run
    save_last_options(template, title, author)
    print("Saved options to /tmp/blurb_last_create_options.json")

    print()
    print(f"Created: {output}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Create a new .blurb file from a template."
    )
    parser.add_argument("--template", required=True, help="Source template .blurb file")
    parser.add_argument("--title",    required=True, help="Book title")
    parser.add_argument("--author",   required=True, help="Book author")
    parser.add_argument("--output",   required=True, help="Output .blurb file path")
    args = parser.parse_args(argv)

    create_blurb(
        template=args.template,
        title=args.title,
        author=args.author,
        output=args.output,
    )


if __name__ == "__main__":
    main()
