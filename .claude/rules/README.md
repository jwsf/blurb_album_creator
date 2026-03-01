# Rules

Rules provide project-specific context and guidelines for Claude when working in this codebase.

## Creating Rules

Add markdown files to this directory. Claude will have access to these rules and follow them when working on your project.

## Rule Example

Create a file like `coding-standards.md`:

```markdown
# Coding Standards

## Language and Framework
This project uses Python 3.11+ with FastAPI.

## Code Style
- Follow PEP 8
- Use type hints for all function signatures
- Maximum line length: 100 characters
- Use Black for formatting

## Testing
- Write tests for all new features
- Maintain >80% code coverage
- Use pytest for testing

## Git Workflow
- Use conventional commits
- Create feature branches from `main`
- Require PR reviews before merging
```

## Common Rule Topics

- Coding standards and style guides
- Architecture patterns and conventions
- Testing requirements
- Documentation standards
- Deployment procedures
- Security guidelines
