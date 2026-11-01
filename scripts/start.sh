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
printf '%s\n' 'Dashboard: http://127.0.0.1:8080'
