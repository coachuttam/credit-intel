#!/bin/sh
# Measures the service inside the container under its real memory limit (PRD FR-018 criterion 12).
#   export CREDIT_INTEL_API_TOKEN=<the token of the env file>
#   deploy/measure_container.sh <public.pdf> [number of submissions at once]
# It submits the document the given number of times at once, waits for every run to end, and prints only: each run's final status (state, code, file names:
# no document text), the seconds from the first submission to the last end, the container's peak memory and whether the kernel killed anything in it.
# Each submission sends the document's statement pages to the hosted model and costs a few thousandths of a dollar: only a public document, with the owner's approval.
set -eu

pdf=${1:?give the path of a public PDF}
count=${2:-1}
: "${CREDIT_INTEL_API_TOKEN:?export CREDIT_INTEL_API_TOKEN (the token in the env file)}"
base=${CREDIT_INTEL_URL:-http://127.0.0.1:8000}
container=${CREDIT_INTEL_CONTAINER:-credit-intel-credit-intel-1}
auth="Authorization: Bearer $CREDIT_INTEL_API_TOKEN"

cgroup() { docker exec "$container" cat "/sys/fs/cgroup/$1" 2>/dev/null || echo unavailable; }

started=$(date +%s)
ids=""
i=0
while [ "$i" -lt "$count" ]; do
  answer=$(curl -s -H "$auth" -F "file=@$pdf" -F confirm_public_document=true "$base/runs") || { echo "submission failed" >&2; exit 1; }
  id=$(printf '%s' "$answer" | sed -n 's/.*"run_id":"\([^"]*\)".*/\1/p')
  if [ -z "$id" ]; then
    echo "submission $((i + 1)) was not accepted: $answer" >&2   # a catalogued code and message: no document text
    exit 1
  fi
  ids="$ids $id"
  i=$((i + 1))
done

for id in $ids; do
  while :; do
    status=$(curl -s -H "$auth" "$base/runs/$id")
    case "$status" in
      *'"state":"exported"'* | *'"state":"failed"'*) break ;;
    esac
    sleep 2
  done
  echo "run $id: $status"
done
ended=$(date +%s)

echo "seconds, first submission to last end: $((ended - started))"
peak=$(cgroup memory.peak)
case "$peak" in
  unavailable) echo "container peak memory: unavailable (needs cgroup v2 and a recent kernel)" ;;
  *) echo "container peak memory: $((peak / 1048576)) MB" ;;
esac
echo "kernel memory events: $(cgroup memory.events | tr '\n' ' ')"
echo "memory limit of the container: $(cgroup memory.max)"
