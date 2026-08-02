#!/usr/bin/env bash
set -e

CONTAINER="${1:-python-json-api-server}"
DB="${2:-/app/storage/data.db}"

echo "[Inspect] Copying scripts to container '$CONTAINER'..."
docker cp "$(dirname "$0")/inspect.sh" "$CONTAINER:/tmp/inspect.sh"
docker cp "$(dirname "$0")/inspect-queries.sql" "$CONTAINER:/tmp/inspect-queries.sql"

echo "[Inspect] Installing sqlite3 CLI..."
docker exec -u 0 "$CONTAINER" sh -c "apk add --no-cache sqlite >/dev/null 2>&1"

echo "[Inspect] Running inspect.sh against $DB..."
echo ""
docker exec -i "$CONTAINER" sh -c "sh /tmp/inspect.sh '$DB'"
