# Gascraft2D

Gascraft2D is a neon-styled 2D voxel sandbox game built with `pygame`.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
gascraft2d
```

You can also run with:

```bash
python -m gascraft2d
```

## Developer workflow

```bash
ruff check .
black --check .
mypy src/gascraft2d/core.py
pytest
```

## Project layout

- `src/gascraft2d/` - package source
- `tests/` - unit tests
- `docs/` - Sphinx docs
- `.github/workflows/ci.yml` - CI pipeline

## Controls

- `WASD` / Arrow keys: move
- `Space`: jump
- `LMB`: mine
- `RMB`: place block
- `E`/`I`: inventory
- `C`: crafting
- `Esc`: menu
