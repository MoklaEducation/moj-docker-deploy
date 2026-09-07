#!/usr/bin/env bash
set -euo pipefail

# Safety guard: this script is destructive and should never run accidentally.
# Usage:
#   ALLOW_DESTRUCTIVE=YES_I_UNDERSTAND ./cleanup.sh
if [[ "${ALLOW_DESTRUCTIVE:-}" != "YES_I_UNDERSTAND" ]]; then
	echo "Refusing to run destructive cleanup."
	echo "Set ALLOW_DESTRUCTIVE=YES_I_UNDERSTAND to continue."
	exit 1
fi

echo "This will remove Docker images/volumes and delete dmoj/database."
echo "Type DELETE_PROD_DATA to continue:"
read -r CONFIRM
if [[ "$CONFIRM" != "DELETE_PROD_DATA" ]]; then
	echo "Confirmation did not match. Aborting."
	exit 1
fi

docker system prune -a --volumes -f
docker rmi $(docker images -aq) || true
docker volume rm $(docker volume ls -q) || true

if [[ -d dmoj/database ]]; then
	rm -rf dmoj/database
fi

echo "Destructive cleanup completed."