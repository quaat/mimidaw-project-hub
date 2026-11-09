#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -e .env ]]; then echo '.env already exists; refusing to overwrite'; exit 1; fi
python3 - <<'PY'
import secrets
from pathlib import Path
password = secrets.token_urlsafe(24)
secret = secrets.token_hex(32)
Path('.env').write_text(f'HUB_ADMIN_PASSWORD={password}\nHUB_SESSION_SECRET={secret}\nHUB_PORT=8090\nHUB_BIND_IP=0.0.0.0\nHUB_MAX_UPLOAD_MB=100\nHUB_COOKIE_SECURE=0\n')
Path('.env').chmod(0o600)
print('Created .env (mode 0600). Copy your hub password from .env to your password manager:')
print(password)
PY
