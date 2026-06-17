#!/bin/sh
set -eu

mkdir -p /app/data /app/uploads
chown -R homelab:homelab /app/data /app/uploads

SECRETS_FILE="/app/data/.runtime.env"

if [ ! -f "$SECRETS_FILE" ]; then
    echo "Generating application secrets..."

    SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(64))")
    ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

    cat > "$SECRETS_FILE" << EOF
SECRET_KEY=$SECRET_KEY
ENCRYPTION_KEY=$ENCRYPTION_KEY
EOF

    chown homelab:homelab "$SECRETS_FILE"
    chmod 600 "$SECRETS_FILE"
fi

set -a
. "$SECRETS_FILE"
set +a

exec gosu homelab "$@"
