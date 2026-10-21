#!/usr/bin/env bash
# A self-contained, loopback-only demo. No existing identity provider is required.
set -euo pipefail
cd "$(dirname "$0")"
case "${1:-up}" in
  up)
    python3 - <<'PY'
import os
from pathlib import Path
import secrets
p = Path('.env.demo')
if not p.exists():
    values = {
        'PUBLIC_URL': 'http://localhost:7476', 'BOLT_ADDRESS': 'localhost:7476',
        'HTTP_PORT': '7476', 'OIDC_ISSUER_URL': 'http://localhost:9480/realms/neo4j',
        'OIDC_CLIENT_ID': 'neo4j-community-sso', 'ALLOWED_GROUPS': 'neo4j-users',
        'EMAIL_DOMAINS': 'example.test', 'COOKIE_SECURE': 'false',
        'COOKIE_SECRET': secrets.token_urlsafe(32),
        'DEMO_ADMIN_PASSWORD': secrets.token_urlsafe(24), 'DEMO_PASSWORD': secrets.token_urlsafe(18),
    }
    with os.fdopen(os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as f:
        f.write(''.join(f'{k}={v}\n' for k, v in values.items()))
p.chmod(0o600)
PY
    docker compose --env-file .env.demo -f compose.yaml -f compose.demo.yaml up -d --wait --wait-timeout 300
    curl --fail --silent --show-error --retry 15 --retry-connrefused --retry-delay 1 http://localhost:7476/ping >/dev/null
    echo 'Open http://localhost:7476/browser/ and sign in as demo. Show the password with ./demo.sh password.'
    ;;
  down) docker compose --env-file .env.demo -f compose.yaml -f compose.demo.yaml down ;;
  password) sed -n 's/^DEMO_PASSWORD=//p' .env.demo ;;
  *) echo 'Usage: ./demo.sh [up|down|password]' >&2; exit 2 ;;
esac
