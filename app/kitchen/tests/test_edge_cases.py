import pytest
from decimal import Decimal

from django.urls import reverse
from rest_framework import status

from kitchen import models


def _create_purchase(client, product, account, **overrides):
    payload = {
        'product': product.id,
        'account': account.id,
        'quantity_bought': '10.00',
        'unit_price': '2.50',
    }
    payload.update(overrides)
    return client.post(reverse('kitchen-purchase-list'), payload, format='json')


@pytest.mark.django_db
class TestTransactionEdgeCases:
    def test_create_transaction_missing_required_fields(self, authenticated_api_client, account):
        response = authenticated_api_client.post(
            reverse('kitchen-transaction-list'),
            {'account': account.id},
            format='json',
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_transaction_invalid_type(self, authenticated_api_client, account):
        response = authenticated_api_client.post(
            reverse('kitchen-transaction-list'),
            {
                'transaction_type': 'X',
                'account': account.id,
                'amount': '10.00',
            },
            format='json',
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_transaction_with_zero_amount(self, authenticated_api_client, account):
        initial_balance = account.balance
        response = authenticated_api_client.post(
            reverse('kitchen-transaction-list'),
            {
                'transaction_type': 'E',
                'account': account.id,
                'amount': '0.00',
            },
            format='json',
        )

        assert response.status_code == status.HTTP_201_CREATED
        account.refresh_from_db()
        assert account.balance == initial_balance

    def test_delete_transaction_linked_to_purchase_returns_400(
        self, authenticated_api_client, purchase
    ):
        url = reverse('kitchen-transaction-detail', kwargs={'pk': purchase.transaction_id})
        response = authenticated_api_client.delete(url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'purchase' in response.data['error'].lower()
        assert models.Transaction.objects.filter(pk=purchase.transaction_id).exists()
        assert models.Purchase.objects.filter(pk=purchase.id).exists()

    def test_update_transaction_linked_to_purchase_changes_balance_only(
        self, authenticated_api_client, purchase, account
    ):
        account.refresh_from_db()
        balance_before = account.balance
        url = reverse('kitchen-transaction-detail', kwargs={'pk': purchase.transaction_id})

        response = authenticated_api_client.patch(
            url,
            {'amount': '40.00'},
            format='json',
        )

        assert response.status_code == status.HTTP_200_OK
        purchase.refresh_from_db()
        account.refresh_from_db()

        assert purchase.subtotal == Decimal('25.00')
        assert account.balance == balance_before - Decimal('15.00')

    def test_move_transaction_between_accounts_updates_both_balances(
        self, authenticated_api_client, expense_transaction, account, second_account
    ):
        account.refresh_from_db()
        second_account.refresh_from_db()
        account_balance_before = account.balance
        second_balance_before = second_account.balance
        url = reverse('kitchen-transaction-detail', kwargs={'pk': expense_transaction.id})

        response = authenticated_api_client.patch(
            url,
            {'account': second_account.id},
            format='json',
        )

        assert response.status_code == status.HTTP_200_OK
        account.refresh_from_db()
        second_account.refresh_from_db()
        assert account.balance == account_balance_before + expense_transaction.amount
        assert second_account.balance == second_balance_before - expense_transaction.amount


@pytest.mark.django_db
class TestPurchaseEdgeCases:
    def test_create_purchase_with_inactive_account_returns_400(
        self, authenticated_api_client, product, inactive_account
    ):
        response = _create_purchase(
            authenticated_api_client,
            product,
            inactive_account,
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'account' in response.data

    def test_create_purchase_missing_account_returns_400(
        self, authenticated_api_client, product
    ):
        response = authenticated_api_client.post(
            reverse('kitchen-purchase-list'),
            {
                'product': product.id,
                'quantity_bought': '5.00',
                'unit_price': '2.00',
            },
            format='json',
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'account' in response.data

    def test_create_purchase_with_nonexistent_product_returns_400(
        self, authenticated_api_client, account
    ):
        response = authenticated_api_client.post(
            reverse('kitchen-purchase-list'),
            {
                'product': 99999,
                'account': account.id,
                'quantity_bought': '5.00',
                'unit_price': '2.00',
            },
            format='json',
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_purchase_with_fractional_quantity(
        self, authenticated_api_client, product, account
    ):
        initial_quantity = product.quantity
        response = _create_purchase(
            authenticated_api_client,
            product,
            account,
            quantity_bought='2.50',
            unit_price='4.00',
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['subtotal'] == Decimal('10.00')
        product.refresh_from_db()
        assert product.quantity == initial_quantity + Decimal('2.50')

    def test_create_purchase_with_zero_unit_price_creates_zero_expense(
        self, authenticated_api_client, product, account
    ):
        initial_balance = account.balance
        response = _create_purchase(
            authenticated_api_client,
            product,
            account,
            unit_price='0.00',
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['transaction']['amount'] == '0.00'
        account.refresh_from_db()
        assert account.balance == initial_balance

    def test_create_purchase_without_notes_uses_product_name_in_transaction(
        self, authenticated_api_client, product, account
    ):
        response = _create_purchase(
            authenticated_api_client,
            product,
            account,
            notes='',
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['transaction']['description'] == f'Purchase: {product.name}'

    def test_create_purchase_with_notes_uses_notes_as_transaction_description(
        self, authenticated_api_client, product, account
    ):
        response = _create_purchase(
            authenticated_api_client,
            product,
            account,
            notes='Mercado central',
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['transaction']['description'] == 'Mercado central'

    def test_update_purchase_reducing_quantity_adjusts_inventory_and_balance(
        self, authenticated_api_client, product, account
    ):
        create_response = _create_purchase(authenticated_api_client, product, account)
        purchase_id = create_response.data['id']
        product.refresh_from_db()
        account.refresh_from_db()
        quantity_after_create = product.quantity
        balance_after_create = account.balance

        response = authenticated_api_client.patch(
            reverse('kitchen-purchase-detail', kwargs={'pk': purchase_id}),
            {'quantity_bought': '4.00'},
            format='json',
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data['subtotal'] == Decimal('10.00')
        product.refresh_from_db()
        account.refresh_from_db()
        assert product.quantity == quantity_after_create - Decimal('6.00')
        assert account.balance == balance_after_create + Decimal('15.00')

    def test_update_purchase_changes_account_and_moves_balance(
        self, authenticated_api_client, product, account, second_account
    ):
        create_response = _create_purchase(authenticated_api_client, product, account)
        purchase_id = create_response.data['id']
        account.refresh_from_db()
        second_account.refresh_from_db()
        account_balance_after_purchase = account.balance
        second_balance_before = second_account.balance

        response = authenticated_api_client.patch(
            reverse('kitchen-purchase-detail', kwargs={'pk': purchase_id}),
            {'account': second_account.id},
            format='json',
        )

        assert response.status_code == status.HTTP_200_OK
        account.refresh_from_db()
        second_account.refresh_from_db()
        assert account.balance == account_balance_after_purchase + Decimal('25.00')
        assert second_account.balance == second_balance_before - Decimal('25.00')

    def test_delete_nonexistent_purchase_returns_404(self, authenticated_api_client):
        url = reverse('kitchen-purchase-detail', kwargs={'pk': 99999})
        response = authenticated_api_client.delete(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_product_blocked_after_multiple_purchases(
        self, authenticated_api_client, product, account
    ):
        _create_purchase(
            authenticated_api_client,
            product,
            account,
            quantity_bought='1.00',
            unit_price='1.00',
        )
        _create_purchase(
            authenticated_api_client,
            product,
            account,
            quantity_bought='2.00',
            unit_price='1.00',
        )

        authenticated_api_client.raise_request_exception = False
        response = authenticated_api_client.delete(
            reverse('kitchen-product-detail', kwargs={'pk': product.id})
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert models.Product.objects.filter(pk=product.id).exists()
