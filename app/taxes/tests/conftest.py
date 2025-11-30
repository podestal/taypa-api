import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from model_bakery import baker
from rest_framework.test import APIClient
from django.conf import settings

from taxes.models import Document
from core.models import User


# Remove debug_toolbar from INSTALLED_APPS during tests to avoid namespace errors
def pytest_configure():
    """Configure pytest - remove debug_toolbar during tests"""
    if 'debug_toolbar' in settings.INSTALLED_APPS:
        settings.INSTALLED_APPS.remove('debug_toolbar')
    if 'debug_toolbar.middleware.DebugToolbarMiddleware' in settings.MIDDLEWARE:
        settings.MIDDLEWARE.remove('debug_toolbar.middleware.DebugToolbarMiddleware')


@pytest.fixture
def api_client():
    """API client for making requests (unauthenticated)"""
    return APIClient()


@pytest.fixture
def user():
    """Create a test user"""
    return baker.make(User, username='testuser', email='test@example.com')


@pytest.fixture
def authenticated_api_client(user):
    """API client authenticated with a test user"""
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def document_invoice():
    """Create a test invoice document (type 01)"""
    return baker.make(
        Document,
        document_type='01',
        serie='F001',
        numero='00000001',
        sunat_id='test-sunat-id-001',
        sunat_status='ACEPTADO',
        status='accepted',
        amount=Decimal('118.00'),
        sunat_issue_time=int(datetime.now().timestamp() * 1000),
    )


@pytest.fixture
def document_ticket():
    """Create a test ticket document (type 03)"""
    return baker.make(
        Document,
        document_type='03',
        serie='B001',
        numero='00000001',
        sunat_id='test-sunat-id-002',
        sunat_status='ACEPTADO',
        status='accepted',
        amount=Decimal('59.00'),
        sunat_issue_time=int(datetime.now().timestamp() * 1000),
    )


@pytest.fixture
def document_invoice_pending():
    """Create a pending invoice document without sunat_issue_time"""
    return baker.make(
        Document,
        document_type='01',
        serie='F001',
        numero='00000002',
        sunat_id='test-sunat-id-003',
        sunat_status='PENDIENTE',
        status='pending',
        amount=Decimal('120.00'),
        sunat_issue_time=None,  # NULL - should appear first in ordering
    )


@pytest.fixture
def document_ticket_pending():
    """Create a pending ticket document without sunat_issue_time"""
    return baker.make(
        Document,
        document_type='03',
        serie='B001',
        numero='00000002',
        sunat_id='test-sunat-id-004',
        sunat_status='PENDIENTE',
        status='pending',
        amount=Decimal('60.00'),
        sunat_issue_time=None,  # NULL - should appear first in ordering
    )

