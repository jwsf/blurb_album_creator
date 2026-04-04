# Blurb Integrity Check — Validation Steps

1. **SQLite validity** — database isn't corrupt
2. **Required tables** — `Files` and `ArchiveVersion` exist
3. **Archive version** — version is 4
4. **Required files** — `bbf2.xml`, `project_settings.json`, `media_registry.xml` present
5. **bbf2.xml structure** — parses as valid XML with `<book>` root
6. **Metadata** — title is non-empty (error); author is non-empty (warning)
7. **Protected elements** — `<masterpage>` and all required `<cover>` types present
8. **Page numbering** — content pages numbered sequentially without gaps or duplicates
9. **Image references** — `src` is filename-only, images exist in archive, `autolayout="fill"` set
10. **Media registry** — all image GUIDs used in pages have registry entries
11. **File sizes** — declared sizes match actual blob sizes
12. **Forbidden file types** — no video, RAW, GIF, or HEIC in archive
13. **Spine text** — spine contains the book title on all cover types
