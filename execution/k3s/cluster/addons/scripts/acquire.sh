#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ADDONS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
release="${1:-}"
output="${2:-}"
[[ "$release" =~ ^[a-z][a-z0-9_]*$ && -n "$output" ]] || {
  echo "usage: $0 <release> <output-path>" >&2
  exit 2
}

readarray -t chart < <(python3 - "$ADDONS_DIR/releases.yaml" "$release" <<'PY'
import sys, yaml
inventory = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))["releases"]
if sys.argv[2] not in inventory:
  raise SystemExit(f"error: unknown release: {sys.argv[2]}")
item = inventory[sys.argv[2]]["chart"]
print(item["url"])
print(item["sha256"])
PY
)
[[ ${#chart[@]} -eq 2 ]] || { echo "error: invalid release inventory" >&2; exit 1; }

temporary="${output}.download"
rm -f "$temporary"
trap 'rm -f "$temporary"' EXIT
curl --fail --location --silent --show-error --output "$temporary" "${chart[0]}"
actual="$(sha256sum "$temporary" | awk '{print $1}')"
[[ "$actual" == "${chart[1]}" ]] || {
  echo "error: chart checksum mismatch for $release" >&2
  exit 1
}
mv "$temporary" "$output"
trap - EXIT