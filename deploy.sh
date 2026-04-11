#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/deploy.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Error: deploy.env not found. Copy deploy.env.example to deploy.env and update it."
  exit 1
fi

source "$ENV_FILE"

RESTART=true
for arg in "$@"; do
  case "$arg" in
    --no-restart) RESTART=false ;;
    --help|-h)
      echo "Usage: ./deploy.sh [--no-restart]"
      echo "  --no-restart  Sync files without restarting Home Assistant"
      exit 0
      ;;
  esac
done

REMOTE="${HA_USER}@${HA_HOST}"
REMOTE_PATH="${HA_CONFIG_PATH}/custom_components/simple_chores"
SSH_CMD="ssh -p ${HA_PORT}"
SCP_CMD="scp -P ${HA_PORT} -r"

echo "Deploying simple_chores to ${REMOTE}:${REMOTE_PATH}"

# Clean remote directory and copy fresh
$SSH_CMD "${REMOTE}" "rm -rf ${REMOTE_PATH} && mkdir -p ${REMOTE_PATH}"
$SCP_CMD "$SCRIPT_DIR/custom_components/simple_chores/"* "${REMOTE}:${REMOTE_PATH}/"

# Remove __pycache__ on remote
$SSH_CMD "${REMOTE}" "find ${REMOTE_PATH} -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true"

echo "Files synced."

if [[ "$RESTART" == true ]]; then
  echo "Restarting Home Assistant..."
  $SSH_CMD "${REMOTE}" "ha core restart"
  echo "Restart triggered. HA will be back in ~1-2 minutes."
else
  echo "Skipping restart. Remember to restart HA to pick up changes."
fi