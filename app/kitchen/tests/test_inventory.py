import pytest
from datetime import date, timedelta
from decimal import Decimal

from django.urls import reverse
from rest_framework import status

from kitchen import models


@pytest.mark.django_db
class TestInventoryMovementAPI:
    def test_create_usage_movement_reduces_product_quantity(
        self, authenticated_api_client, product
    ):
        initial_quantity = product.quantity
        response = authenticated_api_client.post(
            reverse('kitchen-inventory-movement-list'),
            {
                'product': product.id,
                'movement_type': 'OUT',
                'quantity': '5.00',
                'source': 'USAGE',
                'movement_date': str(date.today()),
                'notes': 'Prep for lunch',
            },
            format='json',
        )

        assert response.status_code == status.HTTP_201_CREATED
        product.refresh_from_db()
        assert product.quantity == initial_quantity - Decimal('5.00')
        assert models.InventoryMovement.objects.filter(source='USAGE').count() == 1

    def test_create_waste_movement_requires_out_type(
        self, authenticated_api_client, product
    ):
        response = authenticated_api_client.post(
            reverse('kitchen-inventory-movement-list'),
            {
                'product': product.id,
                'movement_type': 'IN',
                'quantity': '2.00',
                'source': 'WASTE',
            },
            format='json',
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_purchase_source_movement_is_blocked(
        self, authenticated_api_client, product
    ):
        response = authenticated_api_client.post(
            reverse('kitchen-inventory-movement-list'),
            {
                'product': product.id,
                'movement_type': 'IN',
                'quantity': '2.00',
                'source': 'PURCHASE',
            },
            format='json',
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_list_movements_filtered_by_product(
        self, authenticated_api_client, product, other_product
    ):
        authenticated_api_client.post(
            reverse('kitchen-inventory-movement-list'),
            {
                'product': product.id,
                'movement_type': 'OUT',
                'quantity': '1.00',
                'source': 'USAGE',
            },
            format='json',
        )
        authenticated_api_client.post(
            reverse('kitchen-inventory-movement-list'),
            {
                'product': other_product.id,
                'movement_type': 'OUT',
                'quantity': '1.00',
                'source': 'USAGE',
            },
            format='json',
        )

        response = authenticated_api_client.get(
            reverse('kitchen-inventory-movement-list'),
            {'product_id': product.id},
        )

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]['product'] == product.id


@pytest.mark.django_db
class TestInventoryReportAPI:
    def test_report_requires_date_range(self, authenticated_api_client):
        response = authenticated_api_client.get(reverse('kitchen-inventory-report'))

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_report_shows_daily_in_and_out(
        self, authenticated_api_client, account
    ):
        today = date.today()
        yesterday = today - timedelta(days=1)
        opening_date = yesterday - timedelta(days=1)

        product_response = authenticated_api_client.post(
            reverse('kitchen-product-list'),
            {'name': '[TEST] Onions'},
            format='json',
        )
        product_id = product_response.data['id']

        authenticated_api_client.post(
            reverse('kitchen-inventory-movement-list'),
            {
                'product': product_id,
                'movement_type': 'IN',
                'quantity': '20.00',
                'source': 'ADJUSTMENT',
                'movement_date': str(opening_date),
                'notes': 'Opening stock',
            },
            format='json',
        )
        authenticated_api_client.post(
            reverse('kitchen-purchase-list'),
            {
                'product': product_id,
                'account': account.id,
                'quantity_bought': '10.00',
                'unit_price': '2.00',
            },
            format='json',
        )
        authenticated_api_client.post(
            reverse('kitchen-inventory-movement-list'),
            {
                'product': product_id,
                'movement_type': 'OUT',
                'quantity': '3.00',
                'source': 'USAGE',
                'movement_date': str(today),
            },
            format='json',
        )

        response = authenticated_api_client.get(
            reverse('kitchen-inventory-report'),
            {
                'start_date': str(yesterday),
                'end_date': str(today),
                'product_id': product_id,
            },
        )

        assert response.status_code == status.HTTP_200_OK
        results = {row['date']: row for row in response.data['results']}

        assert results[str(yesterday)]['opening_balance'] == '20.00'
        assert results[str(yesterday)]['in'] == '0.00'
        assert results[str(yesterday)]['out'] == '0.00'
        assert results[str(yesterday)]['closing_balance'] == '20.00'

        assert results[str(today)]['opening_balance'] == '20.00'
        assert results[str(today)]['in'] == '10.00'
        assert results[str(today)]['out'] == '3.00'
        assert results[str(today)]['closing_balance'] == '27.00'

        product = models.Product.objects.get(pk=product_id)
        assert product.quantity == Decimal('27.00')

    def test_current_inventory_endpoint(self, authenticated_api_client, product):
        response = authenticated_api_client.get(reverse('kitchen-inventory-current'))

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) >= 1
        row = next(r for r in response.data['results'] if r['product_id'] == product.id)
        assert row['quantity'] == str(product.quantity)
