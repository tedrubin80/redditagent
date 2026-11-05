#!/bin/sh
set -eu
mkdir -p /app/data
# Bind-mounted host dirs are often owned by the developer; make them writable
# for the non-root runtime user before dropping privileges.
if [ "$(id -u)" = "0" ]; then
  chown -R agent:agent /app/data || true
  exec runuser -u agent -- "$@"
fi
exec "$@"
