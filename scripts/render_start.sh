#!/usr/bin/env bash
set -euo pipefail

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec waitress-serve --listen="0.0.0.0:${PORT:-10000}" config.wsgi:application
