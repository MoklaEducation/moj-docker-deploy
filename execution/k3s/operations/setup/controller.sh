#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K3S_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
REQUIREMENTS="$SCRIPT_DIR/controller-requirements.txt"
COLLECTIONS="$K3S_DIR/host/requirements.yml"
VALIDATE="$SCRIPT_DIR/controller_validate.py"
CONTROLLER_VENV="$K3S_DIR/.controller-venv"
SOPS_VERSION="3.9.4"
SOPS_AMD64_SHA256="5488e32bc471de7982ad895dd054bbab3ab91c417a118426134551e9626e4e85"
SOPS_DOWNLOAD="$CONTROLLER_VENV/bin/.sops-download"
HELM_VERSION="3.18.6"
HELM_AMD64_SHA256="3f43c0aa57243852dd542493a0f54f1396c0bc8ec7296bbb2c01e802010819ce"
HELM_DOWNLOAD="$CONTROLLER_VENV/.helm-download.tar.gz"
HELM_EXTRACT_DIR="$CONTROLLER_VENV/.helm-extract"
MISSING_COLLECTION_REQUIREMENTS="$CONTROLLER_VENV/.missing-collection-requirements.yml"

if [[ -x "$CONTROLLER_VENV/bin/python3" ]]; then
  export PATH="$CONTROLLER_VENV/bin:$PATH"
fi

usage() {
  cat <<'EOF'
Usage:
  ./execution/k3s/operations/setup/controller.sh check
  ./execution/k3s/operations/setup/controller.sh install

check    Verify the local controller prerequisites without changing the machine.
install  Install pinned Python dependencies, age, SOPS, Helm, and Ansible collections.
EOF
}

die() {
  echo "error: $1" >&2
  exit 1
}

cleanup_install_files() {
  rm -rf "$HELM_EXTRACT_DIR"
  rm -f "$SOPS_DOWNLOAD" "$HELM_DOWNLOAD" "$MISSING_COLLECTION_REQUIREMENTS"
}

check_command() {
  command -v "$1" >/dev/null 2>&1 || die "missing command: $1"
}

check() {
  for command in bash python3 ansible-playbook ansible-galaxy age sops helm; do
    check_command "$command"
  done
  [[ "$(helm version --template '{{.Version}}')" == "v${HELM_VERSION}" ]] || \
    die "Helm must be v${HELM_VERSION}"
  python3 "$VALIDATE" --python-requirements "$REQUIREMENTS" --collection-requirements "$COLLECTIONS" || die "Pinned Python dependencies or Ansible collections do not match repository requirements"
  echo "controller prerequisites: pass"
}

install_sops() {
  if [[ -x "$CONTROLLER_VENV/bin/sops" ]] && \
      [[ "$(sha256sum "$CONTROLLER_VENV/bin/sops" | awk '{print $1}')" == "$SOPS_AMD64_SHA256" ]]; then
    return
  fi
  if command -v sops >/dev/null 2>&1 && [[ "$(sops --version 2>/dev/null)" == "sops ${SOPS_VERSION}"* ]]; then
    return
  fi
  [[ "$(uname -m)" == "x86_64" ]] || die "automatic SOPS installation currently supports x86_64 only"
  for command in chmod curl mv sha256sum; do
    check_command "$command"
  done
  rm -f "$SOPS_DOWNLOAD"
  if ! curl --fail --location --silent --show-error \
      --output "$SOPS_DOWNLOAD" \
      "https://github.com/getsops/sops/releases/download/v${SOPS_VERSION}/sops-v${SOPS_VERSION}.linux.amd64"; then
    die "failed to download SOPS ${SOPS_VERSION}"
  fi
  if [[ "$(sha256sum "$SOPS_DOWNLOAD" | awk '{print $1}')" != "$SOPS_AMD64_SHA256" ]]; then
    die "SOPS ${SOPS_VERSION} checksum verification failed"
  fi
  chmod 0755 "$SOPS_DOWNLOAD"
  mv "$SOPS_DOWNLOAD" "$CONTROLLER_VENV/bin/sops"
}

install_helm() {
  if command -v helm >/dev/null 2>&1 && \
      [[ "$(helm version --template '{{.Version}}' 2>/dev/null)" == "v${HELM_VERSION}" ]]; then
    return
  fi
  [[ "$(uname -m)" == "x86_64" ]] || die "automatic Helm installation currently supports x86_64 only"
  for command in curl mkdir mv rm sha256sum tar; do
    check_command "$command"
  done
  rm -rf "$HELM_EXTRACT_DIR"
  rm -f "$HELM_DOWNLOAD"
  if ! curl --fail --location --silent --show-error \
      --output "$HELM_DOWNLOAD" \
      "https://get.helm.sh/helm-v${HELM_VERSION}-linux-amd64.tar.gz"; then
    die "failed to download Helm ${HELM_VERSION}"
  fi
  if [[ "$(sha256sum "$HELM_DOWNLOAD" | awk '{print $1}')" != "$HELM_AMD64_SHA256" ]]; then
    die "Helm ${HELM_VERSION} checksum verification failed"
  fi
  mkdir -p "$HELM_EXTRACT_DIR"
  tar -xzf "$HELM_DOWNLOAD" -C "$HELM_EXTRACT_DIR" linux-amd64/helm
  chmod 0755 "$HELM_EXTRACT_DIR/linux-amd64/helm"
  mv "$HELM_EXTRACT_DIR/linux-amd64/helm" "$CONTROLLER_VENV/bin/helm"
}

install() {
  check_command sudo
  check_command python3
  check_command flock
  mkdir -p "$CONTROLLER_VENV"
  exec 9>"$CONTROLLER_VENV/.install.lock"
  flock --nonblock 9 || die "another controller installation is already running"
  trap cleanup_install_files EXIT
  trap 'exit 130' INT TERM

  if [[ ! -x "$CONTROLLER_VENV/bin/python3" ]]; then
    python3 -m venv "$CONTROLLER_VENV"
  fi
  if ! "$CONTROLLER_VENV/bin/python3" "$VALIDATE" --python-requirements "$REQUIREMENTS"; then
    "$CONTROLLER_VENV/bin/python3" -m pip install --requirement "$REQUIREMENTS"
  fi
  export PATH="$CONTROLLER_VENV/bin:$PATH"
  if ! command -v age >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install --yes age
  fi
  install_sops
  install_helm
  if ! python3 "$VALIDATE" --collection-requirements "$COLLECTIONS"; then
    python3 "$VALIDATE" \
      --collection-requirements "$COLLECTIONS" \
      --write-missing-collection-requirements "$MISSING_COLLECTION_REQUIREMENTS"
    ansible-galaxy collection install --requirements-file "$MISSING_COLLECTION_REQUIREMENTS" --force
  fi
  check
  cleanup_install_files
  trap - EXIT INT TERM
  echo "Controller prerequisites are installed and match pinned requirements."
}

action="${1:-}"
case "$action" in
  check) (($# == 1)) || die "check accepts no additional arguments"; check ;;
  install) (($# == 1)) || die "install accepts no additional arguments"; install ;;
  --help|-h) usage ;;
  *) usage >&2; exit 2 ;;
esac