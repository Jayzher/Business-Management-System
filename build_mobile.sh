#!/usr/bin/env bash
# Mobile API build script — runs before the mobile API service starts on Render

set -o errexit

pip install -r requirements.txt

# Use mobile settings for this service
export DJANGO_SETTINGS_MODULE=inventory_system.mobile_settings

python manage.py collectstatic --no-input
python manage.py migrate --no-input
