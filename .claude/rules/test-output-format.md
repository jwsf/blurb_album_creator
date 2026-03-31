# Test Output Reporting Format

## Rule

When running automated tests in this repository, always report per-test result lines and the final summary line.

When changing `.claude/skills/image/SKILL.md` or `.claude/skills/image/test_image_skill.sh`, a fresh run of the image skill tests is required before considering the change complete.

## Required Output

- Include one line per test case ending with `PASS`, `FAIL`, or `SKIP`
- Include the final summary line (for example: `Test summary: pass=21 fail=0 skip=0`)
- Do not provide only a high-level summary when per-test output is available

## Preferred Command Pattern

Use a capture-and-filter pattern so the user always sees the per-test lines:

```bash
bash .claude/skills/image/test_image_skill.sh > /tmp/tout.txt 2>&1 || true
awk '/ PASS$| FAIL$| SKIP$|^Test summary:/' /tmp/tout.txt
```

## Applies To

- `.claude/skills/image/test_image_skill.sh`
- `.claude/skills/image/SKILL.md`
- Any future test harnesses that print per-test line results

## Rationale

Per-test output makes regressions obvious, avoids hiding failures in prose summaries, and makes results easier to scan quickly.
