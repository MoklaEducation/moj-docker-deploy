#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K3S_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
REPOSITORY="$(cd "$K3S_DIR/../.." && pwd)"

action="${1:-}"
environment="${2:-}"
[[ "$action" == "check" || "$action" == "apply" ]] || {
  echo "usage: $0 <check|apply> <environment>" >&2
  exit 2
}
[[ "$environment" =~ ^[a-z][a-z0-9-]*$ ]] || {
  echo "usage: $0 <check|apply> <environment>" >&2
  exit 2
}

environment_dir="$K3S_DIR/environments/$environment"
platform="$environment_dir/platform.yml"
admin="$REPOSITORY/$(python3 -c 'import sys,yaml; print(yaml.safe_load(open(sys.argv[1]))["k3s"]["kubeconfig_output"])' "$platform")"

if [[ "$action" == "apply" ]]; then
  "$SCRIPT_DIR/render.sh" "$environment" | python3 -c '
import sys, yaml
allowed = {"ClusterRole", "ClusterRoleBinding", "RoleBinding"}
documents = [item for item in yaml.safe_load_all(sys.stdin) if item and item.get("kind") in allowed]
yaml.safe_dump_all(documents, sys.stdout, sort_keys=False)
' | k3s kubectl --kubeconfig "$admin" apply --server-side --field-manager=mokla-cluster-core -f -
  exec python3 "$K3S_DIR/operations/validate/cluster_core_access.py" ensure \
    --platform "$platform" --repository "$REPOSITORY" --admin-kubeconfig "$admin"
fi

exec python3 "$K3S_DIR/operations/validate/cluster_core_access.py" check \
  --platform "$platform" --repository "$REPOSITORY" --admin-kubeconfig "$admin"