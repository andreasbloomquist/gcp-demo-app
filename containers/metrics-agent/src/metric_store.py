"""Thread-safe cache for application metrics received via OTLP."""

import logging
import threading

logger = logging.getLogger(__name__)


class MetricEntry:
    """A single metric with its type information and data points."""

    def __init__(self, name: str, description: str, unit: str, metric_type: str, container: str):
        self.name = name
        self.description = description
        self.unit = unit
        self.metric_type = metric_type  # "counter", "gauge", "histogram"
        self.container = container
        self.data_points: list[dict] = []  # Each dict has 'value', 'attributes', 'buckets', etc.


class MetricStore:
    """Thread-safe store for received OTLP metrics, keyed by (container, metric_name)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._metrics: dict[tuple[str, str], MetricEntry] = {}

    def upsert(self, entry: MetricEntry):
        """Insert or update a metric entry."""
        key = (entry.container, entry.name)
        with self._lock:
            self._metrics[key] = entry

    def get_all(self) -> list[MetricEntry]:
        """Return a snapshot of all stored metrics."""
        with self._lock:
            return list(self._metrics.values())

    def clear(self):
        """Clear all stored metrics."""
        with self._lock:
            self._metrics.clear()
