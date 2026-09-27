#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K3S_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
REPOSITORY="$(cd "$K3S_DIR/../.." && pwd)"

environment="${1:-}"
[[ "$environment" =~ ^[a-z][a-z0-9-]*$ ]] || {
  echo "usage: $0 <environment> [facts-path]" >&2
  exit 2
}

environment_dir="$K3S_DIR/environments/$environment"
facts_path="${2:-}"
facts_args=()
[[ -z "$facts_path" ]] || facts_args+=(--facts "$facts_path")

python3 "$K3S_DIR/operations/validate/cluster_core_config.py" \
  --platform "$environment_dir/platform.yml" \
  --repository "$REPOSITORY" \
  --age-identity "$environment_dir/age-identity.txt"
python3 "$K3S_DIR/operations/validate/cluster_core_render.py" \
  --platform "$environment_dir/platform.yml" \
  --overlay "$K3S_DIR/cluster/core/overlays/$environment" \
  "${facts_args[@]}"
recipient="$(python3 -c 'import sys,yaml; print(yaml.safe_load(open(sys.argv[1]))["cluster_core"]["secret_delivery"]["age_recipient"])' "$environment_dir/platform.yml")"
python3 "$K3S_DIR/operations/validate/cluster_core_secrets.py" \
  --template "$K3S_DIR/cluster/core/secrets/template.secret.sops.yaml" \
  --schema "$K3S_DIR/cluster/core/secrets/secret-source.schema.json" \
  --recipient "$recipient"