# Skills

Skills are custom slash commands that extend Claude's capabilities.

## Creating a Skill

Create a new `.md` file in this directory with frontmatter configuration:

```markdown
---
name: example
description: Short description of what this skill does
---

# Instructions for Claude

When this skill is invoked, follow these steps:

1. First step
2. Second step
3. etc.
```

## Skill Example

```markdown
---
name: test
description: Run project tests with coverage
---

# Test Runner Skill

When invoked, execute the following:

1. Run the project's test suite
2. Generate a coverage report
3. Summarize the results
4. If tests fail, highlight the failing tests
```

## Usage

Invoke skills with: `/skill-name` or `/skill-name arg1 arg2`
