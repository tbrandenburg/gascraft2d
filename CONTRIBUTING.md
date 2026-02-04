# Contributing

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
pre-commit install
```

## Quality gates

Before opening a PR, run:

```bash
ruff check .
black --check .
mypy src/gascraft2d/core.py
pytest
```

## Documentation

Build docs locally:

```bash
sphinx-build -b html docs/source docs/_build/html
```
