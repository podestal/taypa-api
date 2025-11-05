from .base import *
import os

DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS += ["debug_toolbar"]

MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]

# For Docker, we need to allow all IPs or use a function to detect IP
# Debug Toolbar checks INTERNAL_IPS to determine if it should show
INTERNAL_IPS = [
    "127.0.0.1",
    "localhost",
    "0.0.0.0",
]

# Function to show toolbar - bypasses INTERNAL_IPS check for Docker
def show_toolbar(request):
    """
    Show toolbar in development mode.
    This bypasses INTERNAL_IPS check which can be problematic in Docker.
    Simply returns DEBUG value, so toolbar shows when DEBUG=True.
    """
    return DEBUG

# Configure debug toolbar
DEBUG_TOOLBAR_CONFIG = {
    "SHOW_TOOLBAR_CALLBACK": show_toolbar,
    "INTERCEPT_REDIRECTS": False,
    "SHOW_COLLAPSED": True,
}

# Use PostgreSQL for production
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": os.environ.get("DB_HOST"),
        "NAME": os.environ.get("DB_NAME"),
        "USER": os.environ.get("DB_USER"),
        "PASSWORD": os.environ.get("DB_PASS"),
    }
}

CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]
CORS_ALLOWED_ORIGINS.extend(
    filter(None, os.environ.get("DJANGO_CORS_ALLOWED_ORIGINS", "").split(","))
)

CORS_ALLOW_CREDENTIALS = True
