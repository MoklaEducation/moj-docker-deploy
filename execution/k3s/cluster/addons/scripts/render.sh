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

temporary="$(mktemp -d)"
trap 'rm -rf "$temporary"' EXIT
"$SCRIPT_DIR/acquire.sh" certificates "$temporary/certificates.tgz"
"$HELM" template cert-manager "$temporary/certificates.tgz" \
  --namespace cert-manager \
  --include-crds \
  --values "$values"
printf '%s\n' '---'
cat "$resources"

metrics_enabled="$(python3 - "$K3S_DIR/environments/$environment/platform.yml" <<'PY'
import sys, yaml
print(str(yaml.safe_load(open(sys.argv[1], encoding="utf-8"))["cluster_addons"]["capabilities"]["metrics"]).lower())
PY
)"
if [[ "$metrics_enabled" == "true" ]]; then
  metrics_values="$ADDONS_DIR/metrics/values/$environment.yaml"
  metrics_resources="$ADDONS_DIR/metrics/resources/$environment.yaml"
  node_values="$ADDONS_DIR/node-metrics/values/$environment.yaml"
  node_resources="$ADDONS_DIR/node-metrics/resources/$environment.yaml"
  [[ -f "$metrics_values" && -f "$metrics_resources" && -f "$node_values" && -f "$node_resources" ]] || {
    echo "error: metrics profile does not exist: $environment" >&2
    exit 1
  }
  "$SCRIPT_DIR/acquire.sh" metrics "$temporary/metrics.tgz"
  "$SCRIPT_DIR/acquire.sh" node_metrics "$temporary/node-metrics.tgz"
  printf '\n%s\n' '---'
  "$HELM" template monitoring "$temporary/metrics.tgz" \
    --namespace observability \
    --include-crds \
    --values "$metrics_values"
  printf '%s\n' '---'
  cat "$metrics_resources"
  printf '\n%s\n' '---'
  "$HELM" template node-exporter "$temporary/node-metrics.tgz" \
    --namespace observability-agents \
    --values "$node_values"
  printf '%s\n' '---'
  cat "$node_resources"
fi