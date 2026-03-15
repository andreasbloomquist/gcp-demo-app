import asyncio
import base64
import io
import time

import httpx
from fastapi import FastAPI, HTTPException
from PIL import Image
from pydantic import BaseModel

import model
from telemetry import set_model_load_time, setup_telemetry

app = FastAPI(title="ResNet-50 Image Classification")

inference_latency, request_counter, tracer = setup_telemetry(app)


class PredictRequest(BaseModel):
    image_url: str | None = None
    image_base64: str | None = None


class Prediction(BaseModel):
    class_name: str
    score: float


class PredictResponse(BaseModel):
    predictions: list[Prediction]
    latency_ms: float


@app.on_event("startup")
def startup():
    load_time = model.load_model()
    set_model_load_time(load_time)


@app.get("/health")
def health():
    return {"status": "healthy", "model_loaded": model.is_loaded()}


@app.post("/predict", response_model=PredictResponse)
async def predict(request: PredictRequest):
    if not request.image_url and not request.image_base64:
        raise HTTPException(status_code=400, detail="Provide image_url or image_base64")

    with tracer.start_as_current_span("resnet50.inference") as span:
        start = time.time()
        request_counter.add(1, {"model": "resnet50"})
        try:
            if request.image_url:
                span.set_attribute("input.type", "url")
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.get(request.image_url)
                    resp.raise_for_status()
                    image = Image.open(io.BytesIO(resp.content)).convert("RGB")
            else:
                span.set_attribute("input.type", "base64")
                image_data = base64.b64decode(request.image_base64)
                image = Image.open(io.BytesIO(image_data)).convert("RGB")

            results = await asyncio.to_thread(model.predict, image)
        except httpx.HTTPError as e:
            raise HTTPException(status_code=400, detail=f"Failed to fetch image: {e}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

        latency = time.time() - start
        inference_latency.record(latency, {"model": "resnet50"})

    return PredictResponse(
        predictions=[Prediction(class_name=r["class"], score=r["score"]) for r in results],
        latency_ms=round(latency * 1000, 2),
    )
