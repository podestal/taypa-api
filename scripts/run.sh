#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

# Wait for the database to be ready before continuing.
python manage.py wait_for_db

# Collect static files (CSS, JS, etc.) without prompting for input.
# python manage.py collectstatic --noinput

# Apply any pending database migrations.
python manage.py migrate

# Start the uWSGI server with 4 worker processes, using the WSGI module.
# --socket :9000: Binds to port 9000.
# --workers 4: Spawns 4 worker processes to handle requests.
# --master: Enables the master process to manage workers.
# --enable-threads: Allows threads to be used within worker processes.
# --module app.wsgi: Specifies the WSGI application module (app.wsgi) to use.
# gunicorn moneyTracker.wsgi:application --bind 0.0.0.0:8000
# daphne -b 0.0.0.0 -p 8000 taypa.asgi:application
# gunicorn taypa.wsgi:application --bind 0.0.0.0:8000 --timeout=5 --threads=10

if [ "$ENVIRONMENT" = "development" ]; then
    echo "Starting server with Daphne for development..."
    exec python manage.py runserver 0.0.0.0:8000
else
    echo "Starting server with Gunicorn for production..."
    exec gunicorn taypa.wsgi:application --bind 0.0.0.0:8000 --timeout=5 --threads=10
fi
