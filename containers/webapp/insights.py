"""Automated insights engine for the observability dashboard.

Fetches Prometheus metrics in parallel, runs statistical analysis
(trend/anomaly/correlation/cost), and returns sorted insight cards.
Uses only stdlib math — no external dependencies.
"""

import math
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import requests

PROMETHEUS_URL = f"http://{os.environ.get('GPU_VM_IP', 'localhost')}:9090"

GPU_TOTAL_MEMORY_MB = 16384  # L4 VRAM

# ── Statistical helpers ─────────────────────────────────────────────

def _clean(values):
    """Filter NaN values (histogram_quantile can produce NaN)."""
    return [v for v in values if v == v and not math.isinf(v)]


def linear_regression_slope(values):
    """Least-squares slope over an evenly-spaced series."""
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n))
    return num / den if den else 0.0


def mean_std(values):
    """Return (mean, std) for a list of numbers."""
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    m = sum(values) / n
    if n < 2:
        return m, 0.0
    variance = sum((v - m) ** 2 for v in values) / n
    return m, math.sqrt(variance)


def zscore_anomaly(values, tail_count=3, warn_z=2.5, crit_z=3.5):
    """Compare last `tail_count` points against the baseline.

    Returns (severity, z_score, tail_mean, baseline_mean).
    severity is None if no anomaly detected.
    """
    if len(values) < tail_count + 5:
        return None, 0.0, 0.0, 0.0
    baseline = values[:-tail_count]
    b_mean, b_std = mean_std(baseline)
    if b_std < 1e-9:
        return None, 0.0, sum(values[-tail_count:]) / tail_count, b_mean
    tail_mean = sum(values[-tail_count:]) / tail_count
    z = abs(tail_mean - b_mean) / b_std
    if z >= crit_z:
        return "critical", z, tail_mean, b_mean
    if z >= warn_z:
        return "warning", z, tail_mean, b_mean
    return None, z, tail_mean, b_mean


# ── Prometheus data fetching ─────────────────────────────────────────

QUERIES = {
    "gpu_util": "gpu_gpu_utilization",
    "gpu_mem": "gpu_memory_used",
    "gpu_temp": "gpu_temp",
    "gpu_mem_util": "gpu_memory_utilization",
    "tensor_active": "gpu_tensor_active",
    "sm_activity": "gpu_sm_activity",
    "distilbert_p95": 'histogram_quantile(0.95, rate(ml_inference_latency_bucket{container="distilbert"}[5m]))',
    "resnet_p95": 'histogram_quantile(0.95, rate(ml_inference_latency_bucket{container="resnet50"}[5m]))',
    "distilbert_rate": 'rate(ml_inference_request_count_total{container="distilbert"}[5m])',
    "resnet_rate": 'rate(ml_inference_request_count_total{container="resnet50"}[5m])',
    "distilbert_errors": 'rate(ml_inference_error_count_total{container="distilbert"}[5m])',
    "resnet_errors": 'rate(ml_inference_error_count_total{container="resnet50"}[5m])',
    "req_rate_total": "sum(rate(ml_inference_request_count_total[5m]))",
    "error_rate_total": "sum(rate(ml_inference_error_count_total[5m]))",
}


def _fetch_one(key, query, start, end, step):
    """Fetch a single range query from Prometheus."""
    try:
        resp = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query_range",
            params={"query": query, "start": str(start), "end": str(end), "step": str(step)},
            timeout=10,
        )
        data = resp.json()
        if data.get("status") == "success" and data["data"]["result"]:
            raw = [float(v[1]) for v in data["data"]["result"][0]["values"]]
            return key, _clean(raw)
    except Exception:
        pass
    return key, []


def fetch_all_metrics(range_seconds, step):
    """Fetch all metrics in parallel. Returns dict of key -> [float]."""
    end = int(time.time())
    start = end - range_seconds
    results = {}

    with ThreadPoolExecutor(max_workers=14) as executor:
        futures = {
            executor.submit(_fetch_one, k, q, start, end, step): k
            for k, q in QUERIES.items()
        }
        for f in as_completed(futures):
            key, values = f.result()
            results[key] = values

    return results


