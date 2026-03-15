#!/bin/bash
set -euo pipefail

# Load config from .env or terraform output
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

if [ -f "$ROOT_DIR/.env" ]; then
    source "$ROOT_DIR/.env"
fi

if [ -z "${PROJECT_ID:-}" ]; then
    PROJECT_ID="$(cd "$ROOT_DIR/terraform" && terraform output -raw project_id 2>/dev/null || echo "")"
fi
if [ -z "${ZONE:-}" ]; then
    ZONE="$(cd "$ROOT_DIR/terraform" && terraform output -raw zone 2>/dev/null || echo "us-central1-a")"
fi
VM_NAME="ml-serving-gpu-vm"

if [ -z "$PROJECT_ID" ]; then
    echo "Error: PROJECT_ID not set. Set it in .env or as an environment variable."
    exit 1
fi

echo "Stopping GPU VM '$VM_NAME' in zone '$ZONE'..."
gcloud compute instances stop "$VM_NAME" \
    --zone="$ZONE" \
    --project="$PROJECT_ID" \
    --quiet

echo ""
echo "GPU VM stopped successfully."
echo "Cost savings: ~\$340/mo (GPU + compute charges stopped)"
echo "Remaining charges: ~\$10/mo (100GB pd-ssd disk)"
echo ""
echo "Docker volumes and model caches are preserved on disk."
echo "Run ./gpu-start.sh to resume."
