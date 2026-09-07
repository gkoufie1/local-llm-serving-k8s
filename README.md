# Local LLM Serving on Kubernetes

The free, CPU-only version of a GPU/EKS MLOps pipeline idea (Argo CD +
Karpenter + Prometheus) that couldn't be built as originally scoped —
no GPU on this hardware. Karpenter specifically doesn't apply here: it's a
node-autoscaler for real cloud clusters, meaningless on a single-node local
`kind` cluster. The honest local substitute for "scale capacity under load"
is the Horizontal Pod Autoscaler, so that's what this demonstrates instead.

Three real, verified pieces: a small open model actually serving inference
requests, real autoscaling under real concurrent load, and real GitOps —
Argo CD created every resource from this git repo, not from a manual
`kubectl apply`.

## Architecture

```
git push -> Argo CD (auto-sync) -> Kubernetes (kind)
                                        |
                                   Deployment (1-6 replicas via HPA)
                                        |
                              +-------------------+
                              | Pod                |
                              |  ollama container   | <- real inference
                              |  (qwen2.5:0.5b,      |    (baked into image)
                              |   baked into image)  |
                              |  gateway container   | <- /generate, /metrics
                              |  (FastAPI + Prometheus client)
                              +-------------------+
```

## Why the model is baked into the image, not pulled at runtime

The obvious approach — an initContainer that runs `ollama pull` against a
shared volume — breaks under autoscaling on a single-node cluster: each new
HPA-triggered replica would need to re-download the ~400MB model before it
could serve anything, making scale-out slow and defeating the point. The
`ollama-image/Dockerfile` here bakes `qwen2.5:0.5b` into the image at build
time instead, so every replica — however many the HPA creates — starts
with the model already present. Verified: a fresh pod's two containers
were both Ready in **8 seconds**.

## Real inference, not a mock

```
$ curl -X POST http://localhost:8000/generate -d '{"prompt":"Explain what a Kubernetes Service does in one sentence."}'
{"response":"A Kubernetes Service is a Kubernetes entity that allows an
application to be deployed and accessed independently and simultaneously."}
```

The gateway's `/metrics` endpoint confirmed the real, CPU-only inference
cost of that single request via its own Prometheus histogram: **~6.96
seconds** — genuinely slow, because this is CPU inference with no GPU, and
the metrics reflect that honestly rather than hiding it.

## HPA under real load — and a real mistake along the way

The first load test used `kubectl port-forward svc/llm-serving` from the
host machine. Result: CPU spiked, the HPA scaled 1 → 4 replicas correctly
— but `kubectl top pods` showed only the *original* pod doing any work; the
three new replicas sat at ~4m CPU, completely idle.

**Why:** `kubectl port-forward` against a Service does not load-balance.
It resolves the Service to a single backing pod once, at the start of the
port-forward session, and tunnels every request to that one pod for the
session's entire lifetime — a real, documented kubectl limitation, not a
bug in the Service or HPA config. It happened to still trigger correct
scaling (that one pod's utilization alone was enough to push the
Deployment's average CPU over target), but it never actually tested whether
load gets distributed across replicas.

**Fix:** ran the load generator *inside* the cluster instead, hitting the
Service by its DNS name (`llm-serving.llm-serving.svc.cluster.local`), so
real kube-proxy load-balancing was exercised. Real result this time —
CPU and traffic genuinely spread across all four pods:

```
llm-serving-84dff49f88-8vhxh   1004m   555Mi
llm-serving-84dff49f88-lfhjc   469m    552Mi
llm-serving-84dff49f88-lt99b   1005m   671Mi
llm-serving-84dff49f88-ppr87   682m    556Mi

HPA:  cpu: 264%/50%   min=1  max=4  replicas=4
```
![image alt](https://github.com/gkoufie1/local-llm-serving-k8s/blob/089725682bada9a5fb2c92e428f59be9db0df239/llm.png)

144 requests fired (12 concurrent workers x 12 requests each): **129
succeeded (200), 15 failed (502)** during the window where demand exceeded
even max capacity (4 replicas, capped for laptop resource limits) — real
backpressure under sustained overload, reported honestly rather than
picking a load level that would hide it.

## Real GitOps, not a claimed one

Argo CD was installed, then pointed at this exact repository's `k8s/`
folder — and *only after that* was the manually-tested namespace deleted,
so what came back was created purely from git, not adopted from
pre-existing state:

```
Application: Synced / Healthy
Resources:
  Namespace                llm-serving   Synced
  Service                  llm-serving   Synced
  Deployment               llm-serving   Synced
  HorizontalPodAutoscaler  llm-serving   Synced
```

Then a real drift test: `k8s/03-hpa.yaml`'s `maxReplicas` was changed from
4 to 6, committed, and pushed. Before sync, the live cluster still showed
`maxReplicas: 4`. After a refresh, Argo CD detected the diff against git
and applied it automatically — live cluster then showed `maxReplicas: 6`,
Application still `Synced / Healthy`.
![image alt](https://github.com/gkoufie1/local-llm-serving-k8s/blob/4a8dd37770b465202728426d6a32ea10e1f8aa5f/gitops.png)

## Cost

Entirely local — `kind`, Docker Desktop, no cloud resources, $0.

## Repository structure

```
gateway/            FastAPI sidecar: /generate, /health, /metrics
ollama-image/        Dockerfile baking qwen2.5:0.5b into ollama/ollama
k8s/                 Namespace, Deployment (2-container pod), Service, HPA
argocd/application.yaml   Points Argo CD at this repo's k8s/ path
load-test/           Host-based and in-cluster load generators
```

## How to run it

```bash
docker build -t llm-gateway:latest ./gateway
docker build -t llm-ollama-baked:latest ./ollama-image
kind load docker-image llm-gateway:latest --name <your-cluster>
kind load docker-image llm-ollama-baked:latest --name <your-cluster>

kubectl apply -f k8s/           # or, for real GitOps:
# kubectl create namespace argocd
# kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml --server-side
# kubectl apply -f argocd/application.yaml
```