# ── Insight generation ───────────────────────────────────────────────

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def _make_insight(rule_id, severity, category, title, description, metric, current_value=None):
    return {
        "id": rule_id,
        "severity": severity,
        "category": category,
        "title": title,
        "description": description,
        "metric": metric,
        "current_value": current_value,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _eval_trends(metrics, step):
    """Evaluate trend-based rules using linear regression."""
    insights = []

    trend_rules = [
        {
            "id": "gpu-util-trend", "key": "gpu_util", "label": "GPU utilization",
            "metric": "gpu_gpu_utilization", "unit": "%",
            "threshold_pct_per_min": 0.5,
            "saturation_limit": 100, "saturation_label": "GPU will saturate",
        },
        {
            "id": "gpu-mem-trend", "key": "gpu_mem", "label": "GPU memory usage",
            "metric": "gpu_memory_used", "unit": "MB",
            "threshold_pct_per_min": 0.5,
            "high_val": GPU_TOTAL_MEMORY_MB * 0.80,
        },
        {
            "id": "latency-trend-distilbert", "key": "distilbert_p95",
            "label": "DistilBERT P95 latency", "metric": "ml_inference_latency (distilbert P95)",
            "unit": "s", "threshold_pct_per_min": 0.5,
        },
        {
            "id": "latency-trend-resnet", "key": "resnet_p95",
            "label": "ResNet-50 P95 latency", "metric": "ml_inference_latency (resnet50 P95)",
            "unit": "s", "threshold_pct_per_min": 0.5,
        },
        {
            "id": "error-rate-trend", "key": "error_rate_total",
            "label": "Error rate", "metric": "ml_inference_error_count_total",
            "unit": "err/s", "threshold_pct_per_min": 0.0,  # any upward
        },
        {
            "id": "gpu-temp-trend", "key": "gpu_temp",
            "label": "GPU temperature", "metric": "gpu_temp",
            "unit": "°C", "threshold_pct_per_min": 0.5,
        },
    ]

    for rule in trend_rules:
        values = metrics.get(rule["key"], [])
        if len(values) < 5:
            continue

        slope = linear_regression_slope(values)
        if slope <= 0:
            continue

        m, _ = mean_std(values)
        if m < 1e-9:
            continue

        # slope is per data-point; convert to per-minute
        slope_per_min = slope * (60.0 / step) if step else slope
        relative_rate = (slope_per_min / m) * 100  # % of mean per minute

        if relative_rate <= rule["threshold_pct_per_min"]:
            continue

        current = values[-1]
        severity = "info"

        # Escalation logic
        if rule["id"] == "error-rate-trend":
            severity = "warning"
        elif rule["id"] == "gpu-temp-trend" and current > 85:
            severity = "critical"
        elif relative_rate > 1.0:
            severity = "warning"

        # Memory high-water mark
        if rule.get("high_val") and current > rule["high_val"]:
            severity = "warning"

        desc = f"{rule['label']} is trending upward at {relative_rate:.1f}%/min (current: {current:.1f}{rule['unit']})."

        # Saturation projection
        if rule.get("saturation_limit") and slope_per_min > 0:
            remaining = rule["saturation_limit"] - current
            if 0 < remaining:
                minutes = remaining / slope_per_min
                if minutes < 120:
                    desc += f" At this rate, {rule['saturation_label']} in ~{minutes:.0f} minutes."

        insights.append(_make_insight(rule["id"], severity, "trend", f"{rule['label']} trending up", desc, rule["metric"], round(current, 2)))

    return insights


def _eval_anomalies(metrics):
    """Evaluate anomaly-based rules using z-score."""
    insights = []

    anomaly_rules = [
        {"id": "gpu-util-spike", "key": "gpu_util", "label": "GPU utilization spike", "metric": "gpu_gpu_utilization", "unit": "%"},
        {"id": "latency-spike-distilbert", "key": "distilbert_p95", "label": "DistilBERT latency spike", "metric": "ml_inference_latency (distilbert P95)", "unit": "s"},
        {"id": "latency-spike-resnet", "key": "resnet_p95", "label": "ResNet-50 latency spike", "metric": "ml_inference_latency (resnet50 P95)", "unit": "s"},
        {"id": "error-spike", "key": "error_rate_total", "label": "Error rate spike", "metric": "ml_inference_error_count_total", "unit": "err/s", "force_critical": True},
        {"id": "request-rate-drop", "key": "req_rate_total", "label": "Request rate drop", "metric": "ml_inference_request_count_total", "unit": "req/s", "negative": True},
    ]

    for rule in anomaly_rules:
        values = metrics.get(rule["key"], [])
        sev, z, tail_mean, baseline_mean = zscore_anomaly(values)
        if sev is None:
            continue

        if rule.get("force_critical"):
            sev = "critical"

        # For negative anomalies (drops), check direction
        if rule.get("negative"):
            if tail_mean >= baseline_mean:
                continue
            desc = f"{rule['label']}: recent value ({tail_mean:.2f}{rule['unit']}) dropped significantly from baseline ({baseline_mean:.2f}{rule['unit']}), z-score: {z:.1f}."
        else:
            if tail_mean <= baseline_mean:
                continue
            desc = f"{rule['label']}: recent value ({tail_mean:.2f}{rule['unit']}) is unusually high vs baseline ({baseline_mean:.2f}{rule['unit']}), z-score: {z:.1f}."

        insights.append(_make_insight(rule["id"], sev, "anomaly", rule["label"], desc, rule["metric"], round(tail_mean, 2)))

    return insights


def _eval_correlations(metrics):
    """Evaluate correlation-based rules (cross-metric checks)."""
    insights = []

    gpu_vals = metrics.get("gpu_util", [])
    gpu_mean = (sum(gpu_vals) / len(gpu_vals)) if gpu_vals else 0
    gpu_cur = gpu_vals[-1] if gpu_vals else 0

    temp_vals = metrics.get("gpu_temp", [])
    temp_cur = temp_vals[-1] if temp_vals else 0

    mem_vals = metrics.get("gpu_mem", [])
    mem_cur = mem_vals[-1] if mem_vals else 0

    distil_p95 = metrics.get("distilbert_p95", [])
    distil_cur = (distil_p95[-1] * 1000) if distil_p95 else 0  # to ms

    resnet_p95 = metrics.get("resnet_p95", [])
    resnet_cur = (resnet_p95[-1] * 1000) if resnet_p95 else 0

    error_vals = metrics.get("error_rate_total", [])
    error_cur = error_vals[-1] if error_vals else 0

    req_vals = metrics.get("req_rate_total", [])
    req_cur = req_vals[-1] if req_vals else 0
    req_mean = (sum(req_vals) / len(req_vals)) if req_vals else 0
    req_p90 = sorted(req_vals)[int(len(req_vals) * 0.9)] if len(req_vals) > 5 else req_mean

    latency_high = distil_cur > 500 or resnet_cur > 1000  # SLO thresholds in ms

    # GPU saturation — high util AND latency above SLO
    if gpu_cur > 85 and latency_high:
        worst_latency = max(distil_cur, resnet_cur)
        insights.append(_make_insight(
            "gpu-saturation", "critical", "correlation",
            "GPU saturation detected -- inference is bottlenecked",
            f"GPU utilization is at {gpu_cur:.0f}% while inference P95 latency is {worst_latency:.0f}ms (above SLO). The GPU is likely the bottleneck.",
            "gpu_gpu_utilization + ml_inference_latency",
            round(gpu_cur, 1),
        ))

    # Thermal throttling — high temp AND util dropping while requests steady
    if temp_cur > 80 and len(gpu_vals) > 10:
        recent_slope = linear_regression_slope(gpu_vals[-10:])
        if recent_slope < -0.1 and req_cur > 0.1:
            insights.append(_make_insight(
                "thermal-throttling", "critical", "correlation",
                "Possible thermal throttling",
                f"GPU temperature is {temp_cur:.0f}°C while utilization is declining ({gpu_cur:.0f}%) despite steady request rate ({req_cur:.1f} req/s). The GPU may be thermal-throttling.",
                "gpu_temp + gpu_gpu_utilization",
                round(temp_cur, 1),
            ))

    # Memory pressure — high memory AND latency trending up
    if mem_cur > GPU_TOTAL_MEMORY_MB * 0.80 and distil_p95:
        lat_slope = linear_regression_slope(distil_p95)
        if lat_slope > 0:
            insights.append(_make_insight(
                "memory-pressure", "warning", "correlation",
                "Memory pressure may be degrading performance",
                f"GPU memory is at {mem_cur:.0f}MB ({mem_cur/GPU_TOTAL_MEMORY_MB*100:.0f}% of {GPU_TOTAL_MEMORY_MB}MB) and latency is trending up. Memory pressure could be causing swap or eviction overhead.",
                "gpu_memory_used + ml_inference_latency",
                round(mem_cur, 0),
            ))

    # Errors under load — errors > 0 AND request rate above 90th percentile
    if error_cur > 0.01 and req_cur > req_p90 and req_p90 > 0:
        insights.append(_make_insight(
            "error-under-load", "warning", "correlation",
            "Errors increasing under high load",
            f"Error rate is {error_cur:.2f} err/s while request rate ({req_cur:.1f} req/s) is above the 90th percentile ({req_p90:.1f} req/s). The system may be overloaded.",
            "ml_inference_error_count_total + ml_inference_request_count_total",
            round(error_cur, 3),
        ))

    return insights


def _eval_cost(metrics):
    """Evaluate cost/efficiency rules based on mean values."""
    insights = []

    gpu_vals = metrics.get("gpu_util", [])
    gpu_mean = (sum(gpu_vals) / len(gpu_vals)) if gpu_vals else None

    mem_vals = metrics.get("gpu_mem", [])
    mem_peak = max(mem_vals) if mem_vals else None

    tensor_vals = metrics.get("tensor_active", [])
    tensor_mean = (sum(tensor_vals) / len(tensor_vals)) if tensor_vals else None

    if gpu_mean is not None:
        if gpu_mean < 10:
            insights.append(_make_insight(
                "gpu-idle", "info", "cost",
                "GPU is mostly idle",
                f"Mean GPU utilization is {gpu_mean:.1f}% over this time window. Consider suspending the instance when not in use to save costs.",
                "gpu_gpu_utilization", round(gpu_mean, 1),
            ))
        elif gpu_mean < 30:
            insights.append(_make_insight(
                "gpu-underutilized", "info", "cost",
                "GPU is underutilized",
                f"Mean GPU utilization is {gpu_mean:.1f}%. A smaller or shared GPU instance may be more cost-effective.",
                "gpu_gpu_utilization", round(gpu_mean, 1),
            ))

    if mem_peak is not None and mem_peak < GPU_TOTAL_MEMORY_MB * 0.40:
        insights.append(_make_insight(
            "memory-overprovisioned", "info", "cost",
            "GPU memory appears overprovisioned",
            f"Peak GPU memory usage is {mem_peak:.0f}MB ({mem_peak/GPU_TOTAL_MEMORY_MB*100:.0f}% of {GPU_TOTAL_MEMORY_MB}MB). A GPU with less VRAM could work.",
            "gpu_memory_used", round(mem_peak, 0),
        ))

    if tensor_mean is not None and tensor_mean < 5:
        insights.append(_make_insight(
            "tensor-cores-unused", "info", "cost",
            "Tensor cores are mostly unused",
            f"Mean tensor core activity is {tensor_mean:.1f}%. Models may not be using mixed precision (FP16/BF16). Enabling it could improve throughput.",
            "gpu_tensor_active", round(tensor_mean, 1),
        ))

    return insights


def generate_insights(range_seconds=3600, step=30):
    """Main entry point: fetch metrics, run all rules, return sorted insights."""
    metrics = fetch_all_metrics(range_seconds, step)

    insights = []
    insights.extend(_eval_trends(metrics, step))
    insights.extend(_eval_anomalies(metrics))
    insights.extend(_eval_correlations(metrics))
    insights.extend(_eval_cost(metrics))

    # Sort: critical first, then warning, then info
    insights.sort(key=lambda i: SEVERITY_ORDER.get(i["severity"], 99))

    return insights
