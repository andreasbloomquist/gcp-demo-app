FROM nvidia/cuda:12.2.2-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install DCGM and Python
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        software-properties-common \
        curl \
        gnupg2 \
        python3 \
        python3-pip \
        python3-dev && \
    # Add DCGM repository
    curl -fsSL https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb \
        -o /tmp/cuda-keyring.deb && \
    dpkg -i /tmp/cuda-keyring.deb && \
    apt-get update && \
    apt-get install -y --no-install-recommends datacenter-gpu-manager && \
    rm -rf /var/lib/apt/lists/* /tmp/*

# DCGM Python bindings location
ENV PYTHONPATH="${PYTHONPATH}:/usr/local/dcgm/bindings/python3"

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY src/ ./src/

EXPOSE 8080 4317

CMD ["python3", "-m", "src.main"]
