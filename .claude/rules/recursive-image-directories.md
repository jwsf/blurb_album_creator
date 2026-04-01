# Recursive Image Directory Processing

## Convention

When the user references a folder or directory for image operations, **ALWAYS process all sub-folders recursively** unless explicitly told otherwise.

## Applies To

- Image metadata extraction
- Caption generation
- Photo organization
- Location analysis
- People name extraction
- Generic directory-wide batch operations

## Default Behavior

When given a directory path like `inputs/vacation`:
- ✅ **DO**: Process all images in `inputs/vacation` AND all subdirectories
- ❌ **DON'T**: Process only the top-level `inputs/vacation` directory

## Implementation

When using find commands, always include `-type f` and recursive search:

```bash
# CORRECT - Recursive search
find "$dir" -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" -o -iname "*.heic" -o -iname "*.tiff" \)

# INCORRECT - Non-recursive (maxdepth 1)
find "$dir" -maxdepth 1 -type f \( -iname "*.jpg" -o -iname "*.jpeg" \)
```

When using exiftool, always include the `-r` flag for recursive processing:

```bash
# CORRECT - Recursive processing
exiftool -r "$dir"

# INCORRECT - Non-recursive
exiftool "$dir"
```

## Override

The user can explicitly request non-recursive processing by saying:
- "only this folder"
- "just the top level"
- "no subdirectories"
- "non-recursive"

## Exception: Directory-Level Location Inference

`infer_directory_location()` in the image skill intentionally uses `-maxdepth 1` when scanning a single directory for GPS peers. The purpose is to find sibling images in the *same folder* as the target image — scanning subdirectories would pull in GPS from unrelated locations. This is by design and is not a violation of this rule.

## Exception: Image Batcher Mode Semantics

`/image-batcher` has mode-specific scanning behavior that is intentionally different from this generic recursion rule:

- Date-folder mode: scans immediate date folders and images within each date folder.
- Flat-directory fallback: scans recursively when no date folders are present.

For `/image-batcher`, follow its own documented behavior in `.claude/skills/image-batcher/SKILL.md`.

## Rationale

Users typically organize photos in nested folder structures (e.g., `vacation/day1`, `vacation/day2`, `events/2024/summer`) and expect operations to process all images within the hierarchy.
