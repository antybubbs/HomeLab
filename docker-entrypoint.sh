#!/bin/sh
set -eu

mkdir -p /app/data /app/uploads
chown -R homelab:homelab /app/data /app/uploads

exec gosu homelab "$@"
