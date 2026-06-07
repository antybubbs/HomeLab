import base64
import os
import secrets

print('SECRET_KEY=' + secrets.token_urlsafe(64))
print('ENCRYPTION_KEY=' + base64.urlsafe_b64encode(os.urandom(32)).decode())
