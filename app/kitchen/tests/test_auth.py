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

    def test_create_product_requires_authentication(self, api_client):
        response = api_client.post(
            reverse('kitchen-product-list'),
            {'name': 'Onions'},
            format='json',
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_account_requires_authentication(self, api_client):
        response = api_client.post(
            reverse('kitchen-account-list'),
            {'name': 'Petty Cash', 'balance': '100.00'},
            format='json',
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_transaction_requires_authentication(self, api_client, account):
        response = api_client.post(
            reverse('kitchen-transaction-list'),
            {
                'transaction_type': 'I',
                'account': account.id,
                'amount': '25.00',
            },
            format='json',
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_purchase_requires_authentication(self, api_client, account, product):
        response = api_client.post(
            reverse('kitchen-purchase-list'),
            {
                'product': product.id,
                'account': account.id,
                'quantity_bought': '2.00',
                'unit_price': '3.00',
            },
            format='json',
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
