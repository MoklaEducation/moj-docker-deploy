#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/common.sh"
cd "$DMOJ_DIR"

ASSUME_YES=0

usage() {
  cat <<'EOF'
Usage: dct bootstrap [--yes|-y] [--help|-h]

Bootstraps the test stack and reseeds the database from SEED_DUMP.

Options:
  --yes, -y   Skip confirmation prompt
  --help, -h  Show this help
EOF
}

parse_args() {
  while (( $# > 0 )); do
    case "$1" in
      --yes|-y)
        ASSUME_YES=1
        ;;
      --help|-h)
        usage
        exit 0
        ;;
      *)
        echo "Unknown argument: $1"
        usage
        exit 1
        ;;
    esac
    shift
  done
}

confirm_reseed() {
  if [[ "$ASSUME_YES" == "1" ]]; then
    return 0
  fi

  if [[ ! -t 0 ]]; then
    echo "Refusing to run without confirmation in non-interactive mode."
    echo "Re-run with --yes to continue."
    exit 1
  fi

  echo "WARNING: dct bootstrap will reset and re-import test database data from $SEED_DUMP."
  echo "Type 'yes' to continue:"
  read -r answer
  if [[ "$answer" != "yes" ]]; then
    echo "Aborted."
    exit 1
  fi
}

ensure_env_file() {
  if [[ ! -f "$ENV_FILE" ]]; then
    if [[ -f ".env.test.example" && "$ENV_FILE" == ".env.test" ]]; then
      cp .env.test.example .env.test
      echo "Created .env.test from .env.test.example"
    else
      echo "Missing env file: $ENV_FILE"
      exit 1
    fi
  fi
}

ensure_seed_dump() {
  if [[ ! -f "$SEED_DUMP" ]]; then
    echo "Missing seed dump: $SEED_DUMP"
    echo "Create one with ./scripts/test-seed-export or provide SEED_DUMP=<path>."
    exit 1
  fi
}

ensure_submodule() {
  git -C "$ROOT_DIR" submodule update --init --recursive dmoj/repo
}

sync_runtime_config() {
  cp "$ROOT_DIR/local_settings.py" "$DMOJ_DIR/repo/dmoj/local_settings.py"
  cp "$ROOT_DIR/config.js" "$DMOJ_DIR/repo/websocket/config.js"
  cp "$ROOT_DIR/uwsgi.ini" "$DMOJ_DIR/repo/uwsgi.ini"
}

ensure_test_certs() {
  local cert="nginx/certs/test/code.test.local.crt"
  local key="nginx/certs/test/code.test.local.key"

  if [[ -f "$cert" && -f "$key" ]]; then
    return 0
  fi

  mkdir -p nginx/certs/test

  if command -v mkcert >/dev/null 2>&1; then
    mkcert -cert-file "$cert" -key-file "$key" "$TEST_HOST"
    echo "Generated certs using mkcert for host: $TEST_HOST"
    return 0
  fi

  if command -v openssl >/dev/null 2>&1; then
    openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
      -keyout "$key" \
      -out "$cert" \
      -subj "/CN=$TEST_HOST" \
      -addext "subjectAltName=DNS:$TEST_HOST"
    echo "Generated self-signed certs using openssl for host: $TEST_HOST"
    return 0
  fi

  echo "Neither mkcert nor openssl is available to generate test certs."
  exit 1
}

preflight_required_files() {
  local missing=()
  local f

  for f in "$ENV_FILE" \
           "$SEED_DUMP" \
           "nginx/certs/test/code.test.local.crt" \
           "nginx/certs/test/code.test.local.key" \
           "repo/requirements.txt" \
           "repo/dmoj/local_settings.py" \
           "repo/websocket/config.js" \
           "repo/uwsgi.ini"; do
    [[ -f "$f" ]] || missing+=("$f")
  done

  if (( ${#missing[@]} > 0 )); then
    echo "Preflight failed. Missing files:"
    for f in "${missing[@]}"; do
      echo "  - $f"
    done
    exit 1
  fi
}

run_bootstrap() {
  PROJECT_NAME="$PROJECT_NAME" ENV_FILE="$ENV_FILE" SEED_DUMP="$SEED_DUMP" "$SCRIPTS_DIR/test-bootstrap"
}

finalize_static_artifacts() {
  "${COMPOSE[@]}" exec -T site python3 manage.py compilemessages
  "${COMPOSE[@]}" exec -T site python3 manage.py compilejsi18n
  "${COMPOSE[@]}" exec -T site python3 manage.py collectstatic --noinput
}

verify_stack() {
  PROJECT_NAME="$PROJECT_NAME" ENV_FILE="$ENV_FILE" "$SCRIPTS_DIR/test-verify"

  local https_port
  https_port="$(grep '^DMOJ_TEST_HTTPS_PORT=' "$ENV_FILE" | cut -d= -f2 || true)"
  https_port="${https_port:-8443}"

  echo "--- host-header probe ---"
  curl -kI -H "Host: $TEST_HOST" "https://127.0.0.1:${https_port}/" | sed -n '1,10p'
}

parse_args "$@"
assert_safe_test_context || exit 2
confirm_reseed
ensure_env_file
ensure_seed_dump
ensure_submodule
sync_runtime_config
ensure_test_certs
preflight_required_files
run_bootstrap
finalize_static_artifacts
verify_stack

echo "dct bootstrap complete for project: $PROJECT_NAME"
