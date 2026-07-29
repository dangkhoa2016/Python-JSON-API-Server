#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

usage() {
  cat <<'EOF'
Usage: ./scripts/run.sh <command>

Database:
  db:migrate        Create missing tables from SQLAlchemy metadata
  db:seed           Seed data from JSONPlaceholder
  db:seed-settings  Seed default settings
  db:setup          Run migrate + seed + seed-settings

Server:
  start             Start uvicorn on port $PORT
  prod              Start in production mode (2 workers, no reload)
  dev               Start with auto-reload on code changes

Testing:
  test              Run tests (coverage shown via pyproject.toml addopts)
  test:watch        Run tests in watch mode
  test:coverage     Run tests + generate HTML report in htmlcov/
EOF
}

cmd_db_migrate() {
  python -m scripts.db_migrate
}

cmd_db_seed() {
  python -m scripts.db_seed
}

cmd_db_seed_settings() {
  python -m scripts.db_seed_settings
}

cmd_db_setup() {
  python -m scripts.db_setup
}

cmd_start() {
  PORT="${PORT:-3000}"
  echo "Starting server on http://localhost:$PORT"
  exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
}

cmd_prod() {
  PORT="${PORT:-3000}"
  echo "Starting production server on http://localhost:$PORT"
  exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --workers 2
}

cmd_dev() {
  PORT="${PORT:-3000}"
  echo "Starting dev server on http://localhost:$PORT (auto-reload)"
  exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --reload
}

cmd_test() {
  python -m pytest "$@"
}

cmd_test_watch() {
  python -m pytest_watch "$@"
}

cmd_test_coverage() {
  python -m pytest --cov-report=html "$@"
}

# --- main ---
command="${1:-help}"
shift || true

case "$command" in
  db:migrate)       cmd_db_migrate ;;
  db:seed)          cmd_db_seed ;;
  db:seed-settings) cmd_db_seed_settings ;;
  db:setup)         cmd_db_setup ;;
  start)            cmd_start ;;
  prod)             cmd_prod ;;
  dev)              cmd_dev ;;
  test)             cmd_test "$@" ;;
  test:watch)       cmd_test_watch "$@" ;;
  test:coverage)    cmd_test_coverage "$@" ;;
  help|--help|-h)   usage ;;
  *)
    echo "Unknown command: $command"
    echo ""
    usage
    exit 1
    ;;
esac
