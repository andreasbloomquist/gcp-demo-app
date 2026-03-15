import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

GPU_VM_IP = os.environ.get("GPU_VM_IP", "localhost")
DISTILBERT_URL = f"http://{GPU_VM_IP}:8001"
RESNET50_URL = f"http://{GPU_VM_IP}:8002"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/sentiment", methods=["POST"])
def sentiment():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid or missing JSON body"}), 400
    text = data.get("text", "")
    if not text:
        return jsonify({"error": "No text provided"}), 400

    try:
        start = time.time()
        resp = requests.post(
            f"{DISTILBERT_URL}/predict",
            json={"text": text},
            timeout=30,
        )
        total_time = time.time() - start
        resp.raise_for_status()
        result = resp.json()
        result["total_latency_ms"] = round(total_time * 1000, 2)
        return jsonify(result)
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/classify", methods=["POST"])
def classify():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid or missing JSON body"}), 400
    image_url = data.get("image_url", "")
    if not image_url:
        return jsonify({"error": "No image_url provided"}), 400

    try:
        start = time.time()
        resp = requests.post(
            f"{RESNET50_URL}/predict",
            json={"image_url": image_url},
            timeout=60,
        )
        total_time = time.time() - start
        resp.raise_for_status()
        result = resp.json()
        result["total_latency_ms"] = round(total_time * 1000, 2)
        return jsonify(result)
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 502


def _make_request(endpoint, payload):
    """Make a single request and return timing info."""
    start = time.time()
    try:
        resp = requests.post(endpoint, json=payload, timeout=60)
        latency = time.time() - start
        return {"latency": latency, "status": resp.status_code, "error": None}
    except Exception as e:
        latency = time.time() - start
        return {"latency": latency, "status": 0, "error": str(e)}


@app.route("/api/load-test", methods=["POST"])
def load_test():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid or missing JSON body"}), 400
    model = data.get("model", "distilbert")
    try:
        num_requests = min(int(data.get("num_requests", 10)), 500)
        concurrency = min(int(data.get("concurrency", 5)), 50)
    except (ValueError, TypeError):
        return jsonify({"error": "num_requests and concurrency must be numbers"}), 400

    if model == "distilbert":
        endpoint = f"{DISTILBERT_URL}/predict"
        payload = {"text": "This is a test sentence for load testing the sentiment analysis model."}
    else:
        endpoint = f"{RESNET50_URL}/predict"
        payload = {"image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4d/Cat_November_2010-1a.jpg/1200px-Cat_November_2010-1a.jpg"}

    results = []
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(_make_request, endpoint, payload) for _ in range(num_requests)]
        for future in as_completed(futures):
            results.append(future.result())

    latencies = sorted([r["latency"] for r in results])
    errors = sum(1 for r in results if r["error"] or r["status"] != 200)

    stats = {
        "total_requests": num_requests,
        "concurrency": concurrency,
        "errors": errors,
        "avg_latency_ms": round(sum(latencies) / len(latencies) * 1000, 2) if latencies else 0,
        "p50_latency_ms": round(latencies[len(latencies) // 2] * 1000, 2) if latencies else 0,
        "p95_latency_ms": round(latencies[int(len(latencies) * 0.95)] * 1000, 2) if latencies else 0,
        "p99_latency_ms": round(latencies[int(len(latencies) * 0.99)] * 1000, 2) if latencies else 0,
    }
    return jsonify(stats)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
