#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ADDONS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
K3S_DIR="$(cd "$ADDONS_DIR/../.." && pwd)"
REPOSITORY="$(cd "$K3S_DIR/../.." && pwd)"
environment="${1:-}"
facts="${2:-}"
[[ "$environment" =~ ^[a-z][a-z0-9-]*$ ]] || {
  echo "usage: $0 <environment> [facts-path]" >&2
  exit 2
}

first="$(mktemp)"
second="$(mktemp)"
trap 'rm -f "$first" "$second"' EXIT
"$SCRIPT_DIR/render.sh" "$environment" >"$first"
"$SCRIPT_DIR/render.sh" "$environment" >"$second"
cmp --silent "$first" "$second" || { echo "error: two identical add-on renders differ" >&2; exit 1; }

args=(
  --platform "$K3S_DIR/environments/$environment/platform.yml"
  --releases "$ADDONS_DIR/releases.yaml"
  --manifest "$first"
  --repository "$REPOSITORY"
)
[[ -z "$facts" ]] || args+=(--facts "$facts")
exec python3 "$K3S_DIR/operations/validate/cluster_addons_render.py" "${args[@]}"