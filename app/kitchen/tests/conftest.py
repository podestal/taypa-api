import pytest
from decimal import Decimal

from django.conf import settings
from django.urls import reverse
from model_bakery import baker
from rest_framework.test import APIClient

from core.models import User
from kitchen import models


def pytest_configure():
    """Remove debug_toolbar during tests to avoid namespace errors."""
    if 'debug_toolbar' in settings.INSTALLED_APPS:
        settings.INSTALLED_APPS.remove('debug_toolbar')
    if 'debug_toolbar.middleware.DebugToolbarMiddleware' in settings.MIDDLEWARE:
        settings.MIDDLEWARE.remove('debug_toolbar.middleware.DebugToolbarMiddleware')


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user():
    return baker.make(User, username='kitchenuser', email='kitchen@example.com')


@pytest.fixture
def authenticated_api_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def product():
    return baker.make(
        models.Product,
        name='Tomatoes',
        description='Fresh tomatoes',
        quantity=Decimal('20.00'),
    )


@pytest.fixture
def other_product():
    return baker.make(
        models.Product,
        name='Rice',
        description='White rice',
        quantity=Decimal('5.00'),
    )


@pytest.fixture
def account():
    return baker.make(
        models.Account,
        name='Kitchen Cash',
        balance=Decimal('500.00'),
        is_active=True,
    )


@pytest.fixture
def expense_transaction(account, user):
    return baker.make(
        models.Transaction,
        transaction_type='E',
        account=account,
        amount=Decimal('50.00'),
        description='Manual expense',
        created_by=user,
    )


@pytest.fixture
def inactive_account():
    return baker.make(
        models.Account,
        name='Closed Account',
        balance=Decimal('100.00'),
        is_active=False,
    )


@pytest.fixture
def second_account():
    return baker.make(
        models.Account,
        name='Secondary Cash',
        balance=Decimal('300.00'),
        is_active=True,
    )


@pytest.fixture
def income_transaction(account, user):
    return baker.make(
        models.Transaction,
        transaction_type='I',
        account=account,
        amount=Decimal('100.00'),
        description='Manual income',
        created_by=user,
    )


@pytest.fixture
def purchase(authenticated_api_client, product, account):
    response = authenticated_api_client.post(
        reverse('kitchen-purchase-list'),
        {
            'product': product.id,
            'account': account.id,
            'quantity_bought': '10.00',
            'unit_price': '2.50',
            'notes': 'Weekly stock',
        },
        format='json',
    )
    assert response.status_code == 201
    return models.Purchase.objects.get(pk=response.data['id'])
