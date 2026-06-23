import pytest
from decimal import Decimal

from django.urls import reverse
from model_bakery import baker
from rest_framework import status

from kitchen import models


@pytest.fixture
def category(db):
    return baker.make(
        models.Category,
        name='[TEST] Burgers',
        is_active=True,
    )


@pytest.fixture
def dish(db, category):
    return baker.make(
        models.Dish,
        name='[TEST] Classic Burger',
        price=Decimal('15.00'),
        category=category,
        is_active=True,
    )


@pytest.fixture
def dish_with_recipe(db, dish, product):
    baker.make(
        models.DishIngredient,
        dish=dish,
        product=product,
        quantity=Decimal('1.00'),
    )
    product.quantity = Decimal('50.00')
    product.save(update_fields=['quantity'])
    return dish


@pytest.mark.django_db
class TestKitchenDishAPI:
    def test_create_dish_with_ingredients(
        self, authenticated_api_client, category, product
    ):
        response = authenticated_api_client.post(
            reverse('kitchen-dish-list'),
            {
                'name': '[TEST] Cheese Burger',
                'price': '18.00',
                'category': category.id,
                'ingredients': [
                    {'product': product.id, 'quantity': '1.00'},
                ],
            },
            format='json',
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert len(response.data['ingredients']) == 1
        assert response.data['ingredients'][0]['product'] == product.id

    def test_list_dishes_by_category(
        self, authenticated_api_client, dish, category
    ):
        response = authenticated_api_client.get(
            reverse('kitchen-dish-list'),
            {'category_id': category.id},
        )

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]['id'] == dish.id


@pytest.mark.django_db
class TestKitchenSaleAPI:
    def test_create_sale_adds_income_and_subtracts_inventory(
        self, authenticated_api_client, dish_with_recipe, account, product
    ):
        initial_balance = account.balance
        initial_quantity = product.quantity

        response = authenticated_api_client.post(
            reverse('kitchen-sale-list'),
            {
                'dish': dish_with_recipe.id,
                'account': account.id,
                'quantity_sold': '2.00',
            },
            format='json',
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['subtotal'] == Decimal('30.00')
        assert response.data['transaction']['transaction_type'] == 'I'
        assert response.data['transaction']['amount'] == '30.00'

        sale = models.Sale.objects.get(pk=response.data['id'])
        assert sale.inventory_movements.filter(source='SALE').count() == 1

        account.refresh_from_db()
        product.refresh_from_db()
        assert account.balance == initial_balance + Decimal('30.00')
        assert product.quantity == initial_quantity - Decimal('2.00')

    def test_create_sale_fails_when_insufficient_stock(
        self, authenticated_api_client, dish_with_recipe, account, product
    ):
        product.quantity = Decimal('1.00')
        product.save(update_fields=['quantity'])

        response = authenticated_api_client.post(
            reverse('kitchen-sale-list'),
            {
                'dish': dish_with_recipe.id,
                'account': account.id,
                'quantity_sold': '2.00',
            },
            format='json',
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'stock' in response.data

    def test_delete_sale_reverses_transaction_and_inventory(
        self, authenticated_api_client, dish_with_recipe, account, product
    ):
        create_response = authenticated_api_client.post(
            reverse('kitchen-sale-list'),
            {
                'dish': dish_with_recipe.id,
                'account': account.id,
                'quantity_sold': '2.00',
            },
            format='json',
        )
        sale_id = create_response.data['id']
        transaction_id = create_response.data['transaction']['id']

        account.refresh_from_db()
        product.refresh_from_db()
        balance_after_sale = account.balance
        quantity_after_sale = product.quantity

        response = authenticated_api_client.delete(
            reverse('kitchen-sale-detail', kwargs={'pk': sale_id}),
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not models.Sale.objects.filter(pk=sale_id).exists()
        assert not models.Transaction.objects.filter(pk=transaction_id).exists()

        account.refresh_from_db()
        product.refresh_from_db()
        assert account.balance == balance_after_sale - Decimal('30.00')
        assert product.quantity == quantity_after_sale + Decimal('2.00')
