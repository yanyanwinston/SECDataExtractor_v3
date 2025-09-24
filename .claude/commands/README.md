# Claude Code Custom Commands

This directory contains custom command definitions for Claude Code.

## Available Commands

### `/commit` - Smart Git Commit
Analyzes staged changes and creates conventional commit messages automatically.
- **File**: `commit.md`
- **Usage**: Type `/commit` after staging your changes
- **Features**: Conventional commits, automatic type detection, Claude attribution

## Adding New Commands

To add a new custom command:

1. Create a new `.md` file in this directory
2. Name it after your command (e.g., `deploy.md` for `/deploy`)
3. Follow this structure:

```markdown
# /command-name - Description

## Description
What the command does

## Usage
How to use it

## Behavior
Step-by-step what happens

## Examples
Example usage and outputs
```

4. Claude Code will automatically recognize the new command

## Command Guidelines

- **Keep commands focused**: One clear purpose per command
- **Use conventional names**: Follow common CLI patterns
- **Document thoroughly**: Include examples and edge cases
- **Handle errors gracefully**: Plan for failure scenarios
- **Be consistent**: Follow the same format for all commands