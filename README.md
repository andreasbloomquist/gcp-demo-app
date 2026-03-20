# ML Serving Platform on GCP

A GPU-accelerated machine learning inference platform deployed on Google Cloud Platform. Serves two models (DistilBERT for sentiment analysis, ResNet-50 for image classification) with full observability — metrics collection, Prometheus monitoring, an interactive dashboard, and an automated insights engine.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Webapp VM (CPU)                                                │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Flask Webapp (:5001)                                     │  │
│  │  - Inference UI (sentiment analysis, image classification)│  │
│  │  - Observability Dashboard (charts, stat cards, insights) │  │
│  │  - Load Testing                                           │  │
│  │  - Automated Insights Engine (trend/anomaly/correlation)  │  │
│  └───────────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP
┌──────────────────────────▼──────────────────────────────────────┐
│  GPU VM (NVIDIA L4 / T4)                                        │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐  │
│  │  DistilBERT   │  │  ResNet-50   │  │  Metrics Agent        │  │
│  │  FastAPI      │  │  FastAPI     │  │  - DCGM GPU metrics   │  │
│  │  :8001        │  │  :8002       │  │  - OTLP receiver      │  │
│  │  Sentiment    │  │  Image       │  │  - Prometheus :8080   │  │
│  │  Analysis     │  │  Classifier  │  │                       │  │
│  └──────┬────────┘  └──────┬───────┘  └───────────┬───────────┘  │
│         │  OTel metrics    │  OTel metrics         │              │
│         └──────────────────┴───────────────────────┘              │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  Prometheus (:9090)  —  scrapes metrics-agent every 15s    │  │
│  └─────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

## Features

### Inference
- **DistilBERT** — sentiment analysis on text input (positive/negative with confidence score)
- **ResNet-50** — image classification from URL (top-5 predictions with probabilities)
- **Load Testing** — configurable concurrent request load tests against either model

### Observability Dashboard
- **Health Overview** — stat cards for GPU utilization, memory, temperature, P95 latency, request/error rates
- **Inference Performance** — latency percentile charts (P50/P95/P99), request rates, error rates per model
- **GPU Utilization** — core/memory utilization, SM/Tensor/DRAM activity profiling
- **GPU Hardware** — temperature, power draw, memory usage over time
- Auto-refresh every 15 seconds with configurable time ranges (15m / 1h / 6h / 24h)

### Automated Insights Engine
Server-side analysis of Prometheus metrics that surfaces actionable findings:
- **Trend Detection** — linear regression on GPU utilization, memory, latency, error rates, temperature; includes saturation time projection
- **Anomaly Detection** — z-score analysis to detect spikes in latency, GPU utilization, error rates, or drops in request rate
- **Correlation Detection** — cross-metric rules for GPU saturation bottlenecks, thermal throttling, memory pressure, errors under load
- **Cost/Efficiency** — flags idle/underutilized GPU, overprovisioned memory, unused tensor cores

### Metrics Pipeline
- **OpenTelemetry** instrumentation in each model container (histograms, counters, gauges)
- **Metrics Agent** — collects DCGM GPU metrics + receives OTLP from model containers, exposes unified Prometheus endpoint
- **Prometheus** — scrapes and stores all metrics with 7-day retention

## Project Structure

