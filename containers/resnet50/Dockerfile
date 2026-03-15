FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir torch==2.2.2+cu121 torchvision==0.17.2+cu121 \
    --index-url https://download.pytorch.org/whl/cu121
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./

EXPOSE 8002

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
