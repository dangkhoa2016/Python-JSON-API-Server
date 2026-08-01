# Contributing

Thank you for considering contributing to this project.

## Development Setup

```bash
git clone https://github.com/dangkhoa2016/Python-JSON-API-Server.git
cd Python-JSON-API-Server
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest
pytest -v              # verbose
pytest -k "test_name"  # specific test
```

## Code Style

- Follow PEP 8
- Use type hints on all function signatures
- Keep functions focused and small
- Write docstrings for public interfaces

## Pull Request Process

1. Fork the repo and create a branch from `main`
2. Add tests for any new functionality
3. Ensure all tests pass (`pytest`)
4. Update documentation if needed
5. Submit a pull request with a clear description

## Reporting Bugs

Open an issue with:
- Steps to reproduce
- Expected vs actual behavior
- Python version and OS
