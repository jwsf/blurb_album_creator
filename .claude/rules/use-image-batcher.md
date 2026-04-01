# Use Image Batcher for Multiple Images

## Rule: Prefer /image-batcher for Multi-Image Album Work

When adding many images to a `.blurb` album, use `/image-batcher` first.

## Applies To

- 10+ images
- Directory-wide or multi-date imports
- "Add all photos/images" requests

## Exception

- 1-5 explicitly specified images can bypass batcher

## Source of Truth

Detailed policy and procedure are maintained in:

- `.claude/skills/image-batcher/SKILL.md`
- `.claude/workflows/multi-image-album.md`

That skill document defines:

- required usage conditions
- ordering guarantees
- integration flow with `/blurb`
- verification commands and expected outcomes

The workflow document defines:

- cross-skill orchestration order
- metadata preparation and batch application steps
- explicit boundary that PDF export is always manual and separate
