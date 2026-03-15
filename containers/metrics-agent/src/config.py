import os


class Config:
    """Environment-based configuration for the metrics agent."""

    INSTANCE_TYPE: str = os.environ.get("INSTANCE_TYPE", "n1-standard-8")
    CLOUD_PROVIDER: str = os.environ.get("CLOUD_PROVIDER", "gcp")
    GPU_POLL_INTERVAL: int = int(os.environ.get("GPU_POLL_INTERVAL", "5"))
    PROMETHEUS_PORT: int = int(os.environ.get("PROMETHEUS_PORT", "8080"))
    OTLP_GRPC_PORT: int = int(os.environ.get("OTLP_GRPC_PORT", "4317"))

    @classmethod
    def common_labels(cls) -> dict[str, str]:
        """Labels applied to all metrics."""
        return {
            "instance_type": cls.INSTANCE_TYPE,
            "cloud_provider": cls.CLOUD_PROVIDER,
        }
