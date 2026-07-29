#!/usr/bin/env bash
set -eu

IMAGE="${1:-python-json-api-server:smoke}"
CONTAINER_NAME="python-json-api-server-smoke"
VOLUME_NAME="python-json-api-server-smoke-data"
NETWORK_NAME="python-json-api-server-smoke-net"

cleanup() {
  docker rm --force --volumes "$CONTAINER_NAME" >/dev/null 2>&1 || true
  docker volume rm --force "$VOLUME_NAME" >/dev/null 2>&1 || true
  docker network rm "$NETWORK_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "Building image $IMAGE..."
docker build --quiet -t "$IMAGE" .

docker network create "$NETWORK_NAME" >/dev/null

echo "Starting container..."
docker run \
  --name "$CONTAINER_NAME" \
  --network "$NETWORK_NAME" \
  -e ADMIN_KEY=smoke-test-admin-key \
  -e DB_PATH=/app/storage/data.db \
  -v "$VOLUME_NAME:/app/storage" \
  -d \
  "$IMAGE" >/dev/null

DEADLINE=$(( $(date +%s) + 30 ))
HEALTHY=false

while [ "$(date +%s)" -lt "$DEADLINE" ]; do
  if docker exec "$CONTAINER_NAME" sh -c "
    python -c 'import urllib.request, json; resp = urllib.request.urlopen(\"http://localhost:3000/health\"); data = json.loads(resp.read()); exit(0 if data.get(\"status\") == \"ok\" else 1)'
  " >/dev/null 2>&1; then
    HEALTHY=true
    break
  fi
  sleep 1
done

if [ "$HEALTHY" != true ]; then
  echo "FAIL: Container never became healthy within 30 seconds."
  docker logs "$CONTAINER_NAME"
  exit 1
fi

echo "Container is healthy."
