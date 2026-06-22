import pytest
from decimal import Decimal

from django.conf import settings
from django.urls import reverse
from model_bakery import baker
from rest_framework.test import APIClient

from core.models import User
from kitchen import models

TEST_ACCOUNT_PREFIX = '[TEST] '


def pytest_configure():
    """Remove debug_toolbar during tests to avoid namespace errors."""
    if 'debug_toolbar' in settings.INSTALLED_APPS:
        settings.INSTALLED_APPS.remove('debug_toolbar')
    if 'debug_toolbar.middleware.DebugToolbarMiddleware' in settings.MIDDLEWARE:
        settings.MIDDLEWARE.remove('debug_toolbar.middleware.DebugToolbarMiddleware')


@pytest.fixture(scope='session')
def django_db_modify_db_settings():
    """Use a separate test database — config stays here, not in dev.py."""
    db_name = settings.DATABASES['default'].get('NAME', 'database')
    settings.DATABASES['default']['TEST'] = {
        'NAME': f'test_{db_name}',
        'MIRROR': None,
        'CHARSET': None,
        'COLLATION': None,
        'MIGRATE': True,
    }


@pytest.fixture(scope='session', autouse=True)
def enforce_test_database(django_db_setup, django_db_blocker):
    """Refuse to run tests against the development database."""
    with django_db_blocker.unblock():
        db_name = settings.DATABASES['default']['NAME']
        if not db_name.startswith('test_'):
            pytest.fail(
                f'Refusing to run tests on database "{db_name}". '
                'pytest-django should use the test_* database, not your dev database.'
            )


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    return baker.make(
        User,
        username='kitchen_test_user',
        email='kitchen-test@example.com',
    )


@pytest.fixture
def authenticated_api_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def product(db):
    return baker.make(
        models.Product,
        name=f'{TEST_ACCOUNT_PREFIX}Tomatoes',
        description='Fresh tomatoes',
        quantity=Decimal('20.00'),
    )


@pytest.fixture
def other_product(db):
    return baker.make(
        models.Product,
        name=f'{TEST_ACCOUNT_PREFIX}Rice',
        description='White rice',
        quantity=Decimal('5.00'),
    )


@pytest.fixture
def account(db):
    return baker.make(
        models.Account,
        name=f'{TEST_ACCOUNT_PREFIX}Kitchen Cash',
        balance=Decimal('500.00'),
        is_active=True,
    )


@pytest.fixture
def expense_transaction(db, account, user):
    return baker.make(
        models.Transaction,
        transaction_type='E',
        account=account,
        amount=Decimal('50.00'),
        description='Manual expense',
        created_by=user,
    )


@pytest.fixture
def inactive_account(db):
    return baker.make(
        models.Account,
        name=f'{TEST_ACCOUNT_PREFIX}Closed Account',
        balance=Decimal('100.00'),
        is_active=False,
    )


@pytest.fixture
def second_account(db):
    return baker.make(
        models.Account,
        name=f'{TEST_ACCOUNT_PREFIX}Secondary Cash',
        balance=Decimal('300.00'),
        is_active=True,
    )


@pytest.fixture
def income_transaction(db, account, user):
    return baker.make(
        models.Transaction,
        transaction_type='I',
        account=account,
        amount=Decimal('100.00'),
        description='Manual income',
        created_by=user,
    )


@pytest.fixture
def purchase(db, authenticated_api_client, product, account):
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
