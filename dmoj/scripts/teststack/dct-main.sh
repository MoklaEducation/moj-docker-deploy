#!/usr/bin/env bash
set -euo pipefail

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo "Do not source dct. Run it as a command: dct <subcommand>"
  return 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/common.sh"
cd "$DMOJ_DIR"

command="${1:-}"

usage() {
  cat <<'EOF'
Usage: dct <subcommand> [args]

Primary subcommands:
  bootstrap [--yes]        Run full bootstrap + reseed flow
  verify                   Run test verification script
  doctor                   Show environment/tooling/prereq diagnostics
  seed-import              Run seed import script
  seed-export              Run seed export script
  status                   Alias for: ps

Compose passthrough:
  dct up -d
  dct down
  dct down -v
  dct stop
  dct start
  dct ps
  dct logs -f nginx
  dct exec site bash

Explicit compose passthrough:
  dct compose <compose-args>
EOF
}

doctor() {
  local missing=()
  local f

  cat <<EOF
dct doctor
project:   $PROJECT_NAME
env file:  $ENV_FILE
test host: $TEST_HOST
dmoj dir:  $DMOJ_DIR
EOF

  echo
  for tool in docker git curl openssl mkcert; do
    if command -v "$tool" >/dev/null 2>&1; then
      printf "tool %-8s : found\n" "$tool"
    else
      printf "tool %-8s : missing\n" "$tool"
    fi
  done

  if docker compose version >/dev/null 2>&1; then
    echo "tool compose  : found"
  else
    echo "tool compose  : missing"
  fi

  for f in "$ENV_FILE" \
           "nginx/certs/test/code.test.local.crt" \
           "nginx/certs/test/code.test.local.key" \
           "repo/requirements.txt" \
           "repo/dmoj/local_settings.py" \
           "repo/websocket/config.js" \
           "repo/uwsgi.ini"; do
    [[ -f "$f" ]] || missing+=("$f")
  done

  echo
  if (( ${#missing[@]} == 0 )); then
    echo "prereqs: OK"
    return 0
  fi

  echo "prereqs: missing"
  for f in "${missing[@]}"; do
    echo "  - $f"
  done
  echo "Run: dct bootstrap"
  return 2
}

run_compose() {
  "${COMPOSE[@]}" "$@"
}

run_start_like() {
  local cmd="$1"
  shift

  check_bootstrap_prereqs || exit 2

  if [[ "$cmd" == "start" ]]; then
    if ! run_compose "$cmd" "$@"; then
      cat <<'EOF'
Tip: 'dct start' needs existing stopped containers.
If containers were removed with 'dct down', use:
  dct up -d
EOF
      exit 1
    fi
    return 0
  fi

  run_compose "$cmd" "$@"
}

case "$command" in
  ""|-h|--help|help)
    usage
    exit 0
    ;;
  bootstrap)
    shift
    "$SCRIPT_DIR/bootstrap-main.sh" "$@"
    exit $?
    ;;
  verify)
    shift
    assert_safe_test_context || exit 2
    env PROJECT_NAME="$PROJECT_NAME" ENV_FILE="$ENV_FILE" "$SCRIPTS_DIR/test-verify" "$@"
    exit $?
    ;;
  doctor)
    shift
    doctor "$@"
    exit $?
    ;;
  seed-import)
    shift
    assert_safe_test_context || exit 2
    env PROJECT_NAME="$PROJECT_NAME" ENV_FILE="$ENV_FILE" "$SCRIPTS_DIR/test-seed-import" "$@"
    exit $?
    ;;
  seed-export)
    shift
    assert_safe_test_context || exit 2
    env PROJECT_NAME="$PROJECT_NAME" ENV_FILE="$ENV_FILE" "$SCRIPTS_DIR/test-seed-export" "$@"
    exit $?
    ;;
  status)
    shift
    assert_safe_test_context || exit 2
    run_compose ps "$@"
    exit $?
    ;;
  compose)
    shift
    assert_safe_test_context || exit 2
    if [[ "$#" -eq 0 ]]; then
      usage
      exit 1
    fi
    case "${1:-}" in
      up|start|restart)
        run_start_like "$@"
        exit $?
        ;;
    esac
    run_compose "$@"
    exit $?
    ;;
  up|start|restart)
    assert_safe_test_context || exit 2
    run_start_like "$command" "${@:2}"
    exit $?
    ;;
  --version|-v|version)
    echo "dct wrapper version 1"
    exit 0
    ;;
  *)
    assert_safe_test_context || exit 2
    run_compose "$@"
    exit $?
    ;;
esac
