import pytest
from datetime import date
from decimal import Decimal

from django.urls import reverse
from model_bakery import baker
from rest_framework import status

from kitchen import models


@pytest.mark.django_db
class TestKitchenTransactionCreate:
    def test_create_income_updates_account_balance(
        self, authenticated_api_client, account, user
    ):
        initial_balance = account.balance
        url = reverse('kitchen-transaction-list')
        payload = {
            'transaction_type': 'I',
            'account': account.id,
            'amount': '75.00',
            'description': 'Opening top-up',
            'transaction_date': str(date.today()),
        }

        response = authenticated_api_client.post(url, payload, format='json')

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['transaction_type'] == 'I'
        assert response.data['amount'] == '75.00'
        assert response.data['created_by'] == user.id

        account.refresh_from_db()
        assert account.balance == initial_balance + Decimal('75.00')

    def test_create_expense_updates_account_balance(
        self, authenticated_api_client, account
    ):
        initial_balance = account.balance
        url = reverse('kitchen-transaction-list')
        payload = {
            'transaction_type': 'E',
            'account': account.id,
            'amount': '40.00',
            'description': 'Cleaning supplies',
            'transaction_date': str(date.today()),
        }

        response = authenticated_api_client.post(url, payload, format='json')

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['transaction_type'] == 'E'

        account.refresh_from_db()
        assert account.balance == initial_balance - Decimal('40.00')


@pytest.mark.django_db
class TestKitchenTransactionUpdate:
    def test_update_amount_corrects_account_balance(
        self, authenticated_api_client, expense_transaction, account
    ):
        account.refresh_from_db()
        balance_after_create = account.balance
        url = reverse('kitchen-transaction-detail', kwargs={'pk': expense_transaction.id})

        response = authenticated_api_client.patch(
            url,
            {'amount': '80.00'},
            format='json',
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data['amount'] == '80.00'

        account.refresh_from_db()
        assert account.balance == balance_after_create - Decimal('30.00')

    def test_update_type_corrects_account_balance(
        self, authenticated_api_client, income_transaction, account
    ):
        account.refresh_from_db()
        balance_after_create = account.balance
        url = reverse('kitchen-transaction-detail', kwargs={'pk': income_transaction.id})

        response = authenticated_api_client.patch(
            url,
            {'transaction_type': 'E'},
            format='json',
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data['transaction_type'] == 'E'

        account.refresh_from_db()
        expected_balance = balance_after_create - (income_transaction.amount * 2)
        assert account.balance == expected_balance


@pytest.mark.django_db
class TestKitchenTransactionDelete:
    def test_delete_income_reverses_account_balance(
        self, authenticated_api_client, account, user
    ):
        transaction = baker.make(
            models.Transaction,
            transaction_type='I',
            account=account,
            amount=Decimal('120.00'),
            created_by=user,
        )
        account.refresh_from_db()
        balance_after_create = account.balance
        url = reverse('kitchen-transaction-detail', kwargs={'pk': transaction.id})

        response = authenticated_api_client.delete(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not models.Transaction.objects.filter(pk=transaction.id).exists()

        account.refresh_from_db()
        assert account.balance == balance_after_create - Decimal('120.00')

    def test_delete_expense_reverses_account_balance(
        self, authenticated_api_client, account, user
    ):
        transaction = baker.make(
            models.Transaction,
            transaction_type='E',
            account=account,
            amount=Decimal('35.00'),
            created_by=user,
        )
        account.refresh_from_db()
        balance_after_create = account.balance
        url = reverse('kitchen-transaction-detail', kwargs={'pk': transaction.id})

        response = authenticated_api_client.delete(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT

        account.refresh_from_db()
        assert account.balance == balance_after_create + Decimal('35.00')
