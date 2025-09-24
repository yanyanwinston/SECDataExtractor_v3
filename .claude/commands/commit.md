# /commit - Smart Git Commit Command

## Description
Analyzes staged git changes and creates a conventional commit message, then commits the changes.

## Usage
```
/commit
```

## Behavior
1. **Check staged changes**: Run `git status` and `git diff --staged`
2. **Analyze changes**: Determine commit type based on:
   - New files: `feat` or `chore`
   - Bug fixes: `fix`
   - Documentation: `docs`
   - Tests: `test`
   - Refactoring: `refactor`
   - Configuration: `chore`
3. **Generate message**: Create conventional commit format
4. **Execute commit**: Commit with generated message + Claude attribution

## Commit Message Format
```
type(scope): description

[optional body]

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>
```

## Examples
- `feat(stop-loss): add automatic position protection`
- `fix(api): handle connection timeout errors`
- `docs: update file organization policies`
- `test: add unit tests for stop loss manager`
- `refactor: extract calculate_stop_price function`

## Error Handling
- No staged changes: Prompt user to stage files first
- Merge conflicts: Abort and show conflict files
- Large changes: Ask for confirmation before committing