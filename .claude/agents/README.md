# Agents

Custom agents are specialized sub-agents that can be spawned to handle specific types of tasks.

## Creating an Agent

Create a new `.md` file in this directory:

```markdown
---
name: my-agent
description: Brief description of what this agent does
tools: [Bash, Read, Write, Edit, Grep, Glob]
---

# Agent Instructions

You are a specialized agent that [describes purpose].

## Responsibilities

- Responsibility 1
- Responsibility 2

## Approach

When invoked, you should:

1. Step 1
2. Step 2
```

## Agent Example

```markdown
---
name: doc-generator
description: Generates documentation for code files
tools: [Read, Write, Grep, Glob]
---

# Documentation Generator

You are a documentation specialist that creates comprehensive docs for code.

## Process

1. Read the specified files
2. Analyze the code structure
3. Generate markdown documentation
4. Include examples and usage patterns
```

## Usage

Agents are spawned programmatically by Claude using the Task tool with `subagent_type: "my-agent"`.
