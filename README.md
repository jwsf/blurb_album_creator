# Blurb Album Creator

> This software is not created, supported, or endorsed by Blurb in any way.

Rapidly creates [Blurb Bookwright](https://www.blurb.com/bookwright) photo albums from date-organised image folders, ready for subsequent editing and publishing using Blurb's official services. Images are batched by date and location, matched to orientation-aware template layouts, and written directly into a `.blurb` file ready to open in Bookwright.

## How It Works

`.blurb` files are SQLite databases. This toolset reads and writes them directly — copying a template, embedding images, updating page layouts, and validating the result — without needing Bookwright to be open.

## Prerequisites

- **Python 3** — `python3`
- **exiftool** — `brew install exiftool` — image metadata extraction
- **sips** — built-in on macOS — image dimensions and HEIC conversion
- **sqlite3** — built-in on macOS — `.blurb` file access

## Directory Structure

```
inputs/                        Source images, organised by date folder
  2021-07-02 Florida/
    photo1.jpg
    photo2.jpg
  2021-07-03 Florida/
    ...

outputs/                       Generated .blurb files (gitignored)

references/
  templates/                   Read-only source templates (not included — download from blurb.com/templates)
    FamilyBook-LargeLandscape.blurb
    ...

.claude/
  skills/
    blurb/                     Create, validate, and add images to .blurb files
    image-batcher/             Batch images from date folders
    image-metadata-utils/      Extract and update image metadata
    blurb-to-pdf/              Convert .blurb files to PDF
  workflows/
    multi-image-album.md       End-to-end album creation workflow
  rules/                       Always-active project rules
```

## Typical Workflow

Full details in [`.claude/workflows/multi-image-album.md`](.claude/workflows/multi-image-album.md).

**1. Organise images into date folders under `inputs/`**

```
inputs/
  2021-07-02 Florida/
  2021-07-03 Florida/
```

**2. Initialise the image batcher**

```bash
python3 .claude/skills/image-batcher/batcher.py init inputs/
```

**3. Create a new album from a template**

```bash
python3 .claude/skills/blurb/create_blurb.py \
  --template "references/templates/FamilyBook-StandardLandscape.blurb" \
  --title "2021 Photos" \
  --author "Your Name" \
  --output "outputs/2021 Photos 2026-04-04 08:43.blurb"
```

**4. Apply batches to the album**

```bash
python3 .claude/skills/blurb/add_batches_to_blurb.py "outputs/2021 Photos 2026-04-04 08:43.blurb"
```

**5. Validate the result**

```bash
python3 .claude/skills/blurb/check_blurb.py "outputs/2021 Photos 2026-04-04 08:43.blurb"
```

**6. Open in Bookwright** — review layouts, adjust, then order via Blurb.

> PDF export is always a separate manual step — see [`blurb-to-pdf`](.claude/skills/blurb-to-pdf/SKILL.md).

## Skills Reference

| Skill | Script | Purpose |
|---|---|---|
| **blurb** | `create_blurb.py` | Create a new `.blurb` file from a template |
| **blurb** | `add_batches_to_blurb.py` | Add batched images to an existing `.blurb` file |
| **blurb** | `check_blurb.py` | Validate a `.blurb` file against 13 integrity checks |
| **image-batcher** | `batcher.py` | Batch images by date/location from `inputs/` |
| **image-metadata-utils** | `image_metadata_utils.py` | Extract and update image metadata (captions, locations) |
| **blurb-to-pdf** | `blurb_to_pdf.py` | Convert a `.blurb` file to PDF |

## Validation

`check_blurb.py` validates a `.blurb` file against 13 checks covering SQLite integrity, required files and structure, metadata, page numbering, image references, media registry consistency, forbidden file types, and spine text. Exits 0 if all files pass (zero errors).

```bash
# Single file
python3 .claude/skills/blurb/check_blurb.py "outputs/My Album.blurb"

# All files in a directory
python3 .claude/skills/blurb/check_blurb.py outputs/*.blurb
```

See [`.claude/skills/blurb/check_blurb_validation_steps.md`](.claude/skills/blurb/check_blurb_validation_steps.md) for the full list of checks.

## Running Tests

Each skill has a test script:

```bash
bash .claude/skills/blurb/test_check_blurb.sh
bash .claude/skills/blurb/test_blurb_skill.sh
bash .claude/skills/image-batcher/test_image_batcher.sh
bash .claude/skills/image-metadata-utils/test_image_metadata_utils.sh
```

## Claude Code Integration

This repo includes a [`CLAUDE.md`](CLAUDE.md) that instructs Claude Code to read all rules, skills, and workflows at the start of every session. When working with Claude Code in this project, it will automatically follow the documented conventions and use the existing skill scripts rather than writing one-off code.

---

*Blurb and Bookwright are registered trademarks of Blurb, Inc. This project is an independent tool and is not affiliated with, created by, supported by, or endorsed by Blurb, Inc.*
