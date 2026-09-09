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

is_test_like_env_file() {
  local base
  base="$(basename "$ENV_FILE")"
  [[ "$base" =~ (^|[._-])test([._-]|$) ]]
}

assert_safe_test_context() {
  local unsafe_re='(^|[-_.])(prod|production|live)($|[-_.])'

  if [[ "${DCT_ALLOW_UNSAFE:-0}" == "1" ]]; then
    return 0
  fi

  if ! is_test_like_env_file; then
    cat <<EOF
Refusing to run in non-test context.
ENV_FILE='$ENV_FILE' does not look test-scoped.

Use a test env file (for example: .env.test), or override intentionally:
  DCT_ALLOW_UNSAFE=1 dct <subcommand>
EOF
    return 1
  fi

  if [[ "$PROJECT_NAME" =~ $unsafe_re ]]; then
    cat <<EOF
Refusing to run with project name '$PROJECT_NAME' because it looks production-like.

Use a dedicated test project name, or override intentionally:
  DCT_ALLOW_UNSAFE=1 PROJECT_NAME='$PROJECT_NAME' dct <subcommand>
EOF
    return 1
  fi

  return 0
}

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
