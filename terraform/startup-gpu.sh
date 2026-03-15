#!/bin/bash
set -euo pipefail

exec > >(tee -a /var/log/startup-script.log) 2>&1
echo "=== GPU VM startup script started at $(date) ==="

# If NVIDIA driver is already installed and loaded, skip to Docker Compose
if nvidia-smi &>/dev/null; then
    echo "NVIDIA driver already loaded, skipping install phase."
    cd /opt/gcp-playground
    docker compose up --build -d
    echo "=== GPU VM startup script completed at $(date) ==="
    exit 0
fi

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

# --- Install NVIDIA Drivers ---
echo "Installing NVIDIA drivers..."
apt-get install -y linux-headers-$(uname -r)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  > /etc/apt/sources.list.d/nvidia-container-toolkit.list

apt-get update -y

# Install NVIDIA driver
apt-get install -y nvidia-driver-535

# Install NVIDIA Container Toolkit
apt-get install -y nvidia-container-toolkit
nvidia-ctk runtime configure --runtime=docker
systemctl restart docker

# --- Clone repo ---
echo "Cloning repository..."
cd /opt
if [ -d "gcp-playground" ]; then
  cd gcp-playground && git pull
else
  git clone ${repo_url} gcp-playground
  cd gcp-playground
fi

# Reboot to load the NVIDIA kernel module; startup script re-runs on boot
# and the nvidia-smi check at the top will skip to docker compose up
echo "NVIDIA driver installed. Rebooting to load kernel module..."
reboot