```
.
├── containers/
│   ├── distilbert/          # DistilBERT sentiment analysis service
│   │   ├── app/
│   │   │   ├── main.py      # FastAPI endpoints
│   │   │   ├── model.py     # Model loading and inference
│   │   │   └── telemetry.py # OpenTelemetry setup
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── resnet50/            # ResNet-50 image classification service
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── model.py
│   │   │   └── telemetry.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── metrics-agent/       # GPU metrics + OTLP receiver
│   │   ├── src/
│   │   │   ├── main.py
│   │   │   ├── gpu_collector.py
│   │   │   ├── unified_collector.py
│   │   │   ├── otlp_receiver.py
│   │   │   ├── metric_store.py
│   │   │   └── config.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   └── webapp/              # Flask web application
│       ├── app.py           # Routes (inference, dashboard, insights API)
│       ├── insights.py      # Automated insights engine
│       ├── templates/
│       │   ├── index.html   # Inference UI
│       │   └── dashboard.html # Observability dashboard
│       ├── Dockerfile
│       └── requirements.txt
├── prometheus/
│   └── prometheus.yml       # Prometheus scrape config
├── terraform/               # GCP infrastructure as code
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   ├── terraform.tfvars.example
│   ├── startup-gpu.sh       # GPU VM bootstrap script
│   └── startup-webapp.sh    # Webapp VM bootstrap script
├── scripts/                 # Helper scripts
│   ├── gpu-start.sh
│   ├── gpu-stop.sh
│   └── gpu-status.sh
├── docker-compose.yml       # GPU VM services (models + metrics + prometheus)
└── webapp-compose.yml       # Webapp VM services (flask app)
```

## Prerequisites

- [Terraform](https://www.terraform.io/) >= 1.0
- [Google Cloud SDK](https://cloud.google.com/sdk) (`gcloud`) authenticated
- A GCP project with Compute Engine API enabled
- GPU quota in your desired region (L4 or T4)

## Deployment

### 1. Configure Terraform

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` with your GCP project ID, region, zone, and repo URL.

### 2. Deploy Infrastructure

```bash
terraform init
terraform plan
terraform apply
```

This creates:
- **GPU VM** — runs the ML models, metrics agent, and Prometheus
- **Webapp VM** — runs the Flask web application
- Firewall rules for ports 5001, 8001, 8002, 8080, 9090

The GPU VM will automatically install NVIDIA drivers, Docker, clone the repo, and start all containers. It reboots once to load the NVIDIA kernel module, then starts services on the second boot.

### 3. Access the Application

After deployment (allow 5-10 minutes for GPU driver install + model downloads):

- **Inference UI**: `http://<webapp-vm-ip>:5001`
- **Dashboard**: `http://<webapp-vm-ip>:5001/dashboard`
- **Prometheus**: `http://<gpu-vm-ip>:9090`

Get VM IPs:
```bash
terraform output
```

## Local Development

Run the webapp locally (connects to a remote GPU VM):

```bash
GPU_VM_IP=<gpu-vm-ip> docker compose -f webapp-compose.yml up --build -d
```

The webapp will be available at `http://localhost:5001`.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Inference UI |
| `/dashboard` | GET | Observability dashboard |
| `/api/sentiment` | POST | DistilBERT sentiment analysis |
| `/api/classify` | POST | ResNet-50 image classification |
| `/api/load-test` | POST | Run load test against a model |
| `/api/insights` | GET | Automated insights (trend/anomaly/correlation/cost) |
| `/api/prometheus/query` | GET | Proxy to Prometheus instant query |
| `/api/prometheus/query_range` | GET | Proxy to Prometheus range query |

## Cost Management

The GPU VM is the primary cost driver. Use the helper scripts to manage it:

```bash
# Stop GPU VM (stops billing for compute, keeps disk)
./scripts/gpu-stop.sh

# Start GPU VM
./scripts/gpu-start.sh

# Check status
./scripts/gpu-status.sh
```

The automated insights engine will flag cost optimization opportunities (idle GPU, underutilized resources, overprovisioned memory).

## Tech Stack

- **ML Frameworks**: PyTorch, Hugging Face Transformers, TorchVision
- **Serving**: FastAPI + Uvicorn
- **Web App**: Flask + Gunicorn
- **Metrics**: OpenTelemetry SDK, DCGM (NVIDIA Data Center GPU Manager)
- **Monitoring**: Prometheus
- **Visualization**: Chart.js
- **Infrastructure**: Terraform, Docker Compose, GCP Compute Engine
- **GPU**: NVIDIA L4/T4 with CUDA 12.2
