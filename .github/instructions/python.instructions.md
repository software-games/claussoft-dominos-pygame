---
applyTo: "**/*.py"
---

# Python Coding Conventions

## Naming Conventions

- Use snake_case for variables and functions
- Use PascalCase for class names
- Use UPPERCASE for constants

## Code Style

- Follow PEP 8 style guidelines
- Limit line length to 88 characters (ruff format standard)
- Use type hints for function signatures
- In _PYSCRIPT_CODE blocks, use type hints for function signatures
- In scripts/**/*.py, use the `uv run --script` shebang and include PEP 723 Inline Script Metadata (/// script) for dependencies and Python version requirements

## Best Practices

- Python code will be linted and formatted with ruff check and ruff format
- Ruff check and ruff format will be run as pre-commit hooks to ensure code quality before commits
- Read the ruff configuration from pyproject.toml
- Use assignment expressions (the walrus operator) for concise code when appropriate
- Use dict, list, and set comprehensions for simple transformations
- Avoid using mutable default arguments in functions
- Use meaningful variable and function names
- Avoid string concatenation with the + operator
- Prefer f-strings for string formatting
- Use context managers (with statements) for resource management

```python
# Avoid
file = open('data.txt')
content = file.read()
file.close()

# Prefer
with open('data.txt') as file:
    content = file.read()
```
