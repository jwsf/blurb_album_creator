# Protect Reference Files

## Rule: Never Modify Reference Files

**CRITICAL**: Files in the `references/` directory and all subdirectories are READ-ONLY and must NEVER be modified, edited, or deleted.

### Protected Paths

- `references/` - Root references directory
- `references/templates/` - Template .blurb files
- `references/**/*` - All files in any subdirectory

### What This Means

**NEVER:**
- Edit files in `references/` or subdirectories
- Write to files in `references/` or subdirectories
- Delete files in `references/` or subdirectories
- Move files from `references/` or subdirectories
- Modify file contents in `references/` or subdirectories
- Update metadata of files in `references/` or subdirectories

**ALWAYS:**
- Read from `references/` files (reading is allowed)
- Copy from `references/` to other locations (copying is allowed)
- Use `references/templates/*.blurb` as source templates (copy to `outputs/` first)

### Workflow

When working with template files:

1. ✅ **ALLOWED**: Copy template to a new location
   ```bash
   cp "references/templates/2020 empty photo album.blurb" "outputs/My Book.blurb"
   ```

2. ✅ **ALLOWED**: Read and inspect reference files
   ```bash
   sqlite3 "references/templates/2020 empty photo album.blurb" "SELECT * FROM Files;"
   ```

3. ❌ **FORBIDDEN**: Modify reference files directly
   ```bash
   # NEVER DO THIS:
   sqlite3 "references/templates/2020 empty photo album.blurb" "UPDATE Files SET ..."
   ```

4. ❌ **FORBIDDEN**: Edit reference files with Edit/Write tools
   ```bash
   # NEVER DO THIS:
   Edit(file_path="references/templates/something.blurb", ...)
   Write(file_path="references/anything", ...)
   ```

### Rationale

Reference files are:
- Reference templates that must remain pristine
- Source files for creating new projects
- Shared resources that should not be corrupted
- Known-good configurations for testing and validation

Modifying reference files would:
- Corrupt the templates for future use
- Make it impossible to create new books from clean templates
- Break reproducibility of the workflow
- Require re-downloading or restoring reference templates

### Response Template

If asked to modify a file in `references/`:

```
I cannot modify files in the references/ directory. These are protected template files that must remain unchanged.

Instead, I can:
1. Copy the template to outputs/ and modify the copy
2. Create a new file based on the template
3. Read and inspect the reference file without changing it

Would you like me to copy the file to a new location and make the changes there?
```

## Implementation

When any tool receives a file path parameter:
1. Resolve to an absolute canonical path (resolve `.`/`..` and symlinks when possible)
2. Check whether the resolved path is under the `references/` root
3. Also treat obvious textual forms (`references/...` or paths containing `/references/`) as protected
4. If path resolution is unavailable or ambiguous, default to treating the path as protected when it may target `references/`
5. If the operation is Edit, Write, Delete, or any modification operation, REFUSE
6. If the operation is Read, Glob, or copy-to-elsewhere, ALLOW
7. Explain to the user why the operation was refused and suggest the copy-first workflow
