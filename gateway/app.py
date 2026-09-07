"""
Thin sidecar in front of Ollama: proxies real inference requests and
exposes Prometheus metrics. Runs in the same pod as the ollama container,
talking to it over localhost — no network hop, no extra Service needed
just for this.
"""
import time
import requests
from fastapi import FastAPI, Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from pydantic import BaseModel

app = FastAPI()

REQUEST_COUNT = Counter("llm_requests_total", "Total generate requests", ["status"])
REQUEST_LATENCY = Histogram("llm_request_latency_seconds", "Time spent generating a response")

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:0.5b"


class GenerateRequest(BaseModel):
    prompt: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/generate")
def generate(req: GenerateRequest):
    start = time.time()
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": MODEL, "prompt": req.prompt, "stream": False},
            timeout=60,
        )
        resp.raise_for_status()
        REQUEST_COUNT.labels(status="ok").inc()
        REQUEST_LATENCY.observe(time.time() - start)
        return {"response": resp.json().get("response", "")}
    except Exception as e:
        REQUEST_COUNT.labels(status="error").inc()
        REQUEST_LATENCY.observe(time.time() - start)
        return Response(content=str(e), status_code=502)
