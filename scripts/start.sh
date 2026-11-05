#!/usr/bin/env sh
set -eu
if [ ! -f .env ]; then
  echo 'Copy .env.example to .env and edit it first.' >&2
  exit 1
fi
mkdir -p data
if [ ! -f data/settings.json ]; then
  cp config/settings.example.json data/settings.json
  echo 'Created data/settings.json from the example; edit keywords and subreddits.' >&2
fi
docker compose up --build -d
HOST_PORT="${HOST_PORT:-8080}"
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
printf '%s\n' "Dashboard (local):  http://127.0.0.1:${HOST_PORT}"
if [ -n "${IP}" ]; then
  printf '%s\n' "Dashboard (network): http://${IP}:${HOST_PORT}"
fi
