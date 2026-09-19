#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENVIRONMENTS_DIR="$SCRIPT_DIR/environments"
SCHEMA="$SCRIPT_DIR/operations/validate/schemas/platform.schema.json"
PREFLIGHT="$SCRIPT_DIR/operations/validate/preflight.py"
UPDATE_REPORT="$SCRIPT_DIR/operations/validate/update_report.py"
HOST_BASELINE_REPORT="$SCRIPT_DIR/operations/validate/host_baseline_report.py"
DATA_SERVICES_CONFIG="$SCRIPT_DIR/operations/validate/data_services_config.py"
DATA_SERVICES_SECRETS="$SCRIPT_DIR/operations/validate/data_services_secrets.py"
DATA_SERVICES_RUNTIME="$SCRIPT_DIR/operations/validate/data_services_runtime.py"
DATA_SERVICES_REPORT="$SCRIPT_DIR/operations/validate/data_services_report.py"
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
  ./execution/k3s/bootstrap.sh check --environment NAME --through host-data-services
  ./execution/k3s/bootstrap.sh apply --environment NAME --through host-data-services

The check action is non-mutating. The apply action requires an explicit --through
boundary and never reboots the host automatically.
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
[[ -z "$through" || "$through" == "host-baseline" || "$through" == "host-data-services" ]] || die_usage "unsupported phase: $through"
[[ "$action" != "apply" || -n "$through" ]] || die_usage "apply requires an explicit --through boundary"
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
if (( report_status != 0 )) || [[ "$through" == "host-baseline" ]]; then
  exit "$report_status"
fi

python3 "$DATA_SERVICES_CONFIG" --platform "$environment_dir/platform.yml"
python3 "$DATA_SERVICES_SECRETS" \
  --platform "$environment_dir/platform.yml" \
  --secrets "$environment_dir/secrets.sops.yml"

phase3_report_path="$SCRIPT_DIR/.evidence/$environment/phase-3-host-data-services.json"
phase3_facts_path="$SCRIPT_DIR/.evidence/$environment/.phase-3-host-data-services-facts.json"
phase3_runtime_path="$SCRIPT_DIR/.evidence/$environment/.phase-3-runtime.json"
phase3_output="$(mktemp)"
phase3_secrets=""
trap 'rm -f "$phase2_output" "$phase2_facts_path" "$phase3_output" "$phase3_facts_path" "$phase3_runtime_path" "$phase3_secrets"' EXIT
rm -f "$phase3_facts_path" "$phase3_runtime_path"

phase3_args=()
if [[ "$action" == "check" ]]; then
  phase3_args+=(--check --diff)
else
  phase3_secrets="$(mktemp)"
  chmod 0600 "$phase3_secrets"
  sops --decrypt --output "$phase3_secrets" "$environment_dir/secrets.sops.yml"
  phase3_args+=(-e "@$phase3_secrets")
fi

set +e
ansible-playbook \
  -i "$environment_dir/inventory.yml" \
  "$SCRIPT_DIR/host/playbooks/host-data-services.yml" \
  -e "platform_file=$environment_dir/platform.yml" \
  -e "phase2_report_path=$phase2_report_path" \
  -e "phase3_facts_path=$phase3_facts_path" \
  "${phase3_args[@]}" 2>&1 | tee "$phase3_output"
phase3_status=${PIPESTATUS[0]}
set -e

set +e
python3 "$DATA_SERVICES_RUNTIME" \
  --platform "$environment_dir/platform.yml" \
  --secrets "$environment_dir/secrets.sops.yml" \
  --report "$phase3_runtime_path"
phase3_runtime_status=$?
set -e

set +e
python3 "$DATA_SERVICES_REPORT" \
  --environment "$environment" \
  --mode "$action" \
  --phase-1-report "$report_path" \
  --phase-2-report "$phase2_report_path" \
  --facts "$phase3_facts_path" \
  --runtime-report "$phase3_runtime_path" \
  --ansible-output "$phase3_output" \
  --ansible-status "$phase3_status" \
  --report "$phase3_report_path"
phase3_report_status=$?
set -e

if (( phase3_status != 0 )); then
  exit "$phase3_status"
fi
if (( phase3_runtime_status != 0 )); then
  exit "$phase3_runtime_status"
fi
exit "$phase3_report_status"
