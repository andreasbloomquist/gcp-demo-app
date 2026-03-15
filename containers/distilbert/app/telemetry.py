import os
import time

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_model_load_time: float = 0.0


def set_model_load_time(t: float) -> None:
    global _model_load_time
    _model_load_time = t


def _model_load_time_callback(_options):
    yield metrics.Observation(value=_model_load_time)


def setup_telemetry(app) -> tuple:
    """Initialize OTel metrics and traces, instrument FastAPI, return (meter, tracer)."""
    service_name = os.environ.get("OTEL_SERVICE_NAME", "distilbert")
    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://metrics-agent:4317")

    resource = Resource.create({"service.name": service_name})

    # Traces
    trace_provider = TracerProvider(resource=resource)
    trace_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True))
    )
    trace.set_tracer_provider(trace_provider)
    tracer = trace.get_tracer(service_name)

    # Metrics
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True),
        export_interval_millis=10000,
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)
    meter = metrics.get_meter(service_name)

    # Custom metrics
    inference_latency = meter.create_histogram(
        name="ml.inference.latency",
        description="Model inference latency in seconds",
        unit="s",
    )
    request_counter = meter.create_counter(
        name="ml.inference.request_count",
        description="Total inference requests",
    )
    meter.create_observable_gauge(
        name="ml.model.load_time",
        description="Time taken to load the model in seconds",
        unit="s",
        callbacks=[_model_load_time_callback],
    )

    # Auto-instrument FastAPI
    FastAPIInstrumentor.instrument_app(app)

    return inference_latency, request_counter, tracer
