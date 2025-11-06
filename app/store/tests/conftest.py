import pytest
from decimal import Decimal
from model_bakery import baker
from rest_framework.test import APIClient
from django.conf import settings

from store import models
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
def category():
    """Create a test category"""
    return baker.make(models.Category, name='Test Category', is_active=True)


@pytest.fixture
def dish(category):
    """Create a test dish"""
    return baker.make(
        models.Dish,
        name='Test Dish',
        description='Test Description',
        price=Decimal('19.99'),
        category=category,
        is_active=True
    )


@pytest.fixture
def customer():
    """Create a test customer"""
    return baker.make(
        models.Customer,
        first_name='John',
        last_name='Doe',
        phone_number='1234567890'
    )


@pytest.fixture
def address(customer):
    """Create a test address"""
    return baker.make(
        models.Address,
        street='123 Main St',
        reference='Apt 4B',
        customer=customer,
        is_primary=False
    )


@pytest.fixture
def account(user):
    """Create a test account"""
    return baker.make(
        models.Account,
        name='Test Account',
        balance=Decimal('1000.00'),
        account_type='CH',
        is_active=True
    )


@pytest.fixture
def transaction(account, user, category):
    """Create a test transaction"""
    return baker.make(
        models.Transaction,
        transaction_type='I',  # Income
        account=account,
        amount=Decimal('100.00'),
        category=category,
        description='Test transaction',
        created_by=user
    )

