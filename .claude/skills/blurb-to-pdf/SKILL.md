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
- `reportlab` and `pillow` (Pillow 9.2+, for color-emoji glyph rendering
  via its `embedded_color` support)
- `sqlite3` CLI (available by default on macOS)
- macOS with `/System/Library/Fonts/Apple Color Emoji.ttc` present, for
  emoji rendering specifically (everything else works without it)

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
- Image containers with transforms and clipping, including a container
  that's itself rotated a few degrees (a tilted "scrapbook-style" photo,
  drop-shadow/keyline border and all) -- separate from `<image rotate=...>`,
  which rotates the picture *content* inside an otherwise-rectangular,
  unrotated container
- A container's own visible border/frame shape (stroked outline and/or
  filled background), when the archive marks it shown
- Text containers with alignment, rotation, and underline -- including
  getting the underline's extent right at a run boundary. Word-wrap
  injects a space between two adjacent, differently-styled runs (e.g.
  plain "...to the " followed by underlined "Scar Cafe,") to preserve
  the real gap between them; that boundary space is never underlined
  even when the run it's prepended to is, but an ordinary space between
  two words already inside the SAME underlined run (e.g. "Daniel Hill,")
  keeps its underline like any other character in it
- Per-paragraph line spacing from its own inline `line-height:NN%` style
  (falling back to 108%, the dominant value in practice, for a paragraph
  with none) -- these vary per paragraph (108/115/116% all appear in the
  same book) and differ substantially from a single flat assumption.
  Getting this right matters far more than it sounds: an inflated line
  height doesn't just add visual gap, it makes every multi-line paragraph
  measure taller than Bookwright's own layout, which cascades into
  spurious overflow, mistimed auto-shrinking, and text colliding with
  whatever sits below it
- A paragraph whose only content is a zero-width space (`​`) --
  Bookwright's own way of authoring a deliberate blank line between two
  paragraphs -- still takes up a blank line of vertical space rather than
  collapsing away
- Emoji and other pictographic characters missing from Arial (stopwatch,
  walking figure, checkmark, colored circles, etc.), rendered as small
  inline color images -- Pillow rendering Apple Color Emoji glyphs
  directly, cropped and cached per character, sized to the surrounding
  line's font size. This is a genuine raster image drawn inline, not a
  font glyph -- reportlab can't draw color bitmap (sbix/CBDT) glyphs as
  text at all, which is what every emoji font actually is
- Page background colors
- PDF metadata from book title/author
- Containers drawn in their original document order, matching Bookwright's
  paint order -- e.g. a caption meant to sit on top of a decorative
  background image renders fully intact, on top of it, exactly as designed
- Rounding-sized overlaps between a text box and any other container
  (image OR text) on the page -- whether it comes before or after in
  document order -- are resolved by shrinking the text's font just
  enough for its actual rendered ink to clear it, never by clipping
  either element and never by moving or resizing the other container.
  Document order only decides paint order (what's drawn on top); it's
  irrelevant to whether an overlap needs fixing -- a heading positioned
  in the gap above a photo grid (images earlier in the document) can
  overflow into it from font-metric wrapping differences just as easily
  as a caption can overflow into a later image, and both get the same
  treatment. Applies to unrotated text of any (uniform per-line)
  alignment -- left, center, or right all reduce to a computable ink
  extent once each line's own alignment is taken into account -- and
  only when shrinking could actually help (the text's own top must
  start above the obstacle's top -- shrinking pulls the bottom of
  top-anchored text back up, it can never move the top, so an overlap
  that starts right at the text's own top edge -- an intentional
  caption-over-background-image design, not a rounding accident -- is
  left alone rather than shrunk all the way to the floor for no benefit)
- A text container's own declared height is *not* a clipping or shrinking
  boundary -- Bookwright's own output shows text overflow past the bottom
  of its box, completely unshrunk and unclipped, whenever nothing else
  sits there. Text is only ever shrunk to avoid an actual collision with
  another container or the page's own edge, never merely for exceeding
  its own box
- True transparency for images with an alpha channel (e.g. clipart PNGs),
  preserved via a PDF soft mask rather than flattened onto a solid color

## What Is Excluded

- Inside cover pages from `masterpage`
- Pure spine-only elements

## Known Limitations

- Font metrics are close to, but not pixel-identical with, Bookwright's
  own text engine. Most paragraphs wrap the same, but a string sized to
  fit its box within roughly a point (e.g. a heading exactly as wide as
  its container) can wrap one word early or late compared to Bookwright.
  Seen on two short bold headings in one real book, both within ~1pt of
  their box's width -- not worth chasing with a global fudge factor on
  the evidence of two edge cases
- The emoji fallback font is hardcoded to macOS's Apple Color Emoji
  (`/System/Library/Fonts/Apple Color Emoji.ttc`) and a fixed set of
  Unicode ranges (Misc Technical, Misc Symbols & Dingbats, Misc Symbols
  and Arrows, and the main emoji/supplemental-pictograph planes). On a
  non-macOS system, or for a character outside those ranges, it falls
  back to no glyph at all rather than a tofu box -- silently blank,
  not visibly broken
- A container border/frame's visual weight can look different from
  Bookwright's own render at low DPI due to anti-aliasing differences
  between renderers (checked via precise pixel measurement rather than
  eyeballing, on one book, and found to be within a pixel of a match) --
  not a confirmed stroke-width bug, so not "fixed" by guessing a scale
  correction
- **`pdftoppm`/poppler-based PDF previewers can misrender this output**:
  specifically, embedding-TTF text (Arial) drawn anywhere on a page that
  also has a clipped image can render with part of that text missing,
  even in a region far from the image, and even with no clipping on the
  text at all. The generated PDF itself is correct -- verified via its
  raw content stream and via macOS Quick Look (Quartz/CoreGraphics,
  which renders it correctly). Don't diagnose "text cut off" findings
  from a `pdftoppm` render alone; cross-check with `qlmanage -t` (or
  another non-poppler renderer) before concluding it's a real bug
