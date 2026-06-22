#!/bin/sh
set -eu

mkdir -p /app/data /app/uploads
chown -R homelab:homelab /app/data /app/uploads

SECRETS_FILE="/app/data/.runtime.env"

generate_secret_key() {
    python -c "import secrets; print(secrets.token_urlsafe(64))"
}

generate_encryption_key() {
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
}

if [ ! -f "$SECRETS_FILE" ]; then
    echo "Creating first-run HomeLab secrets..."

    cat > "$SECRETS_FILE" <<EOF
SECRET_KEY=$(generate_secret_key)
ENCRYPTION_KEY=$(generate_encryption_key)
EOF

    chown homelab:homelab "$SECRETS_FILE"
    chmod 600 "$SECRETS_FILE"
fi

set -a
. "$SECRETS_FILE"
set +a

export SECRET_KEY
export ENCRYPTION_KEY

echo "Starting HomeLab with ENCRYPTION_KEY length: ${#ENCRYPTION_KEY}"

echo "Running database migrations..."
gosu homelab python /app/scripts/migrate_sqlite.py

exec gosu homelab "$@"
