import os
import time

import torch
from torchvision.models import ResNet50_Weights, resnet50

_model = None
_weights = None
_load_time = 0.0
_device = None


def load_model() -> float:
    """Load ResNet-50 with ImageNet weights. Returns load time in seconds."""
    global _model, _weights, _load_time, _device

    cache_dir = os.environ.get("MODEL_CACHE_DIR", "/models")
    os.environ["TORCH_HOME"] = cache_dir

    _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    start = time.time()
    _weights = ResNet50_Weights.IMAGENET1K_V2
    _model = resnet50(weights=_weights)
    _model = _model.to(_device)
    _model.eval()
    _load_time = time.time() - start
    return _load_time


def predict(image) -> list[dict]:
    """Run image classification. Returns top-5 predictions as [{'class': str, 'score': float}]."""
    if _model is None:
        raise RuntimeError("Model not loaded")

    preprocess = _weights.transforms()
    batch = preprocess(image).unsqueeze(0).to(_device)

    with torch.no_grad():
        outputs = _model(batch)

    probabilities = torch.nn.functional.softmax(outputs[0], dim=0)
    top5_prob, top5_idx = torch.topk(probabilities, 5)

    categories = _weights.meta["categories"]
    results = []
    for i in range(5):
        results.append({
            "class": categories[top5_idx[i].item()],
            "score": round(top5_prob[i].item(), 4),
        })
    return results


def is_loaded() -> bool:
    return _model is not None
