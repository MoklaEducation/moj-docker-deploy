#!/usr/bin/env bash
set -euo pipefail

COMMON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_DIR="$(cd "$COMMON_DIR/.." && pwd)"
DMOJ_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"
ROOT_DIR="$(cd "$DMOJ_DIR/.." && pwd)"

PROJECT_NAME="${PROJECT_NAME:-dmoj-test}"
ENV_FILE="${ENV_FILE:-.env.test}"
SEED_DUMP="${SEED_DUMP:-seeds/latest.sql.gz}"
TEST_HOST="${DMOJ_TEST_HOST:-code.test.local}"

COMPOSE=(docker compose --env-file "$ENV_FILE" -f docker-compose.yml -f docker-compose.test.yml -p "$PROJECT_NAME")

show_bootstrap_hint() {
  cat <<'EOF'
Bootstrap prerequisites are incomplete for test startup.
Run bootstrap once:
  dct bootstrap

Or set any needed variables first, for example:
  PROJECT_NAME=dmoj-test ENV_FILE=.env.test SEED_DUMP=seeds/latest.sql.gz dct bootstrap --yes
EOF
}

check_bootstrap_prereqs() {
  local missing=()

  [[ -f "$ENV_FILE" ]] || missing+=("$ENV_FILE")
  [[ -f "nginx/certs/test/code.test.local.crt" ]] || missing+=("nginx/certs/test/code.test.local.crt")
  [[ -f "nginx/certs/test/code.test.local.key" ]] || missing+=("nginx/certs/test/code.test.local.key")
  [[ -f "repo/requirements.txt" ]] || missing+=("repo/requirements.txt")
  [[ -f "repo/dmoj/local_settings.py" ]] || missing+=("repo/dmoj/local_settings.py")
  [[ -f "repo/websocket/config.js" ]] || missing+=("repo/websocket/config.js")
  [[ -f "repo/uwsgi.ini" ]] || missing+=("repo/uwsgi.ini")

  if (( ${#missing[@]} > 0 )); then
    echo "Missing bootstrap prerequisites:"
    for item in "${missing[@]}"; do
      echo "  - $item"
    done
    show_bootstrap_hint
    return 1
  fi

  return 0
}
