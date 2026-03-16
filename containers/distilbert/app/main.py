import time

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import model
from telemetry import set_model_load_time, setup_telemetry

app = FastAPI(title="DistilBERT Sentiment Analysis")

inference_latency, request_counter, error_counter, tracer = setup_telemetry(app)


class PredictRequest(BaseModel):
    text: str


class PredictResponse(BaseModel):
    label: str
    score: float
    latency_ms: float


@app.on_event("startup")
def startup():
    load_time = model.load_model()
    set_model_load_time(load_time)


@app.get("/health")
def health():
    return {"status": "healthy", "model_loaded": model.is_loaded()}


@app.post("/predict", response_model=PredictResponse)
def predict(request: PredictRequest):
    with tracer.start_as_current_span("distilbert.inference"):
        start = time.time()
        request_counter.add(1, {"model": "distilbert"})
        try:
            result = model.predict(request.text)
        except Exception as e:
            error_counter.add(1, {"model": "distilbert", "error_type": type(e).__name__})
            raise HTTPException(status_code=500, detail=str(e))
        latency = time.time() - start
        inference_latency.record(latency, {"model": "distilbert"})

    return PredictResponse(
        label=result["label"],
        score=result["score"],
        latency_ms=round(latency * 1000, 2),
    )
