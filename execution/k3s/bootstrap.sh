#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENVIRONMENTS_DIR="$SCRIPT_DIR/environments"
SCHEMA="$SCRIPT_DIR/operations/validate/schemas/platform.schema.json"
PREFLIGHT="$SCRIPT_DIR/operations/validate/preflight.py"
UPDATE_REPORT="$SCRIPT_DIR/operations/validate/update_report.py"

usage() {
  cat <<'EOF'
Usage:
  ./execution/k3s/bootstrap.sh check --environment NAME

The check action validates controller prerequisites and environment inputs without
changing the target host.
EOF
}

die_usage() {
  echo "error: $1" >&2
  usage >&2
  exit 2
}

action=""
environment=""
while (($# > 0)); do
  case "$1" in
    --help|-h) usage; exit 0 ;;
    check) [[ -z "$action" ]] || die_usage "action specified more than once"; action="$1"; shift ;;
    --environment) (($# >= 2)) || die_usage "--environment requires a value"; environment="$2"; shift 2 ;;
    --environment=*) environment="${1#*=}"; [[ -n "$environment" ]] || die_usage "--environment requires a value"; shift ;;
    *) die_usage "unknown option or argument: $1" ;;
  esac
done

[[ "$action" == "check" ]] || die_usage "an action is required"
[[ -n "$environment" ]] || die_usage "--environment is required"
[[ "$EUID" -ne 0 ]] || { echo "error: do not run preflight as root" >&2; exit 1; }

environment_dir="$ENVIRONMENTS_DIR/$environment"
report_path="$SCRIPT_DIR/.evidence/$environment/phase-1-preflight.json"

set +e
python3 "$PREFLIGHT" \
    --environment "$environment" \
    --environment-dir "$environment_dir" \
    --schema "$SCHEMA" \
    --report "$report_path" \
    --repository "$REPO_DIR"
controller_status=$?
set -e
if (( controller_status != 0 )); then
  exit "$controller_status"
fi

set +e
export ANSIBLE_CONFIG="$SCRIPT_DIR/host/ansible.cfg"
ansible-playbook \
  -i "$environment_dir/inventory.yml" \
  "$SCRIPT_DIR/host/playbooks/preflight.yml" \
  -e "platform_file=$environment_dir/platform.yml" \
  -e "report_path=$report_path"
ansible_status=$?
set -e

python3 "$UPDATE_REPORT" --report "$report_path" --ansible-status "$ansible_status"

exit "$ansible_status"
