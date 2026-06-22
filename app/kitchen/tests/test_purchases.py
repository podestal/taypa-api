import pytest
from decimal import Decimal

from django.urls import reverse
from rest_framework import status

from kitchen import models


def _create_purchase(client, product, account, quantity_bought='10.00', unit_price='2.50', notes=''):
    url = reverse('kitchen-purchase-list')
    payload = {
        'product': product.id,
        'account': account.id,
        'quantity_bought': quantity_bought,
        'unit_price': unit_price,
        'notes': notes,
    }
    return client.post(url, payload, format='json')


@pytest.mark.django_db
class TestKitchenPurchaseCreate:
    def test_create_purchase_creates_expense_transaction_and_updates_product(
        self, authenticated_api_client, product, account
    ):
        initial_balance = account.balance
        initial_quantity = product.quantity
        expected_subtotal = Decimal('25.00')

        response = _create_purchase(authenticated_api_client, product, account)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['subtotal'] == expected_subtotal
        assert response.data['transaction']['transaction_type'] == 'E'
        assert response.data['transaction']['amount'] == '25.00'

        purchase = models.Purchase.objects.get(pk=response.data['id'])
        assert purchase.transaction_id == response.data['transaction']['id']
        assert models.Transaction.objects.filter(pk=purchase.transaction_id).exists()

        product.refresh_from_db()
        account.refresh_from_db()
        assert product.quantity == initial_quantity + Decimal('10.00')
        assert account.balance == initial_balance - expected_subtotal


@pytest.mark.django_db
class TestKitchenPurchaseUpdate:
    def test_update_purchase_updates_transaction_and_adjusts_product_quantity(
        self, authenticated_api_client, product, account
    ):
        create_response = _create_purchase(authenticated_api_client, product, account)
        purchase_id = create_response.data['id']
        old_transaction_id = create_response.data['transaction']['id']

        product.refresh_from_db()
        account.refresh_from_db()
        quantity_after_create = product.quantity
        balance_after_create = account.balance

        url = reverse('kitchen-purchase-detail', kwargs={'pk': purchase_id})
        response = authenticated_api_client.patch(
            url,
            {
                'quantity_bought': '15.00',
                'unit_price': '3.00',
            },
            format='json',
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data['subtotal'] == Decimal('45.00')
        assert response.data['transaction']['id'] == old_transaction_id
        assert models.Transaction.objects.filter(pk=old_transaction_id).exists()

        product.refresh_from_db()
        account.refresh_from_db()
        assert product.quantity == quantity_after_create + Decimal('5.00')
        assert account.balance == balance_after_create - Decimal('20.00')

    def test_update_purchase_product_moves_inventory_between_products(
        self, authenticated_api_client, product, other_product, account
    ):
        create_response = _create_purchase(
            authenticated_api_client,
            product,
            account,
            quantity_bought='8.00',
            unit_price='2.00',
        )
        purchase_id = create_response.data['id']

        product.refresh_from_db()
        other_product.refresh_from_db()
        tomatoes_quantity_after_create = product.quantity
        rice_quantity_before_update = other_product.quantity

        url = reverse('kitchen-purchase-detail', kwargs={'pk': purchase_id})
        response = authenticated_api_client.patch(
            url,
            {'product': other_product.id},
            format='json',
        )

        assert response.status_code == status.HTTP_200_OK

        product.refresh_from_db()
        other_product.refresh_from_db()
        assert product.quantity == tomatoes_quantity_after_create - Decimal('8.00')
        assert other_product.quantity == rice_quantity_before_update + Decimal('8.00')


@pytest.mark.django_db
class TestKitchenPurchaseDelete:
    def test_delete_purchase_removes_transaction_and_reverses_product_quantity(
        self, authenticated_api_client, product, account
    ):
        create_response = _create_purchase(authenticated_api_client, product, account)
        purchase_id = create_response.data['id']
        transaction_id = create_response.data['transaction']['id']

        product.refresh_from_db()
        account.refresh_from_db()
        quantity_after_create = product.quantity
        balance_after_create = account.balance

        url = reverse('kitchen-purchase-detail', kwargs={'pk': purchase_id})
        response = authenticated_api_client.delete(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not models.Purchase.objects.filter(pk=purchase_id).exists()
        assert not models.Transaction.objects.filter(pk=transaction_id).exists()

        product.refresh_from_db()
        account.refresh_from_db()
        assert product.quantity == quantity_after_create - Decimal('10.00')
        assert account.balance == balance_after_create + Decimal('25.00')
