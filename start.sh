#!/usr/bin/env bash
# Startup script — runs on every server start.
# Applies any pending migrations before launching gunicorn.

set -o errexit

python manage.py migrate --no-input

exec gunicorn inventory_system.wsgi:application \
  --bind 0.0.0.0:$PORT \
  --workers 2 \
  --timeout 120
