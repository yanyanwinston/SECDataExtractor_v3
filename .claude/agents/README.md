# Claude Code Custom Agents

This directory will contain custom subagent definitions for specialized tasks.

## Future Agents (Planned)

### Trading Agent
- Analyze market data
- Execute trading strategies
- Monitor positions

### Testing Agent
- Run comprehensive tests
- Generate test reports
- Fix failing tests

### Deployment Agent
- Handle production deployments
- Run pre-deployment checks
- Monitor deployment status

### Documentation Agent
- Generate API documentation
- Update README files
- Create implementation guides

## Agent Structure (Template)

```markdown
# Agent Name

## Purpose
What this agent specializes in

## Capabilities
- Specific task 1
- Specific task 2
- Specific task 3

## Tools Available
- List of tools this agent can use
- API endpoints it can access
- File types it can work with

## Usage Patterns
Common scenarios where this agent would be invoked
```

## Integration with Commands

Agents can be invoked by custom commands:
- `/test` command could use Testing Agent
- `/deploy` command could use Deployment Agent
- `/docs` command could use Documentation Agent