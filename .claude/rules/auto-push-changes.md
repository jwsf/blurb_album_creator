# Auto-Push Code Changes to GitHub

## Rule: Commit and Push After Modifying Skills, Rules, Workflows, or Scripts

**CRITICAL**: After making changes to any of the following paths, ALWAYS commit and push to the `origin/main` branch on GitHub:

### Tracked Paths

- `.claude/rules/` — Project rules (any `.md` file)
- `.claude/skills/` — Skill definitions and scripts (`SKILL.md`, `*.py`)
- `.claude/workflows/` — Workflow definitions
- `.claude/agents/` — Agent definitions
- `.claude/settings.local.json` — Local settings
- `.gitignore` — Git ignore rules

### When This Rule Applies

After ANY of these operations on the tracked paths:
- Creating a new file
- Editing an existing file
- Deleting a file
- Renaming or moving a file

### Workflow

1. **Make the changes** as requested by the user
2. **Stage the changed files** using `git add` with specific file paths
3. **Commit** with a concise descriptive message
4. **Push** to `origin/main`

```bash
# Example
git add .claude/skills/image-batcher/batcher.py .claude/skills/image-batcher/SKILL.md
git commit -m "Update image batcher with new feature"
git push
```

### Commit Message Format

- Use imperative mood ("Add feature" not "Added feature")
- Keep the first line under 72 characters
- Add a blank line and description body for non-trivial changes
- Always include the Co-Authored-By trailer

### What NOT to Push

- `inputs/` — Source images (gitignored)
- `outputs/` — Generated .blurb files and PDFs (gitignored)
- `samples/*.blurb` and `samples/*.pdf` — Large sample albums (gitignored)
- `.DS_Store` — macOS metadata (gitignored)

### Override

The user can explicitly say:
- "don't push" or "don't commit"
- "commit but don't push"
- "I'll push later"

In those cases, respect their preference.

### Rationale

The GitHub repository at `github.com/jwsf/blurb_album_creator` is the source of truth for all code, skills, and configuration. Keeping it up to date ensures changes are preserved and versioned.
