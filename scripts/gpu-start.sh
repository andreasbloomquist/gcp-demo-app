#!/bin/bash
set -euo pipefail

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

echo "Starting GPU VM '$VM_NAME' in zone '$ZONE'..."
gcloud compute instances start "$VM_NAME" \
    --zone="$ZONE" \
    --project="$PROJECT_ID" \
    --quiet

# Wait for RUNNING status
echo "Waiting for VM to reach RUNNING state..."
for i in $(seq 1 30); do
    STATUS=$(gcloud compute instances describe "$VM_NAME" \
        --zone="$ZONE" \
        --project="$PROJECT_ID" \
        --format="value(status)" 2>/dev/null || echo "UNKNOWN")
    if [ "$STATUS" = "RUNNING" ]; then
        echo "VM is RUNNING."
        break
    fi
    echo "  Status: $STATUS (attempt $i/30)"
    sleep 5
done

# Get the new external IP (ephemeral IP may have changed)
EXTERNAL_IP=$(gcloud compute instances describe "$VM_NAME" \
    --zone="$ZONE" \
    --project="$PROJECT_ID" \
    --format="value(networkInterfaces[0].accessConfigs[0].natIP)")

echo "External IP: $EXTERNAL_IP"

# Wait for SSH to be available
echo "Waiting for SSH..."
for i in $(seq 1 20); do
    if gcloud compute ssh "$VM_NAME" \
        --zone="$ZONE" \
        --project="$PROJECT_ID" \
        --command="echo 'SSH ready'" \
        --quiet 2>/dev/null; then
        break
    fi
    echo "  SSH not ready yet (attempt $i/20)"
    sleep 10
done

# Ensure Docker Compose services are running
echo "Ensuring Docker Compose services are up..."
gcloud compute ssh "$VM_NAME" \
    --zone="$ZONE" \
    --project="$PROJECT_ID" \
    --command="cd /opt/gcp-playground && sudo docker compose up -d" \
    --quiet

# Poll health endpoints
echo "Waiting for models to be healthy..."
for i in $(seq 1 40); do
    DISTILBERT_OK=$(curl -sf "http://$EXTERNAL_IP:8001/health" 2>/dev/null | grep -c '"healthy"' || echo "0")
    RESNET_OK=$(curl -sf "http://$EXTERNAL_IP:8002/health" 2>/dev/null | grep -c '"healthy"' || echo "0")

    if [ "$DISTILBERT_OK" = "1" ] && [ "$RESNET_OK" = "1" ]; then
        echo ""
        echo "All models are healthy!"
        echo ""
        echo "GPU VM ready!"
        echo "  DistilBERT:     http://$EXTERNAL_IP:8001"
        echo "  ResNet-50:      http://$EXTERNAL_IP:8002"
        echo "  Metrics Agent:  http://$EXTERNAL_IP:8080/metrics"
        echo "  Prometheus:     http://$EXTERNAL_IP:9090"
        echo ""
        echo "Note: External IP is ephemeral and may have changed."
        echo "Update the webapp's GPU_VM_IP if needed."
        exit 0
    fi

    echo "  Waiting for models... (attempt $i/40)"
    sleep 15
done

echo ""
echo "Warning: Health checks timed out. VM is running but models may still be loading."
echo "  GPU VM IP: $EXTERNAL_IP"
echo "  Check logs: gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID --command='sudo docker compose -f /opt/gcp-playground/docker-compose.yml logs'"
