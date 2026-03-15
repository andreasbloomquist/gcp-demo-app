import os
import time

import torch
from transformers import pipeline

_model = None
_load_time = 0.0

MODEL_NAME = "distilbert-base-uncased-finetuned-sst-2-english"


def load_model() -> float:
    """Load the DistilBERT sentiment analysis model. Returns load time in seconds."""
    global _model, _load_time

    cache_dir = os.environ.get("MODEL_CACHE_DIR", "/models")
    device = 0 if torch.cuda.is_available() else -1

    start = time.time()
    _model = pipeline(
        "sentiment-analysis",
        model=MODEL_NAME,
        device=device,
        model_kwargs={"cache_dir": cache_dir},
    )
    _load_time = time.time() - start
    return _load_time


def predict(text: str) -> dict:
    """Run sentiment analysis. Returns {'label': str, 'score': float}."""
    if _model is None:
        raise RuntimeError("Model not loaded")
    result = _model(text, truncation=True, max_length=512)[0]
    return {"label": result["label"], "score": round(result["score"], 4)}


def is_loaded() -> bool:
    return _model is not None
