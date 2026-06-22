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
    echo "Initialising persistent HomeLab secrets..."

    # v0.16 (yes, there was once a time) and earlier supplied these values through Compose's .env file. (LOL, right?)
    # Preserve them on the first v0.18 start so existing encrypted data (ha ha ha, help us)
    # sessions remain valid. Generate only values that were not supplied. (duh)
    # Again, this is a one-time operation. After the first start, the secrets file is used. (we hope)
    # Lord help us if we ever need to change this logic again.

    PERSISTED_SECRET_KEY="${SECRET_KEY:-}"
    PERSISTED_ENCRYPTION_KEY="${ENCRYPTION_KEY:-}"

    if [ -z "$PERSISTED_SECRET_KEY" ]; then
        PERSISTED_SECRET_KEY="$(generate_secret_key)"
    fi

    if [ -z "$PERSISTED_ENCRYPTION_KEY" ]; then
        PERSISTED_ENCRYPTION_KEY="$(generate_encryption_key)"
    fi

    cat > "$SECRETS_FILE" <<EOF
SECRET_KEY=$PERSISTED_SECRET_KEY
ENCRYPTION_KEY=$PERSISTED_ENCRYPTION_KEY
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
