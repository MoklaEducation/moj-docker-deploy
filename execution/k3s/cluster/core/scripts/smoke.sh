#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K3S_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
REPOSITORY="$(cd "$K3S_DIR/../.." && pwd)"

environment="${1:-}"
report="${2:-}"
[[ "$environment" =~ ^[a-z][a-z0-9-]*$ && -n "$report" ]] || {
  echo "usage: $0 <environment> <runtime-report>" >&2
  exit 2
}

environment_dir="$K3S_DIR/environments/$environment"
exec python3 "$K3S_DIR/operations/validate/cluster_core_runtime.py" \
  --mode smoke \
  --platform "$environment_dir/platform.yml" \
  --repository "$REPOSITORY" \
  --overlay "$K3S_DIR/cluster/core/overlays/$environment" \
  --phase-4-report "$K3S_DIR/.evidence/$environment/phase-4-k3s-installation.json" \
  --report "$report"