#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

environment="${1:-}"
[[ "$environment" =~ ^[a-z][a-z0-9-]*$ ]] || {
  echo "usage: $0 <environment>" >&2
  exit 2
}

overlay="$CORE_DIR/overlays/$environment"
[[ -f "$overlay/kustomization.yaml" ]] || {
  echo "error: cluster-core overlay does not exist: $environment" >&2
  exit 1
}

exec k3s kubectl kustomize "$overlay"