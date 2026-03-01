# Protect Sample Files

## Rule: Never Modify Sample Files

**CRITICAL**: Files in the `samples/` directory and all subdirectories are READ-ONLY and must NEVER be modified, edited, or deleted.

### Protected Paths

- `samples/` - Root samples directory
- `samples/templates/` - Template .blurb files
- `samples/**/*` - All files in any subdirectory

### What This Means

**NEVER:**
- Edit files in `samples/` or subdirectories
- Write to files in `samples/` or subdirectories
- Delete files in `samples/` or subdirectories
- Move files from `samples/` or subdirectories
- Modify file contents in `samples/` or subdirectories
- Update metadata of files in `samples/` or subdirectories

**ALWAYS:**
- Read from `samples/` files (reading is allowed)
- Copy from `samples/` to other locations (copying is allowed)
- Use `samples/templates/*.blurb` as source templates (copy to `outputs/` first)

### Workflow

When working with template files:

1. ✅ **ALLOWED**: Copy template to a new location
   ```bash
   cp "samples/templates/TravelBook-StandardLandscape.blurb" "outputs/My Book.blurb"
   ```

2. ✅ **ALLOWED**: Read and inspect sample files
   ```bash
   sqlite3 "samples/templates/TravelBook-StandardLandscape.blurb" "SELECT * FROM Files;"
   ```

3. ❌ **FORBIDDEN**: Modify sample files directly
   ```bash
   # NEVER DO THIS:
   sqlite3 "samples/templates/TravelBook-StandardLandscape.blurb" "UPDATE Files SET ..."
   ```

4. ❌ **FORBIDDEN**: Edit sample files with Edit/Write tools
   ```bash
   # NEVER DO THIS:
   Edit(file_path="samples/templates/something.blurb", ...)
   Write(file_path="samples/anything", ...)
   ```

### Rationale

Sample files are:
- Reference templates that must remain pristine
- Source files for creating new projects
- Shared resources that should not be corrupted
- Known-good configurations for testing and validation

Modifying sample files would:
- Corrupt the templates for future use
- Make it impossible to create new books from clean templates
- Break reproducibility of the workflow
- Require re-downloading or restoring samples

### Response Template

If asked to modify a file in `samples/`:

```
I cannot modify files in the samples/ directory. These are protected template files that must remain unchanged.

Instead, I can:
1. Copy the template to outputs/ and modify the copy
2. Create a new file based on the template
3. Read and inspect the sample file without changing it

Would you like me to copy the file to a new location and make the changes there?
```

## Implementation

When any tool receives a file path parameter:
1. Check if the path starts with `samples/` or contains `/samples/`
2. If the operation is Edit, Write, Delete, or any modification operation, REFUSE
3. If the operation is Read, Glob, or copy-to-elsewhere, ALLOW
4. Explain to the user why the operation was refused and suggest the copy-first workflow
