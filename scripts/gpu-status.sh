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

STATUS=$(gcloud compute instances describe "$VM_NAME" \
    --zone="$ZONE" \
    --project="$PROJECT_ID" \
    --format="value(status)" 2>/dev/null || echo "NOT_FOUND")

echo "GPU VM Status: $STATUS"
echo ""

if [ "$STATUS" = "RUNNING" ]; then
    EXTERNAL_IP=$(gcloud compute instances describe "$VM_NAME" \
        --zone="$ZONE" \
        --project="$PROJECT_ID" \
        --format="value(networkInterfaces[0].accessConfigs[0].natIP)")

    echo "External IP: $EXTERNAL_IP"
    echo ""

    # Check health endpoints
    echo "Service Health:"
    DISTILBERT=$(curl -sf "http://$EXTERNAL_IP:8001/health" 2>/dev/null || echo '{"status":"unreachable"}')
    echo "  DistilBERT (:8001): $DISTILBERT"

    RESNET=$(curl -sf "http://$EXTERNAL_IP:8002/health" 2>/dev/null || echo '{"status":"unreachable"}')
    echo "  ResNet-50  (:8002): $RESNET"

    METRICS=$(curl -sf "http://$EXTERNAL_IP:8080/metrics" 2>/dev/null | head -1 || echo "unreachable")
    if [ "$METRICS" != "unreachable" ]; then
        echo "  Metrics Agent (:8080): OK"
    else
        echo "  Metrics Agent (:8080): unreachable"
    fi

    PROM=$(curl -sf "http://$EXTERNAL_IP:9090/-/healthy" 2>/dev/null || echo "unreachable")
    if [ "$PROM" != "unreachable" ]; then
        echo "  Prometheus (:9090): OK"
    else
        echo "  Prometheus (:9090): unreachable"
    fi

    # Show GPU utilization
    echo ""
    echo "GPU Utilization:"
    gcloud compute ssh "$VM_NAME" \
        --zone="$ZONE" \
        --project="$PROJECT_ID" \
        --command="nvidia-smi --query-gpu=utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu,power.draw --format=csv" \
        --quiet 2>/dev/null || echo "  Unable to query GPU (SSH may not be ready)"

elif [ "$STATUS" = "TERMINATED" ]; then
    echo "VM is stopped. Run ./gpu-start.sh to resume."
    echo "Estimated cost while stopped: ~\$10/mo (disk only)"
elif [ "$STATUS" = "NOT_FOUND" ]; then
    echo "VM not found. Run 'terraform apply' to create it."
else
    echo "VM is in state: $STATUS"
fi
