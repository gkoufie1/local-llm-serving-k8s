"""
Fires concurrent real inference requests at the gateway (via
`kubectl port-forward svc/llm-serving 8000:8000 -n llm-serving`) to drive
genuine CPU load on the Ollama container, so the HPA has something real to
react to.
"""
import time
import concurrent.futures
import requests

URL = "http://localhost:8000/generate"
PROMPTS = [
    "Explain what a load balancer does in two sentences.",
    "Write a haiku about Kubernetes.",
    "List three benefits of horizontal pod autoscaling.",
    "What is the difference between a Deployment and a StatefulSet?",
]

DURATION_SECONDS = 90
CONCURRENCY = 12


def fire_one(i):
    prompt = PROMPTS[i % len(PROMPTS)]
    start = time.time()
    try:
        resp = requests.post(URL, json={"prompt": prompt}, timeout=60)
        return resp.status_code, round(time.time() - start, 2)
    except Exception as e:
        return "ERR", str(e)


if __name__ == "__main__":
    print(f"Firing {CONCURRENCY} concurrent requests for {DURATION_SECONDS}s...")
    end_time = time.time() + DURATION_SECONDS
    completed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = set()
        i = 0
        while time.time() < end_time or futures:
            while len(futures) < CONCURRENCY and time.time() < end_time:
                futures.add(pool.submit(fire_one, i))
                i += 1
            done, futures = concurrent.futures.wait(
                futures, timeout=1, return_when=concurrent.futures.FIRST_COMPLETED
            )
            for f in done:
                status, elapsed = f.result()
                completed += 1
                print(f"  request {completed}: status={status} time={elapsed}s")

    print(f"\nDone. {completed} requests completed.")
