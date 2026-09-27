#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ADDONS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
K3S_DIR="$(cd "$ADDONS_DIR/../.." && pwd)"
HELM="$K3S_DIR/.controller-venv/bin/helm"
environment="${1:-}"
[[ "$environment" =~ ^[a-z][a-z0-9-]*$ ]] || {
  echo "usage: $0 <environment>" >&2
  exit 2
}
[[ -x "$HELM" ]] || { echo "error: pinned Helm is not installed; run controller.sh install" >&2; exit 1; }

values="$ADDONS_DIR/certificates/values/$environment.yaml"
resources="$ADDONS_DIR/certificates/resources/$environment.yaml"
[[ -f "$values" && -f "$resources" ]] || { echo "error: certificate profile does not exist: $environment" >&2; exit 1; }

chart="$(mktemp)"
trap 'rm -f "$chart"' EXIT
"$SCRIPT_DIR/acquire.sh" certificates "$chart"
"$HELM" template cert-manager "$chart" \
  --namespace cert-manager \
  --include-crds \
  --values "$values"
printf '%s\n' '---'
cat "$resources"