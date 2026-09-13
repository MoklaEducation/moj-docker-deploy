#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="${PROJECT_NAME:-dmoj-test}"
KEYCLOAK_ENV_FILE="${KEYCLOAK_ENV_FILE:-environment/keycloak.test.env}"
KEYCLOAK_CERT="nginx/certs/test/code.test.local.crt"
KEYCLOAK_HOST="${KEYCLOAK_HOST:-auth.test.local}"
KEYCLOAK_SERVICES=(keycloak-db keycloak)
KEYCLOAK_UP_SERVICES=(keycloak-db keycloak nginx)

COMPOSE=(docker compose --env-file "$KEYCLOAK_ENV_FILE" -f docker-compose.yml -f docker-compose.test.yml -f docker-compose.keycloak.test.yml -p "$PROJECT_NAME")

usage() {
  cat <<'EOF'
Usage: dct keycloak <command> [args]

Commands:
  doctor                 Check Keycloak test prerequisites
  bootstrap [--yes]     Create local env if absent, start, and verify Keycloak
  up [-d]                Start Keycloak and its dedicated database
  down                  Stop and remove only Keycloak containers
  down -v [--yes]       Also remove only the dedicated Keycloak database volume
  status                Show Keycloak service status
  logs [-f]              Show Keycloak service logs
  verify                Check HTTPS OIDC discovery and issuer
EOF
}

run_compose() {
  "${COMPOSE[@]}" "$@"
}

require_env() {
  if [[ ! -f "$KEYCLOAK_ENV_FILE" ]]; then
    echo "Missing $KEYCLOAK_ENV_FILE. Run: cp environment/keycloak.test.env.example $KEYCLOAK_ENV_FILE"
    return 1
  fi
}

