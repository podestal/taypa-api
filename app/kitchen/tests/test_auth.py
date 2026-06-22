import pytest
from django.urls import reverse
from rest_framework import status


@pytest.mark.django_db
class TestKitchenAuthentication:
    """All kitchen endpoints require authentication."""

    @pytest.mark.parametrize(
        'url_name',
        [
            'kitchen-product-list',
            'kitchen-account-list',
            'kitchen-transaction-list',
            'kitchen-purchase-list',
        ],
    )
    def test_list_requires_authentication(self, api_client, url_name):
        url = reverse(url_name)
        response = api_client.get(url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.parametrize(
        'url_name,method',
        [
            ('kitchen-product-list', 'post'),
            ('kitchen-account-list', 'post'),
            ('kitchen-transaction-list', 'post'),
            ('kitchen-purchase-list', 'post'),
        ],
    )
    def test_create_requires_authentication(self, api_client, account, product, url_name, method):
        url = reverse(url_name)
        payload = {}

        if url_name == 'kitchen-product-list':
            payload = {'name': 'Onions', 'quantity': '0.00'}
        elif url_name == 'kitchen-account-list':
            payload = {'name': 'Petty Cash', 'balance': '100.00'}
        elif url_name == 'kitchen-transaction-list':
            payload = {
                'transaction_type': 'I',
                'account': account.id,
                'amount': '25.00',
            }
        elif url_name == 'kitchen-purchase-list':
            payload = {
                'product': product.id,
                'account': account.id,
                'quantity_bought': '2.00',
                'unit_price': '3.00',
            }

        response = getattr(api_client, method)(url, payload, format='json')

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
