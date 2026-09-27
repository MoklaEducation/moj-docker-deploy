#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ADDONS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
K3S_DIR="$(cd "$ADDONS_DIR/../.." && pwd)"
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

exec python3 "$K3S_DIR/operations/validate/cluster_addons_runtime.py" \
  --mode "$mode" \
  --platform "$K3S_DIR/environments/$environment/platform.yml" \
  --repository "$REPOSITORY" \
  --releases "$ADDONS_DIR/releases.yaml" \
  --values "$ADDONS_DIR/certificates/values/$environment.yaml" \
  --resources "$ADDONS_DIR/certificates/resources/$environment.yaml" \
  --acquire "$SCRIPT_DIR/acquire.sh" \
  --phase-5-report "$K3S_DIR/.evidence/$environment/phase-5-cluster-core.json" \
  --report "$report"