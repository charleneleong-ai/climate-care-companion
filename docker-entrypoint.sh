#!/bin/bash
# Two processes, one container. Next.js is the only one exposed; the Python core
# listens on loopback because `assess-client.ts` calls it server-side and never
# ships CORE_API_URL to the browser.
#
# bash, not sh: `wait -n` is a bash builtin and Debian's /bin/sh is dash.
#
# Neither process can be the foreground one on its own. If the core dies while
# Next.js keeps serving, every assessment falls through to the 503 path — a site
# that looks up but has quietly stopped answering the only question it exists to
# answer. So a death on either side takes the container down and lets the
# platform restart it.
set -euo pipefail

: "${PORT:=7860}"

stop() {
  # Kill the process group, not the two PIDs — `uv` and `next` are wrappers, and
  # signalling a wrapper orphans the server it spawned.
  trap - TERM INT
  kill 0
}
trap stop TERM INT

uv run --frozen uvicorn api.main:app --host 127.0.0.1 --port 8000 --log-level warning &

cd /app/web/app
./node_modules/.bin/next start --hostname 0.0.0.0 --port "$PORT" &

# Returns as soon as EITHER exits. A bare `wait` would block until both had,
# which is the failure this is here to prevent.
wait -n
status=$?
echo "entrypoint: a process exited (status $status) — stopping the container" >&2
kill 0
exit "$status"
