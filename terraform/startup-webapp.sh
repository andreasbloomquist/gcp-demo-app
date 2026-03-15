#!/bin/bash
set -euo pipefail

exec > >(tee -a /var/log/startup-script.log) 2>&1
echo "=== Webapp VM startup script started at $(date) ==="

# --- Install Docker Engine ---
echo "Installing Docker..."
apt-get update -y
apt-get install -y ca-certificates curl gnupg lsb-release

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | gpg --dearmor --yes -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
  > /etc/apt/sources.list.d/docker.list

apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

systemctl enable docker
systemctl start docker

# --- Clone repo and start webapp ---
echo "Cloning repository..."
cd /opt
if [ -d "gcp-playground" ]; then
  cd gcp-playground && git pull
else
  git clone ${repo_url} gcp-playground
  cd gcp-playground
fi

# Persist GPU_VM_IP so docker compose can read it on restarts
echo "GPU_VM_IP=${gpu_vm_ip}" > /opt/gcp-playground/.env

echo "Starting webapp container..."
docker compose -f webapp-compose.yml up --build -d

echo "=== Webapp VM startup script completed at $(date) ==="
echo "Webapp available at http://$(curl -s http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip -H 'Metadata-Flavor: Google'):5000"
