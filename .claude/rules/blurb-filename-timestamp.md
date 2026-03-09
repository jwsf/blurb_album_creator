# Blurb Filename Timestamp

## Rule

When generating a .blurb file, the output filename must include a timestamp in the format `YYYY-MM-DD HH:MM`.

## Example

If the book title is "My Photo Album", the output file should be:

```
outputs/My Photo Album 2026-03-08 15:30.blurb
```

## Format

```
<title> <YYYY-MM-DD HH:MM>.blurb
```

- Use the current local time at the moment of file creation
- Use 24-hour time format
- Separate date and time with a space
- Place the timestamp after the title, separated by a space

## Applies To

- Creating new .blurb files from templates
- Regenerating .blurb files
- Any workflow that produces a .blurb output file
