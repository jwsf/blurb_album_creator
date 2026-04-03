# Blurb Album Creator — Claude Code Instructions

At the start of every session, before taking any action:

1. Read all files in `.claude/rules/` — these are always active
2. Read all `SKILL.md` files in `.claude/skills/*/` — know what skills and scripts exist
3. Read all files in `.claude/workflows/` — follow documented workflows
4. Read all files in `.claude/agents/` — know what agents are available

## General Principles

- Always follow the rules in `.claude/rules/`
- Always use existing scripts in `.claude/skills/` — never write inline bash/python one-offs when a skill script exists
- Always follow the workflow steps in `.claude/workflows/` for multi-step tasks
- Default source images directory: `inputs/`
- Default output directory: `outputs/`
