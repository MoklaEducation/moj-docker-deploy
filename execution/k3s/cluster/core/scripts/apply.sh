#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K3S_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
REPOSITORY="$(cd "$K3S_DIR/../.." && pwd)"

mode="${1:-}"
environment="${2:-}"
report="${3:-}"
[[ "$mode" == "check" || "$mode" == "apply" ]] || {
  echo "usage: $0 <check|apply> <environment> <runtime-report>" >&2
  exit 2
}
[[ "$environment" =~ ^[a-z][a-z0-9-]*$ && -n "$report" ]] || {
  echo "usage: $0 <check|apply> <environment> <runtime-report>" >&2
  exit 2
}

environment_dir="$K3S_DIR/environments/$environment"
phase5_report="$K3S_DIR/.evidence/$environment/phase-5-cluster-core.json"
previous_args=()
[[ ! -f "$phase5_report" ]] || previous_args+=(--previous-report "$phase5_report")

exec python3 "$K3S_DIR/operations/validate/cluster_core_runtime.py" \
  --mode "$mode" \
  --platform "$environment_dir/platform.yml" \
  --repository "$REPOSITORY" \
  --overlay "$K3S_DIR/cluster/core/overlays/$environment" \
  --phase-4-report "$K3S_DIR/.evidence/$environment/phase-4-k3s-installation.json" \
  --report "$report" \
  "${previous_args[@]}"