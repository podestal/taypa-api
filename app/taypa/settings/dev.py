from .base import *
import os

DEBUG = True
ALLOWED_HOSTS = ["*"]

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

CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "https://sub.example.com",
    "http://localhost:8080",
    "http://127.0.0.1:9000",
]