#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.demo.yml"

cd "$PROJECT_DIR"

if [ ! -f "$SCRIPT_DIR/seed/homelab.db" ]; then
    echo "Demo seed database is missing: $SCRIPT_DIR/seed/homelab.db" >&2
    exit 1
fi

echo "Stopping the public demo..."
docker compose -f "$COMPOSE_FILE" stop homelab
restart_required=1
trap 'if [ "${restart_required:-0}" = "1" ]; then docker compose -f "$COMPOSE_FILE" up -d homelab; fi' EXIT INT TERM

echo "Restoring the demo database and uploads..."
docker compose -f "$COMPOSE_FILE" run --rm --no-deps --entrypoint sh homelab -c '
    set -eu
    test -f /app/demo-seed/homelab.db
    cp /app/demo-seed/homelab.db /app/data/homelab.db.reset
    chown homelab:homelab /app/data/homelab.db.reset
    chmod 600 /app/data/homelab.db.reset
    mv /app/data/homelab.db.reset /app/data/homelab.db
    rm -f /app/data/homelab.db-wal /app/data/homelab.db-shm
    find /app/uploads -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
    if [ -d /app/demo-seed/uploads ]; then
        cp -a /app/demo-seed/uploads/. /app/uploads/
    fi
    chown -R homelab:homelab /app/uploads
    printf "%s-%s\n" "$(date +%s)" "$$" > /app/data/.demo-generation
    chown homelab:homelab /app/data/.demo-generation
'

echo "Starting the refreshed public demo..."
docker compose -f "$COMPOSE_FILE" up -d homelab
restart_required=0
trap - EXIT INT TERM
echo "Public demo reset complete."
