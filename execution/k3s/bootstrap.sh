#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENVIRONMENTS_DIR="$SCRIPT_DIR/environments"
SCHEMA="$SCRIPT_DIR/operations/validate/schemas/platform.schema.json"
PREFLIGHT="$SCRIPT_DIR/operations/validate/preflight.py"
UPDATE_REPORT="$SCRIPT_DIR/operations/validate/update_report.py"
HOST_BASELINE_REPORT="$SCRIPT_DIR/operations/validate/host_baseline_report.py"
CONTROLLER_VENV="$SCRIPT_DIR/.controller-venv"

if [[ -x "$CONTROLLER_VENV/bin/python3" ]]; then
  export PATH="$CONTROLLER_VENV/bin:$PATH"
fi

usage() {
  cat <<'EOF'
Usage:
  ./execution/k3s/bootstrap.sh check --environment NAME
  ./execution/k3s/bootstrap.sh check --environment NAME --through host-baseline
  ./execution/k3s/bootstrap.sh apply --environment NAME --through host-baseline

The check action is non-mutating. The apply action is available only with an explicit
--through host-baseline boundary and never reboots the host automatically.
EOF
}

die_usage() {
  echo "error: $1" >&2
  usage >&2
  exit 2
}

action=""
environment=""
through=""
while (($# > 0)); do
  case "$1" in
    --help|-h) usage; exit 0 ;;
    check|apply) [[ -z "$action" ]] || die_usage "action specified more than once"; action="$1"; shift ;;
    --environment) (($# >= 2)) || die_usage "--environment requires a value"; environment="$2"; shift 2 ;;
    --environment=*) environment="${1#*=}"; [[ -n "$environment" ]] || die_usage "--environment requires a value"; shift ;;
    --through) (($# >= 2)) || die_usage "--through requires a value"; through="$2"; shift 2 ;;
    --through=*) through="${1#*=}"; [[ -n "$through" ]] || die_usage "--through requires a value"; shift ;;
    *) die_usage "unknown option or argument: $1" ;;
  esac
done

[[ "$action" == "check" || "$action" == "apply" ]] || die_usage "an action is required"
[[ -n "$environment" ]] || die_usage "--environment is required"
[[ -z "$through" || "$through" == "host-baseline" ]] || die_usage "unsupported phase: $through"
[[ "$action" != "apply" || "$through" == "host-baseline" ]] || die_usage "apply requires --through host-baseline"
[[ "$EUID" -ne 0 ]] || { echo "error: do not run bootstrap as root" >&2; exit 1; }

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

if (( ansible_status != 0 )) || [[ -z "$through" ]]; then
  exit "$ansible_status"
fi

phase2_report_path="$SCRIPT_DIR/.evidence/$environment/phase-2-host-baseline.json"
phase2_facts_path="$SCRIPT_DIR/.evidence/$environment/.phase-2-host-baseline-facts.json"
phase2_output="$(mktemp)"
trap 'rm -f "$phase2_output" "$phase2_facts_path"' EXIT
rm -f "$phase2_facts_path"

phase2_args=()
if [[ "$action" == "check" ]]; then
  phase2_args+=(--check --diff)
fi

set +e
ansible-playbook \
  -i "$environment_dir/inventory.yml" \
  "$SCRIPT_DIR/host/playbooks/host-baseline.yml" \
  -e "platform_file=$environment_dir/platform.yml" \
  -e "phase2_facts_path=$phase2_facts_path" \
  "${phase2_args[@]}" 2>&1 | tee "$phase2_output"
phase2_status=${PIPESTATUS[0]}
set -e

set +e
python3 "$HOST_BASELINE_REPORT" \
  --environment "$environment" \
  --mode "$action" \
  --phase-1-report "$report_path" \
  --facts "$phase2_facts_path" \
  --ansible-output "$phase2_output" \
  --ansible-status "$phase2_status" \
  --report "$phase2_report_path"
report_status=$?
set -e

if (( phase2_status != 0 )); then
  exit "$phase2_status"
fi
exit "$report_status"
