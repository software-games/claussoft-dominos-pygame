# Copilot Instructions for claussoft-dominos

## Development Tools

### uv
Use [uv](https://docs.astral.sh/uv/) as the Python package manager and project runner.

- Run scripts directly: `uv run script.py`
- Install dependencies: `uv add <package>`
- Run tools: `uv tool run ruff check .`

### PEP 723 – Inline Script Metadata
All standalone Python scripts should declare their dependencies and Python version
using [PEP 723](https://peps.python.org/pep-0723/) inline script metadata so they
can be run directly with `uv run`:

```python
#!/usr/bin/env -S uv run --script

# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "some-package",
# ]
# ///
```

### pre-commit
Use [pre-commit](https://pre-commit.com/) to enforce code quality before each commit.

- Install hooks: `pre-commit install`
- Run manually: `pre-commit run --all-files`
- Configuration lives in `.pre-commit-config.yaml`

When adding new linting or formatting hooks, add them to `.pre-commit-config.yaml`
rather than running tools ad-hoc.

### pytest
Use [pytest](https://docs.pytest.org/) for all tests.

- Run tests: `uv run pytest` or `python -m pytest`
- Tests live in the `tests/` directory
- New features and bug fixes should include tests in `tests/`
- Test files are named `test_*.py`
