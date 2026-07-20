# Python JSON API Server

JSONPlaceholder-compatible REST API built with FastAPI, SQLAlchemy, and Redis.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

## Tests

```bash
pytest -v
```
