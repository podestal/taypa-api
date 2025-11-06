"""
URL configuration for taypa project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from django.conf.urls import include
from django.conf import settings
import os
import sys

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('store.urls')),
    path('auth/', include('djoser.urls')),
    path('auth/', include('djoser.urls.jwt')),
]

# Only include debug toolbar URLs if DEBUG is True and debug_toolbar is installed
# Skip in test environment to avoid namespace errors
if settings.DEBUG and 'debug_toolbar' in settings.INSTALLED_APPS:
    try:
        # Detect if we're running tests - pytest-django sets this
        is_testing = (
            'PYTEST_CURRENT_TEST' in os.environ or
            any('pytest' in str(arg).lower() for arg in getattr(sys, 'argv', []))
        )
        
        if not is_testing:
            import debug_toolbar
            try:
                urlpatterns = [
                    path("__debug__/", include(debug_toolbar.urls)),
                ] + urlpatterns
            except Exception:
                # If there's any issue with debug toolbar URLs (e.g., namespace errors in tests)
                # just skip it
                pass
    except (ImportError, Exception):
        # Silently fail if debug_toolbar is not available or has issues
        pass
