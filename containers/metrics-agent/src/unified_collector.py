"""Custom prometheus_client Collector that unifies GPU metrics and app metrics."""

import logging

from prometheus_client.core import (
    CounterMetricFamily,
    GaugeMetricFamily,
    HistogramMetricFamily,
)

from .config import Config
from .gpu_collector import GPUCollector
from .metric_store import MetricStore

logger = logging.getLogger(__name__)


def _sanitize_label_name(name: str) -> str:
    """Convert OTel attribute keys (e.g. 'http.method') to valid Prometheus label names."""
    return name.replace(".", "_").replace("-", "_")


class UnifiedCollector:
    """Prometheus Collector that yields GPU + app metrics on each scrape."""

    def __init__(self, gpu_collector: GPUCollector, metric_store: MetricStore):
        self._gpu = gpu_collector
        self._store = metric_store
        self._common_labels = Config.common_labels()

    def describe(self):
        # Return empty to indicate dynamic metrics
        return []

    def collect(self):
        """Called by prometheus_client on each /metrics scrape."""
        yield from self._collect_gpu_metrics()
        yield from self._collect_app_metrics()

    def _collect_gpu_metrics(self):
        gpu_metrics = self._gpu.get_metrics()
        label_names = list(self._common_labels.keys()) + ["container", "gpu"]
        label_values = list(self._common_labels.values()) + ["metrics-agent", "0"]

        for metric_name, value in gpu_metrics.items():
            g = GaugeMetricFamily(
                metric_name,
                f"GPU metric: {metric_name}",
                labels=label_names,
            )
            g.add_metric(label_values, value)
            yield g

    def _collect_app_metrics(self):
        entries = self._store.get_all()
        common_label_names = list(self._common_labels.keys())
        common_label_values = list(self._common_labels.values())

        for entry in entries:
            try:
                if entry.metric_type == "counter":
                    yield from self._emit_counter(entry, common_label_names, common_label_values)
                elif entry.metric_type == "gauge":
                    yield from self._emit_gauge(entry, common_label_names, common_label_values)
                elif entry.metric_type == "histogram":
                    yield from self._emit_histogram(entry, common_label_names, common_label_values)
            except Exception:
                logger.exception("Error collecting metric %s", entry.name)

    def _emit_counter(self, entry, common_label_names, common_label_values):
        for dp in entry.data_points:
            label_names = common_label_names + ["container"] + [_sanitize_label_name(k) for k in dp["attributes"].keys()]
            c = CounterMetricFamily(
                entry.name.replace(".", "_"),
                entry.description or entry.name,
                labels=label_names,
            )
            label_values = common_label_values + [entry.container] + list(dp["attributes"].values())
            c.add_metric(label_values, dp["value"])
            yield c

    def _emit_gauge(self, entry, common_label_names, common_label_values):
        for dp in entry.data_points:
            label_names = common_label_names + ["container"] + [_sanitize_label_name(k) for k in dp["attributes"].keys()]
            g = GaugeMetricFamily(
                entry.name.replace(".", "_"),
                entry.description or entry.name,
                labels=label_names,
            )
            label_values = common_label_values + [entry.container] + list(dp["attributes"].values())
            g.add_metric(label_values, dp["value"])
            yield g

    def _emit_histogram(self, entry, common_label_names, common_label_values):
        for dp in entry.data_points:
            label_names = common_label_names + ["container"] + [_sanitize_label_name(k) for k in dp["attributes"].keys()]
            h = HistogramMetricFamily(
                entry.name.replace(".", "_"),
                entry.description or entry.name,
                labels=label_names,
            )
            buckets = dp.get("buckets", [])
            label_values = common_label_values + [entry.container] + list(dp["attributes"].values())
            h.add_metric(
                label_values,
                buckets=buckets,
                sum_value=dp.get("sum", 0),
            )
            yield h
