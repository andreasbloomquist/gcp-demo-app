"""Unified Metrics Agent entry point.

Starts three concurrent subsystems:
1. GPU Collector - background thread polling GPU metrics via DCGM/pynvml
2. OTLP gRPC Receiver - receives app metrics from model containers
3. Prometheus HTTP Server - serves unified metrics on /metrics
"""

import logging
import signal
import sys
import time

from prometheus_client import REGISTRY, start_http_server

from .config import Config
from .gpu_collector import GPUCollector
from .metric_store import MetricStore
from .otlp_receiver import start_otlp_receiver
from .unified_collector import UnifiedCollector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("metrics-agent")


def main():
    logger.info("Starting Unified Metrics Agent")
    logger.info("Config: instance_type=%s, cloud_provider=%s", Config.INSTANCE_TYPE, Config.CLOUD_PROVIDER)

    # Initialize components
    metric_store = MetricStore()
    gpu_collector = GPUCollector(poll_interval=Config.GPU_POLL_INTERVAL)
    unified_collector = UnifiedCollector(gpu_collector, metric_store)

    # Register custom collector with Prometheus registry
    REGISTRY.register(unified_collector)

    # Start GPU polling
    gpu_collector.start()

    # Start OTLP gRPC receiver
    grpc_server = start_otlp_receiver(metric_store, Config.OTLP_GRPC_PORT)

    # Start Prometheus HTTP server
    start_http_server(Config.PROMETHEUS_PORT)
    logger.info("Prometheus metrics server listening on port %d", Config.PROMETHEUS_PORT)

    # Handle shutdown
    def shutdown(signum, frame):
        logger.info("Shutting down...")
        gpu_collector.stop()
        grpc_server.stop(grace=5)
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    logger.info("Unified Metrics Agent is running")

    # Keep main thread alive
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
