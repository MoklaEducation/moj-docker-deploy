#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K3S_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPO_DIR="$(cd "$K3S_DIR/../.." && pwd)"
REQUIREMENTS="$SCRIPT_DIR/controller-requirements.txt"
COLLECTIONS="$K3S_DIR/host/requirements.yml"
VALIDATE="$SCRIPT_DIR/controller_validate.py"

usage() {
  cat <<'EOF'
Usage:
  ./execution/k3s/operations/setup/controller.sh check
  ./execution/k3s/operations/setup/controller.sh install

check    Verify the local controller prerequisites without changing the machine.
install  Install age through apt and the pinned Ansible collections. SOPS and
         Python dependencies are verified but are not downloaded automatically.
EOF
}

die() {
  echo "error: $1" >&2
  exit 1
}

check_command() {
  command -v "$1" >/dev/null 2>&1 || die "missing command: $1"
}

check() {
  for command in bash python3 ansible-playbook ansible-galaxy age sops; do
    check_command "$command"
  done
  python3 "$VALIDATE" --python-requirements "$REQUIREMENTS" --collection-requirements "$COLLECTIONS" || die "Pinned Python dependencies or Ansible collections do not match repository requirements"
  echo "controller prerequisites: pass"
}

install() {
  check_command sudo
  check_command ansible-galaxy
  sudo apt-get update
  sudo apt-get install --yes age
  ansible-galaxy collection install --requirements-file "$COLLECTIONS" --force
  echo "Installed age and pinned Ansible collections."
  echo "SOPS and Python dependencies still require explicit, verified setup."
}

action="${1:-}"
case "$action" in
  check) (($# == 1)) || die "check accepts no additional arguments"; check ;;
  install) (($# == 1)) || die "install accepts no additional arguments"; install ;;
  --help|-h) usage ;;
  *) usage >&2; exit 2 ;;
esac