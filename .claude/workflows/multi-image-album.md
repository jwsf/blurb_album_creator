---
name: multi-image-album
description: Orchestrate multi-image album ingestion using image-batcher, image-metadata-utils, and blurb, stopping before PDF export
trigger: manual
---

# Multi-Image Album Workflow

Use this workflow when creating or updating a `.blurb` album from many images.

## Scope

- Includes: batching, metadata/caption preparation, and `.blurb` updates.
- Excludes: automatic PDF conversion.
- PDF export is always a separate manual action.

## Steps

1. Initialize batch state:
```bash
python3 .claude/skills/image-batcher/batcher.py init inputs/
```

2. Prepare target `.blurb` file:
- New album: copy template to `outputs/` and set title/author.
- Existing album: verify path and create backup.

3. Prepare metadata/caption context:
```bash
python3 .claude/skills/image-metadata-utils/image_metadata_utils.py analyze-directory inputs/ outputs/image-analysis.txt
python3 .claude/skills/image-metadata-utils/image_metadata_utils.py export-metadata-csv inputs/ outputs/image-metadata.csv
```

4. Apply batches to album:
```bash
python3 .claude/skills/blurb/add_batches_to_blurb.py "outputs/Album.blurb"
```

5. Verify completion:
```bash
python3 .claude/skills/image-batcher/batcher.py status
```

## Manual PDF Step (Separate)

If the user wants a PDF, run this only after the workflow completes and only as a separate explicit step:

```bash
python3 .claude/skills/blurb-to-pdf/blurb_to_pdf.py "outputs/Album.blurb"
```
