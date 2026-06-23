import pytest
from decimal import Decimal

from django.urls import reverse
from model_bakery import baker
from rest_framework import status

from kitchen import models


@pytest.mark.django_db
class TestProductEdgeCases:
    def test_create_product_missing_name_returns_400(self, authenticated_api_client):
        response = authenticated_api_client.post(
            reverse('kitchen-product-list'),
            {'quantity': '0.00'},
            format='json',
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'name' in response.data

    def test_create_product_defaults_quantity_to_zero(self, authenticated_api_client):
        response = authenticated_api_client.post(
            reverse('kitchen-product-list'),
            {'name': 'Salt'},
            format='json',
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['quantity'] == '0.00'

    def test_create_product_with_initial_quantity_creates_adjustment(
        self, authenticated_api_client, user
    ):
        response = authenticated_api_client.post(
            reverse('kitchen-product-list'),
            {
                'name': '[TEST] Flour',
                'quantity': '25.00',
            },
            format='json',
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['quantity'] == '25.00'

        product = models.Product.objects.get(pk=response.data['id'])
        movement = models.InventoryMovement.objects.get(product=product)
        assert movement.movement_type == 'IN'
        assert movement.source == 'ADJUSTMENT'
        assert movement.quantity == Decimal('25.00')
        assert movement.created_by == user
        assert movement.notes == 'Opening stock'

    def test_create_product_rejects_negative_quantity(self, authenticated_api_client):
        response = authenticated_api_client.post(
            reverse('kitchen-product-list'),
            {
                'name': 'Bad Product',
                'quantity': '-1.00',
            },
            format='json',
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'quantity' in response.data

    def test_update_product_quantity_directly_is_not_allowed(
        self, authenticated_api_client, product
    ):
        url = reverse('kitchen-product-detail', kwargs={'pk': product.id})
        response = authenticated_api_client.patch(
            url,
            {'quantity': '99.50'},
            format='json',
        )

        assert response.status_code == status.HTTP_200_OK
        product.refresh_from_db()
        assert product.quantity == Decimal('20.00')

    def test_delete_product_with_purchases_is_blocked(
        self, authenticated_api_client, purchase
    ):
        authenticated_api_client.raise_request_exception = False
        url = reverse('kitchen-product-detail', kwargs={'pk': purchase.product_id})
        response = authenticated_api_client.delete(url)

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert models.Product.objects.filter(pk=purchase.product_id).exists()

    def test_retrieve_nonexistent_product_returns_404(self, authenticated_api_client):
        url = reverse('kitchen-product-detail', kwargs={'pk': 99999})
        response = authenticated_api_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND
