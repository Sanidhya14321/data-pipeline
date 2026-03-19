#!/bin/sh
set -e

PORT_VALUE="${PORT:-8080}"

if [ -z "$PORT_VALUE" ]; then
  PORT_VALUE="8080"
fi

exec uvicorn api.main:app --host 0.0.0.0 --port "$PORT_VALUE"
