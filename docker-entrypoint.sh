#!/bin/sh
set -eu

mkdir -p /app/data /app/uploads
chown -R keyvault:keyvault /app/data /app/uploads

exec gosu keyvault "$@"
