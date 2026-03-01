# Recursive Image Directory Processing

## Convention

When the user references a folder or directory for image operations, **ALWAYS process all sub-folders recursively** unless explicitly told otherwise.

## Applies To

- Image metadata extraction
- Caption generation
- Photo organization
- Location analysis
- People name extraction
- Any batch image processing operations

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

## Rationale

Users typically organize photos in nested folder structures (e.g., `vacation/day1`, `vacation/day2`, `events/2024/summer`) and expect operations to process all images within the hierarchy.
