# Bakes the model into the image at build time, so every autoscaled
# replica starts with it already present — no re-download per pod, no
# shared PVC needed across replicas.
FROM ollama/ollama:latest

RUN (ollama serve &) && \
    sleep 5 && \
    ollama pull qwen2.5:0.5b && \
    sleep 2

ENTRYPOINT ["ollama", "serve"]
