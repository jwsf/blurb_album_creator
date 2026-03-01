# Workflows

Workflows automate common sequences of tasks in your development process.

## Creating a Workflow

Create a new `.md` file in this directory:

```markdown
---
name: workflow-name
description: What this workflow does
trigger: manual | on_commit | on_pr | schedule
---

# Workflow Instructions

This workflow [describes purpose].

## Steps

1. First action
2. Second action
3. Final action
```

## Workflow Example

```markdown
---
name: pre-release
description: Prepares the codebase for a new release
trigger: manual
---

# Pre-Release Workflow

## Tasks

1. Run full test suite
2. Update version numbers
3. Generate changelog
4. Build documentation
5. Create release branch
6. Tag the release

## Validation

Ensure all tests pass before proceeding with the release.
```

## Trigger Types

- **manual** - User invokes explicitly
- **on_commit** - Runs after commits
- **on_pr** - Runs when PR is created
- **schedule** - Runs on a schedule (if supported)