doctor() {
  local missing=()
  [[ -f "$KEYCLOAK_ENV_FILE" ]] || missing+=("$KEYCLOAK_ENV_FILE")
  [[ -f "docker-compose.keycloak.test.yml" ]] || missing+=("docker-compose.keycloak.test.yml")
  [[ -f "keycloak/test/realm-dmoj-test.json" ]] || missing+=("keycloak/test/realm-dmoj-test.json")
  [[ -f "$KEYCLOAK_CERT" ]] || missing+=("$KEYCLOAK_CERT")
  getent hosts "$KEYCLOAK_HOST" >/dev/null 2>&1 || missing+=("hosts entry for $KEYCLOAK_HOST")

  if [[ -f "$KEYCLOAK_ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$KEYCLOAK_ENV_FILE"
    set +a
    for required in KEYCLOAK_TEST_USER KEYCLOAK_TEST_USER_PASSWORD KEYCLOAK_TEST_USER_EMAIL KEYCLOAK_TEST_USER_FIRST_NAME KEYCLOAK_TEST_USER_LAST_NAME; do
      [[ -n "${!required:-}" ]] || missing+=("$required in $KEYCLOAK_ENV_FILE")
    done
  fi

  if (( ${#missing[@]} > 0 )); then
    echo "Keycloak prerequisites: missing"
    printf '  - %s\n' "${missing[@]}"
    return 2
  fi

  echo "Keycloak prerequisites: OK"
  echo "env file: $KEYCLOAK_ENV_FILE"
  echo "host: $KEYCLOAK_HOST"
}

verify() {
  require_env
  local discovery issuer
  discovery="$(curl --fail --silent --show-error --cacert "$KEYCLOAK_CERT" --resolve "$KEYCLOAK_HOST:443:127.0.0.1" "https://$KEYCLOAK_HOST/realms/master/.well-known/openid-configuration")"
  issuer="$(printf '%s' "$discovery" | jq -r '.issuer')"
  [[ "$issuer" == "https://$KEYCLOAK_HOST/realms/master" ]] || {
    echo "Unexpected Keycloak issuer: $issuer"
    return 1
  }
  echo "Keycloak discovery OK: $issuer"
}

configure_test_user() {
  local required
  require_env
  set -a
  # shellcheck disable=SC1090
  source "$KEYCLOAK_ENV_FILE"
  set +a

  for required in KEYCLOAK_ADMIN KEYCLOAK_ADMIN_PASSWORD KEYCLOAK_TEST_USER KEYCLOAK_TEST_USER_PASSWORD KEYCLOAK_TEST_USER_EMAIL KEYCLOAK_TEST_USER_FIRST_NAME KEYCLOAK_TEST_USER_LAST_NAME; do
    if [[ -z "${!required:-}" ]]; then
      echo "Missing $required in $KEYCLOAK_ENV_FILE"
      return 1
    fi
  done

  run_compose exec -T \
    -e KEYCLOAK_ADMIN="$KEYCLOAK_ADMIN" \
    -e KEYCLOAK_ADMIN_PASSWORD="$KEYCLOAK_ADMIN_PASSWORD" \
    -e KEYCLOAK_TEST_USER="$KEYCLOAK_TEST_USER" \
    -e KEYCLOAK_TEST_USER_PASSWORD="$KEYCLOAK_TEST_USER_PASSWORD" \
    -e KEYCLOAK_TEST_USER_EMAIL="$KEYCLOAK_TEST_USER_EMAIL" \
    -e KEYCLOAK_TEST_USER_FIRST_NAME="$KEYCLOAK_TEST_USER_FIRST_NAME" \
    -e KEYCLOAK_TEST_USER_LAST_NAME="$KEYCLOAK_TEST_USER_LAST_NAME" \
    keycloak bash -lc '
      set -e
      /opt/keycloak/bin/kcadm.sh config credentials \
        --server http://127.0.0.1:8080 \
        --realm master \
        --user "$KEYCLOAK_ADMIN" \
        --password "$KEYCLOAK_ADMIN_PASSWORD" >/dev/null

      user_id="$(/opt/keycloak/bin/kcadm.sh get users -r dmoj-test \
        -q username="$KEYCLOAK_TEST_USER" --fields id --format csv | tail -n 1)"
      user_id="${user_id//\"/}"
      if [[ -z "$user_id" ]]; then
        /opt/keycloak/bin/kcadm.sh create users -r dmoj-test \
          -s username="$KEYCLOAK_TEST_USER" \
          -s email="$KEYCLOAK_TEST_USER_EMAIL" \
          -s firstName="$KEYCLOAK_TEST_USER_FIRST_NAME" \
          -s lastName="$KEYCLOAK_TEST_USER_LAST_NAME" \
          -s enabled=true >/dev/null
        user_id="$(/opt/keycloak/bin/kcadm.sh get users -r dmoj-test \
          -q username="$KEYCLOAK_TEST_USER" --fields id --format csv | tail -n 1)"
        user_id="${user_id//\"/}"
      fi

      [[ -n "$user_id" ]]
      /opt/keycloak/bin/kcadm.sh update "users/$user_id" -r dmoj-test \
        -s email="$KEYCLOAK_TEST_USER_EMAIL" \
        -s firstName="$KEYCLOAK_TEST_USER_FIRST_NAME" \
        -s lastName="$KEYCLOAK_TEST_USER_LAST_NAME" \
        -s enabled=true >/dev/null
      /opt/keycloak/bin/kcadm.sh set-password -r dmoj-test \
        --username "$KEYCLOAK_TEST_USER" --new-password "$KEYCLOAK_TEST_USER_PASSWORD" >/dev/null
      echo "Configured Keycloak test user: $KEYCLOAK_TEST_USER"
    '
}

bootstrap() {
  local arg
  for arg in "$@"; do
    case "$arg" in
      --yes|-y) ;;
      *) echo "Unknown bootstrap option: $arg"; usage; return 1 ;;
    esac
  done

  if [[ ! -f "$KEYCLOAK_ENV_FILE" ]]; then
    mkdir -p "$(dirname "$KEYCLOAK_ENV_FILE")"
    cp environment/keycloak.test.env.example "$KEYCLOAK_ENV_FILE"
    echo "Created $KEYCLOAK_ENV_FILE from the example. Set local passwords before continuing."
  fi

  run_compose up -d "${KEYCLOAK_UP_SERVICES[@]}"
  verify
  configure_test_user
}

down() {
  local remove_volume=0
  local assume_yes=0
  local arg
  for arg in "$@"; do
    case "$arg" in
      -v|--volumes) remove_volume=1 ;;
      --yes|-y) assume_yes=1 ;;
      *) echo "Unknown down option: $arg"; usage; return 1 ;;
    esac
  done

  if (( remove_volume == 1 && assume_yes == 0 )); then
    if [[ ! -t 0 ]]; then
      echo "Refusing destructive Keycloak down in non-interactive mode. Re-run with --yes."
      return 1
    fi
    printf "Remove only the Keycloak database volume? Type 'yes' to continue: "
    read -r answer
    [[ "$answer" == "yes" ]] || { echo "Aborted."; return 1; }
  fi

  run_compose rm -sf "${KEYCLOAK_SERVICES[@]}"
  if (( remove_volume == 1 )); then
    docker volume rm "${PROJECT_NAME}_keycloak-db-data"
  fi
}

command="${1:-}"
shift || true
case "$command" in
  doctor) doctor "$@" ;;
  bootstrap) bootstrap "$@" ;;
  up)
    require_env
    run_compose up "$@" "${KEYCLOAK_UP_SERVICES[@]}"
    ;;
  down) require_env; down "$@" ;;
  status) require_env; run_compose ps "$@" "${KEYCLOAK_SERVICES[@]}" ;;
  logs) require_env; run_compose logs "$@" keycloak keycloak-db ;;
  verify) verify ;;
  ""|-h|--help|help) usage ;;
  *) echo "Unknown Keycloak command: $command"; usage; exit 1 ;;
esac
