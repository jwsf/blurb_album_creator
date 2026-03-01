# Claude Code Configuration

This directory contains configuration for Claude Code extensibility features.

## Directory Structure

- **skills/** - Custom skills that extend Claude's capabilities with domain-specific commands
- **agents/** - Custom agents that can be spawned to handle specialized tasks
- **rules/** - Project-specific rules that guide Claude's behavior in this codebase
- **workflows/** - Automated workflows that chain together multiple operations

## Getting Started

### Skills
Skills are invoked with slash commands (e.g., `/my-skill`). Create a new skill by adding a file in the `skills/` directory.

### Agents
Agents are spawned using the Task tool and can work autonomously on complex tasks. Define custom agents in the `agents/` directory.

### Rules
Rules provide context and guidelines for Claude when working in this project. Add markdown files to the `rules/` directory.

### Workflows
Workflows automate common task sequences. Define them in the `workflows/` directory.

## Documentation

For more information, visit:
- Claude Code Documentation: https://docs.anthropic.com/en/docs/claude-code
- GitHub Repository: https://github.com/anthropics/claude-code
