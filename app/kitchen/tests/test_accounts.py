import pytest
from decimal import Decimal

from django.urls import reverse
from rest_framework import status

from kitchen import models


@pytest.mark.django_db
class TestAccountEdgeCases:
    def test_create_account_with_zero_balance(self, authenticated_api_client):
        response = authenticated_api_client.post(
            reverse('kitchen-account-list'),
            {'name': 'Empty Petty Cash', 'balance': '0.00'},
            format='json',
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['balance'] == '0.00'

    def test_expense_can_drive_account_balance_negative(
        self, authenticated_api_client, account
    ):
        url = reverse('kitchen-transaction-list')
        response = authenticated_api_client.post(
            url,
            {
                'transaction_type': 'E',
                'account': account.id,
                'amount': '600.00',
            },
            format='json',
        )

        assert response.status_code == status.HTTP_201_CREATED
        account.refresh_from_db()
        assert account.balance == Decimal('-100.00')

    def test_multiple_transactions_net_balance_correctly(
        self, authenticated_api_client, account
    ):
        initial_balance = account.balance
        url = reverse('kitchen-transaction-list')

        authenticated_api_client.post(
            url,
            {'transaction_type': 'I', 'account': account.id, 'amount': '200.00'},
            format='json',
        )
        authenticated_api_client.post(
            url,
            {'transaction_type': 'E', 'account': account.id, 'amount': '75.00'},
            format='json',
        )
        authenticated_api_client.post(
            url,
            {'transaction_type': 'E', 'account': account.id, 'amount': '25.00'},
            format='json',
        )

        account.refresh_from_db()
        assert account.balance == initial_balance + Decimal('100.00')

    def test_deactivate_account_still_retrievable(self, authenticated_api_client, inactive_account):
        url = reverse('kitchen-account-detail', kwargs={'pk': inactive_account.id})
        response = authenticated_api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['is_active'] is False
