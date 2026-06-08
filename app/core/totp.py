import base64
import hmac
import secrets
import struct
import time
from hashlib import sha1
from urllib.parse import quote
from app.core.config import get_settings
from app.core.security import decrypt_secret, encrypt_secret


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def encrypted_totp_secret(secret: str) -> str:
    return encrypt_secret(secret)


def decrypted_totp_secret(encrypted_secret: str | None) -> str:
    return decrypt_secret(encrypted_secret)


def hotp(secret: str, counter: int, digits: int = 6) -> str:
    padding = "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode((secret + padding).upper())
    digest = hmac.new(key, struct.pack(">Q", counter), sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code % (10 ** digits)).zfill(digits)


def verify_totp(secret: str, code: str, window: int = 1) -> bool:
    if not code or not code.strip().isdigit():
        return False
    counter = int(time.time() // 30)
    submitted = code.strip()
    for offset in range(-window, window + 1):
        if hmac.compare_digest(hotp(secret, counter + offset), submitted):
            return True
    return False


def provisioning_uri(email: str, secret: str) -> str:
    issuer = get_settings().app_name
    label = f"{issuer}:{email}"
    return (
        "otpauth://totp/"
        f"{quote(label)}?secret={quote(secret)}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"
    )
