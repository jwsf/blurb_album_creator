# Use Image Batcher for Multiple Images

## Rule: Always Use /image-batcher When Adding Multiple Images

**CRITICAL**: When adding multiple images to a .blurb file, ALWAYS use the `/image-batcher` skill to organize and batch the images before adding them to the album.

## When This Rule Applies

### ALWAYS Use Image Batcher:
- Adding 10+ images to a blurb file
- Adding all images from a directory
- Adding images from multiple date folders
- Creating a new album with many images
- User says "add all photos" or "add all images"

### CAN Skip Image Batcher:
- Adding 1-5 specific images (already a batch)
- Adding a single image
- User specifies exact images to add (e.g., "add these 3 photos")

## Order Preservation (Mandatory)

**CRITICAL**: The image batcher must NEVER alter the order of photos. Images always appear in batches in the same order they were found (sorted by filename/path). This applies to ALL modes:

- **Date-folder mode**: Images within each date folder retain their filename sort order across all batches.
- **Flat-directory mode**: Images retain their recursive filename sort order; grouping by filename commonality does not reorder them.
- **No shuffling, no random reordering, no orientation-based reordering.**

The user's chosen filenames and directory structure define the canonical order. Batching only decides where to *split* the sequence — it never rearranges it.

## Why Use Image Batcher

1. **Efficient organization**: Groups images into optimal batches of 1-5
2. **Date preservation**: Keeps multi-image dates together
3. **Smart combining**: Merges single-image dates to avoid isolated pages
4. **Optimal layouts**: Matches batch sizes to available template pages
5. **Progress tracking**: Can process large collections incrementally

## Workflow

### Standard Multi-Image Workflow

```bash
# 1. Initialize image batcher
python3 .claude/skills/image-batcher/batcher.py init inputs/

# 2. Create/prepare blurb file
cp "samples/templates/TravelBook-StandardLandscape.blurb" "outputs/Album.blurb"
# Set title and author...

# 3. Process all batches
# Use batch processing script or process one batch at a time
python3 /path/to/batch_processor.py "outputs/Album.blurb"

# Result: Efficiently organized album with optimal page layouts
```

### Benefits Over Bulk Addition

**Without Image Batcher (Old Way):**
```
- 59 images → analyze template → group → add all at once
- No date organization
- Harder to track progress
- All-or-nothing approach
```

**With Image Batcher (Correct Way):**
```
- 59 images → 14 intelligent batches
- Date organization preserved
- Single-image dates combined
- Can process incrementally
- Clear progress tracking
```

## Implementation Requirements

When you detect a request to add multiple images:

1. **Check if image-batcher is initialized:**
   ```bash
   if [ ! -f /tmp/image_batcher_state.json ]; then
     echo "Initializing image batcher..."
     python3 .claude/skills/image-batcher/batcher.py init inputs/
   fi
   ```

2. **Use batches to add images:**
   - Process one batch at a time
   - Match batch size to template pages
   - Track progress through batches
   - Show summary at completion

3. **Report results:**
   ```
   ✅ Added 59 images in 14 pages
      - 13 date-specific batches
      - 1 multi-date batch (combining 3 single-image dates)
      - Batch sizes: 5, 5, 2, 2, 5, 5, 5, 5, 5, 4, 5, 4, 4, 3
   ```

## Example Scenarios

### Scenario 1: Create New Album with All Photos

**User request:** "Create a new blurb file with all photos"

**Correct approach:**
```
1. Initialize image-batcher: scan inputs/ directory
2. Create new blurb file from template
3. Set title and author
4. Process all batches from image-batcher
5. Report: X images added in Y pages
```

**Incorrect approach:**
```
❌ Don't: Scan inputs/ and add all images directly without batching
```

### Scenario 2: Add Photos to Existing Album

**User request:** "Add all new photos to my existing album"

**Correct approach:**
```
1. Initialize image-batcher: scan inputs/ directory
2. Load existing blurb file
3. Process all batches from image-batcher
4. Append new pages with batched images
5. Report: X images added in Y new pages
```

### Scenario 3: Small Specific Set (Exception)

**User request:** "Add these 3 photos: img1.jpg, img2.jpg, img3.jpg"

**Correct approach:**
```
Can skip image-batcher for 1-5 specific images.
Use the batch addition method directly with the 3 images.
```

## Integration with /blurb Skill

The `/blurb` skill's batch addition methods (Section 5d and 5c) should:
- Accept batch data from image-batcher
- Match batch sizes to template pages
- Fill all containers in the selected template
- Track which batches have been processed

## Error Prevention

**DON'T:**
- ❌ Process 50+ images without using image-batcher
- ❌ Create one page per image when batching is possible
- ❌ Ignore date organization from folder structure
- ❌ Mix single-image dates with multi-image dates in batches
- ❌ Shuffle, randomize, or reorder images (order must always be preserved)

**DO:**
- ✅ Always initialize image-batcher for 10+ images
- ✅ Use batch data to guide page creation
- ✅ Preserve date organization from image-batcher
- ✅ Preserve filename sort order within every batch
- ✅ Report batch statistics to user

## Verification

After adding images, verify the organization:
```bash
# Check batch statistics
python3 .claude/skills/image-batcher/batcher.py status

# Expected output shows:
# - Total batches processed
# - Images per batch
# - Date organization preserved
# - Multi-date batches identified
```

## Response Template

When user requests adding multiple images:

```
I'll use the image-batcher skill to organize your images efficiently.

[Initialize image-batcher]
Found X images in Y date folders
Created Z batches (W batches combine single-image dates)

[Process batches]
Adding images to album...
[Progress updates]

✅ Added X images in Z pages
   - Date organization preserved
   - Single-image dates combined for efficiency
```

## Rationale

The image-batcher skill provides:
1. **Better organization**: Date-based grouping with smart single-image combining
2. **Optimal layouts**: Batch sizes match available template pages (1-5 containers)
3. **Efficiency**: Fewer pages, better use of space
4. **Maintainability**: Clear batch structure makes it easy to track and modify
5. **User experience**: Progress tracking and meaningful summaries

Without image-batcher:
- Images processed without date context
- No optimization for single-image dates
- Harder to create varied, efficient page layouts
- No built-in progress tracking

## Summary

**Golden Rule**: When adding 10+ images to a blurb file, ALWAYS:
1. Initialize `/image-batcher` to scan and batch images
2. Use the batch data to guide page creation
3. Process batches sequentially or all at once
4. Report batch statistics to user

This ensures efficient, well-organized albums with optimal page layouts.
