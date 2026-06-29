import pytest
from datetime import date, timedelta
from decimal import Decimal

from django.urls import reverse
from model_bakery import baker
from rest_framework import status

from kitchen import models


def _create_purchase(
    client,
    product,
    account,
    quantity_bought='10.00',
    unit_price='2.50',
    notes='',
    purchase_date=None,
):
    url = reverse('kitchen-purchase-list')
    payload = {
        'product': product.id,
        'account': account.id,
        'quantity_bought': quantity_bought,
        'unit_price': unit_price,
        'notes': notes,
    }
    if purchase_date is not None:
        payload['purchase_date'] = str(purchase_date)
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
        assert hasattr(purchase, 'inventory_movement')
        assert purchase.inventory_movement.movement_type == 'IN'
        assert purchase.inventory_movement.source == 'PURCHASE'
        assert purchase.inventory_movement.quantity == Decimal('10.00')

        product.refresh_from_db()
        account.refresh_from_db()
        assert product.quantity == initial_quantity + Decimal('10.00')
        assert account.balance == initial_balance - expected_subtotal

    def test_create_purchase_for_other_product_records_expense_without_inventory(
        self, authenticated_api_client, account
    ):
        product_response = authenticated_api_client.post(
            reverse('kitchen-product-list'),
            {
                'name': '[TEST] Cleaning Service',
                'product_type': models.Product.TYPE_OTHER,
            },
            format='json',
        )
        other_product = models.Product.objects.get(pk=product_response.data['id'])
        initial_balance = account.balance

        response = _create_purchase(authenticated_api_client, other_product, account)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['transaction']['amount'] == '25.00'

        purchase = models.Purchase.objects.get(pk=response.data['id'])
        assert not hasattr(purchase, 'inventory_movement')

        other_product.refresh_from_db()
        account.refresh_from_db()
        assert other_product.quantity == Decimal('0.00')
        assert account.balance == initial_balance - Decimal('25.00')

    def test_create_purchase_with_custom_date(
        self, authenticated_api_client, product, account
    ):
        purchase_date = date.today() - timedelta(days=4)

        response = _create_purchase(
            authenticated_api_client,
            product,
            account,
            purchase_date=purchase_date,
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['transaction']['transaction_date'] == str(purchase_date)

        purchase = models.Purchase.objects.get(pk=response.data['id'])
        assert purchase.inventory_movement.movement_date == purchase_date


@pytest.mark.django_db
class TestKitchenPurchaseListFilters:
    def test_list_purchases_by_date(
        self, authenticated_api_client, product, other_product, account
    ):
        today = date.today()
        yesterday = today - timedelta(days=1)

        tomatoes_purchase_id = _create_purchase(
            authenticated_api_client,
            product,
            account,
            purchase_date=yesterday,
        ).data['id']
        _create_purchase(
            authenticated_api_client,
            other_product,
            account,
            purchase_date=today,
        )

        response = authenticated_api_client.get(
            reverse('kitchen-purchase-list'),
            {'date': str(yesterday)},
        )

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]['id'] == tomatoes_purchase_id

    def test_list_purchases_by_date_range(
        self, authenticated_api_client, product, other_product, account
    ):
        today = date.today()
        two_days_ago = today - timedelta(days=2)
        yesterday = today - timedelta(days=1)

        _create_purchase(
            authenticated_api_client,
            product,
            account,
            purchase_date=two_days_ago,
        )
        middle_purchase_id = _create_purchase(
            authenticated_api_client,
            product,
            account,
            purchase_date=yesterday,
        ).data['id']
        _create_purchase(
            authenticated_api_client,
            other_product,
            account,
            purchase_date=today,
        )

        response = authenticated_api_client.get(
            reverse('kitchen-purchase-list'),
            {
                'start_date': str(yesterday),
                'end_date': str(today),
            },
        )

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2
        assert middle_purchase_id in {row['id'] for row in response.data}

    def test_list_purchases_by_product(
        self, authenticated_api_client, product, other_product, account
    ):
        today = date.today()

        tomatoes_purchase_id = _create_purchase(
            authenticated_api_client,
            product,
            account,
            purchase_date=today,
        ).data['id']
        _create_purchase(
            authenticated_api_client,
            other_product,
            account,
            purchase_date=today,
        )

        response = authenticated_api_client.get(
            reverse('kitchen-purchase-list'),
            {'product_id': product.id},
        )

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]['id'] == tomatoes_purchase_id

    def test_list_purchases_by_account(
        self, authenticated_api_client, product, account, second_account
    ):
        today = date.today()

        cash_purchase_id = _create_purchase(
            authenticated_api_client,
            product,
            account,
            purchase_date=today,
        ).data['id']
        _create_purchase(
            authenticated_api_client,
            product,
            second_account,
            purchase_date=today,
        )

        response = authenticated_api_client.get(
            reverse('kitchen-purchase-list'),
            {'account_id': account.id},
        )

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]['id'] == cash_purchase_id


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

    def test_create_purchase_with_zero_quantity_skips_inventory(
        self, authenticated_api_client, product, account
    ):
        initial_quantity = product.quantity

        response = _create_purchase(
            authenticated_api_client,
            product,
            account,
            quantity_bought='0.00',
            unit_price='5.00',
            notes='Pending delivery',
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['subtotal'] == Decimal('0.00')
        assert response.data['transaction']['amount'] == '0.00'

        purchase = models.Purchase.objects.get(pk=response.data['id'])
        assert not models.InventoryMovement.objects.filter(purchase=purchase).exists()

        product.refresh_from_db()
        assert product.quantity == initial_quantity

    def test_update_purchase_adds_quantity_and_syncs_inventory(
        self, authenticated_api_client, product, account
    ):
        create_response = _create_purchase(
            authenticated_api_client,
            product,
            account,
            quantity_bought='0.00',
            unit_price='2.50',
        )
        purchase_id = create_response.data['id']
        initial_quantity = product.quantity
        initial_balance = account.balance

        response = authenticated_api_client.patch(
            reverse('kitchen-purchase-detail', kwargs={'pk': purchase_id}),
            {
                'quantity_bought': '12.00',
                'unit_price': '3.00',
            },
            format='json',
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data['subtotal'] == Decimal('36.00')
        assert response.data['transaction']['amount'] == '36.00'

        purchase = models.Purchase.objects.get(pk=purchase_id)
        assert purchase.inventory_movement.quantity == Decimal('12.00')
        assert purchase.inventory_movement.product_id == product.id

        product.refresh_from_db()
        account.refresh_from_db()
        assert product.quantity == initial_quantity + Decimal('12.00')
        assert account.balance == initial_balance - Decimal('36.00')

    def test_update_purchase_date_account_and_notes(
        self, authenticated_api_client, product, account, second_account
    ):
        purchase_date = date.today() - timedelta(days=5)
        updated_date = date.today() - timedelta(days=2)

        create_response = _create_purchase(
            authenticated_api_client,
            product,
            account,
            purchase_date=purchase_date,
            notes='Initial note',
        )
        purchase_id = create_response.data['id']
        account.refresh_from_db()
        balance_after_create = account.balance
        second_balance_before = second_account.balance

        response = authenticated_api_client.patch(
            reverse('kitchen-purchase-detail', kwargs={'pk': purchase_id}),
            {
                'account': second_account.id,
                'purchase_date': str(updated_date),
                'notes': 'Updated note',
                'unit_price': '4.00',
            },
            format='json',
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data['transaction']['transaction_date'] == str(updated_date)
        assert response.data['transaction']['description'] == 'Updated note'
        assert response.data['transaction']['amount'] == '40.00'

        purchase = models.Purchase.objects.get(pk=purchase_id)
        assert purchase.inventory_movement.movement_date == updated_date

        account.refresh_from_db()
        second_account.refresh_from_db()
        assert account.balance == balance_after_create + Decimal('25.00')
        assert second_account.balance == second_balance_before - Decimal('40.00')


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
        assert models.InventoryMovement.objects.filter(
            product=product,
            source='PURCHASE',
        ).count() == 0

        product.refresh_from_db()
        account.refresh_from_db()
        assert product.quantity == quantity_after_create - Decimal('10.00')
        assert account.balance == balance_after_create + Decimal('25.00')
