# Delete SQLite WAL Files with .blurb Files

## Rule

When deleting a `.blurb` file, **always also delete** the corresponding `.blurb-shm` and `.blurb-wal` files if they exist.

## Why

`.blurb` files are SQLite databases. SQLite creates two auxiliary files when using Write-Ahead Logging (WAL) mode:

- `.blurb-shm` -- shared memory file
- `.blurb-wal` -- write-ahead log

These files are left behind if the database wasn't closed cleanly (e.g., Bookwright was open). Orphaned WAL files can cause confusion or errors if a new `.blurb` file is created at the same path.

## Implementation

```bash
rm -f "path/to/file.blurb" "path/to/file.blurb-shm" "path/to/file.blurb-wal"
```

## Applies To

- Any `rm` command targeting a `.blurb` file
- Any cleanup or regeneration workflow that deletes a `.blurb` before recreating it
- Both `outputs/` and `/tmp/` locations
