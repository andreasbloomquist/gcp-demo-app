"""gRPC OTLP MetricsService receiver that parses incoming metrics into MetricStore."""

import logging
from concurrent import futures

import grpc
from opentelemetry.proto.collector.metrics.v1 import (
    metrics_service_pb2,
    metrics_service_pb2_grpc,
)
from opentelemetry.proto.metrics.v1 import metrics_pb2

from .metric_store import MetricEntry, MetricStore

logger = logging.getLogger(__name__)


class OTLPMetricsServicer(metrics_service_pb2_grpc.MetricsServiceServicer):
    """Implements the OTLP MetricsService.Export RPC."""

    def __init__(self, store: MetricStore):
        self._store = store

    def Export(self, request, context):
        try:
            self._process_request(request)
        except Exception:
            logger.exception("Error processing OTLP metrics export")
        return metrics_service_pb2.ExportMetricsServiceResponse()

    def _process_request(self, request):
        for resource_metrics in request.resource_metrics:
            # Extract service.name from resource attributes
            container = "unknown"
            for attr in resource_metrics.resource.attributes:
                if attr.key == "service.name":
                    container = attr.value.string_value
                    break

            for scope_metrics in resource_metrics.scope_metrics:
                for metric in scope_metrics.metrics:
                    self._process_metric(metric, container)

    def _process_metric(self, metric, container: str):
        name = metric.name
        description = metric.description
        unit = metric.unit

        if metric.HasField("sum"):
            self._process_sum(name, description, unit, metric.sum, container)
        elif metric.HasField("gauge"):
            self._process_gauge(name, description, unit, metric.gauge, container)
        elif metric.HasField("histogram"):
            self._process_histogram(name, description, unit, metric.histogram, container)

    def _process_sum(self, name, description, unit, sum_data, container):
        is_monotonic = sum_data.is_monotonic
        metric_type = "counter" if is_monotonic else "gauge"

        entry = MetricEntry(name, description, unit, metric_type, container)
        for dp in sum_data.data_points:
            attributes = {attr.key: attr.value.string_value for attr in dp.attributes}
            value = dp.as_double if dp.HasField("as_double") else float(dp.as_int)
            entry.data_points.append({"value": value, "attributes": attributes})

        self._store.upsert(entry)

    def _process_gauge(self, name, description, unit, gauge_data, container):
        entry = MetricEntry(name, description, unit, "gauge", container)
        for dp in gauge_data.data_points:
            attributes = {attr.key: attr.value.string_value for attr in dp.attributes}
            value = dp.as_double if dp.HasField("as_double") else float(dp.as_int)
            entry.data_points.append({"value": value, "attributes": attributes})

        self._store.upsert(entry)

    def _process_histogram(self, name, description, unit, hist_data, container):
        entry = MetricEntry(name, description, unit, "histogram", container)
        for dp in hist_data.data_points:
            attributes = {attr.key: attr.value.string_value for attr in dp.attributes}

            # Convert explicit bounds to cumulative bucket counts
            explicit_bounds = list(dp.explicit_bounds)
            bucket_counts = list(dp.bucket_counts)

            cumulative_buckets = []
            cumulative = 0
            for i, count in enumerate(bucket_counts):
                cumulative += count
                if i < len(explicit_bounds):
                    cumulative_buckets.append((str(explicit_bounds[i]), cumulative))
                else:
                    # +Inf bucket
                    cumulative_buckets.append(("+Inf", cumulative))

            entry.data_points.append({
                "attributes": attributes,
                "buckets": cumulative_buckets,
                "count": dp.count,
                "sum": dp.sum,
            })

        self._store.upsert(entry)


def start_otlp_receiver(store: MetricStore, port: int) -> grpc.Server:
    """Start the gRPC OTLP metrics receiver server."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    metrics_service_pb2_grpc.add_MetricsServiceServicer_to_server(
        OTLPMetricsServicer(store), server
    )
    server.add_insecure_port(f"0.0.0.0:{port}")
    server.start()
    logger.info("OTLP gRPC receiver listening on port %d", port)
    return server
