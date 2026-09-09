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
  seed-import              Run seed import script
  seed-export              Run seed export script

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
    env PROJECT_NAME="$PROJECT_NAME" ENV_FILE="$ENV_FILE" "$SCRIPTS_DIR/test-verify" "$@"
    exit $?
    ;;
  seed-import)
    shift
    env PROJECT_NAME="$PROJECT_NAME" ENV_FILE="$ENV_FILE" "$SCRIPTS_DIR/test-seed-import" "$@"
    exit $?
    ;;
  seed-export)
    shift
    env PROJECT_NAME="$PROJECT_NAME" ENV_FILE="$ENV_FILE" "$SCRIPTS_DIR/test-seed-export" "$@"
    exit $?
    ;;
  compose)
    shift
    if [[ "$#" -eq 0 ]]; then
      usage
      exit 1
    fi
    case "${1:-}" in
      up|start|restart)
        check_bootstrap_prereqs || exit 2
        ;;
    esac
    "${COMPOSE[@]}" "$@"
    exit $?
    ;;
  up|start|restart)
    check_bootstrap_prereqs || exit 2
    "${COMPOSE[@]}" "$@"
    exit $?
    ;;
  *)
    "${COMPOSE[@]}" "$@"
    exit $?
    ;;
esac
