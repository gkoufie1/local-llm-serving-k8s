#!/bin/sh
URL="http://llm-serving.llm-serving.svc.cluster.local:8000/generate"
BODY='{"prompt":"Write one sentence about container orchestration."}'

for i in $(seq 1 12); do
  (
    for j in $(seq 1 12); do
      code=$(curl -s -X POST "$URL" -H "Content-Type: application/json" -d "$BODY" -o /dev/null -w "%{http_code}")
      echo "worker $i req $j -> $code"
    done
  ) &
done
wait
echo "load generation complete"
