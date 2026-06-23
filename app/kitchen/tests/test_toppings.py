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


@pytest.fixture
def cheese_product(db):
    return baker.make(
        models.Product,
        name='[TEST] Cheese',
        quantity=Decimal('10.00'),
    )


@pytest.fixture
def topping(db, cheese_product):
    return baker.make(
        models.Topping,
        name='[TEST] Extra Cheese',
        price=Decimal('2.00'),
        product=cheese_product,
        quantity=Decimal('0.50'),
        is_active=True,
    )


@pytest.mark.django_db
class TestKitchenToppingAPI:
    def test_create_topping(self, authenticated_api_client, cheese_product):
        response = authenticated_api_client.post(
            reverse('kitchen-topping-list'),
            {
                'name': '[TEST] Extra Bacon',
                'price': '3.00',
                'product': cheese_product.id,
                'quantity': '1.00',
            },
            format='json',
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['name'] == '[TEST] Extra Bacon'
        assert response.data['price'] == '3.00'

    def test_list_toppings_excludes_inactive(
        self, authenticated_api_client, topping, cheese_product
    ):
        baker.make(
            models.Topping,
            name='[TEST] Old Topping',
            price=Decimal('1.00'),
            product=cheese_product,
            quantity=Decimal('1.00'),
            is_active=False,
        )

        response = authenticated_api_client.get(reverse('kitchen-topping-list'))

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]['id'] == topping.id

    def test_update_topping(self, authenticated_api_client, topping):
        response = authenticated_api_client.patch(
            reverse('kitchen-topping-detail', kwargs={'pk': topping.id}),
            {'price': '2.50'},
            format='json',
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data['price'] == '2.50'

    def test_delete_topping(self, authenticated_api_client, topping):
        response = authenticated_api_client.delete(
            reverse('kitchen-topping-detail', kwargs={'pk': topping.id}),
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not models.Topping.objects.filter(pk=topping.id).exists()


@pytest.mark.django_db
class TestKitchenSaleWithToppingsAPI:
    def test_create_sale_with_toppings_updates_income_and_inventory(
        self,
        authenticated_api_client,
        dish_with_recipe,
        account,
        product,
        topping,
        cheese_product,
    ):
        initial_balance = account.balance
        initial_patty_qty = product.quantity
        initial_cheese_qty = cheese_product.quantity

        response = authenticated_api_client.post(
            reverse('kitchen-sale-list'),
            {
                'dish': dish_with_recipe.id,
                'account': account.id,
                'quantity_sold': '2.00',
                'toppings': [
                    {'topping': topping.id, 'quantity': '1.00'},
                ],
            },
            format='json',
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['dish_subtotal'] == Decimal('30.00')
        assert response.data['toppings_subtotal'] == Decimal('2.00')
        assert response.data['subtotal'] == Decimal('32.00')
        assert response.data['transaction']['amount'] == '32.00'
        assert len(response.data['sale_toppings']) == 1
        assert response.data['sale_toppings'][0]['topping'] == topping.id

        sale = models.Sale.objects.get(pk=response.data['id'])
        assert sale.sale_toppings.count() == 1
        assert sale.inventory_movements.filter(source='SALE').count() == 2

        account.refresh_from_db()
        product.refresh_from_db()
        cheese_product.refresh_from_db()
        assert account.balance == initial_balance + Decimal('32.00')
        assert product.quantity == initial_patty_qty - Decimal('2.00')
        assert cheese_product.quantity == initial_cheese_qty - Decimal('0.50')

    def test_create_sale_fails_when_topping_stock_insufficient(
        self,
        authenticated_api_client,
        dish_with_recipe,
        account,
        topping,
        cheese_product,
    ):
        cheese_product.quantity = Decimal('0.10')
        cheese_product.save(update_fields=['quantity'])

        response = authenticated_api_client.post(
            reverse('kitchen-sale-list'),
            {
                'dish': dish_with_recipe.id,
                'account': account.id,
                'quantity_sold': '1.00',
                'toppings': [
                    {'topping': topping.id, 'quantity': '1.00'},
                ],
            },
            format='json',
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'stock' in response.data

    def test_delete_sale_with_toppings_reverses_inventory(
        self,
        authenticated_api_client,
        dish_with_recipe,
        account,
        product,
        topping,
        cheese_product,
    ):
        create_response = authenticated_api_client.post(
            reverse('kitchen-sale-list'),
            {
                'dish': dish_with_recipe.id,
                'account': account.id,
                'quantity_sold': '2.00',
                'toppings': [
                    {'topping': topping.id, 'quantity': '1.00'},
                ],
            },
            format='json',
        )
        sale_id = create_response.data['id']

        product.refresh_from_db()
        cheese_product.refresh_from_db()
        patty_after_sale = product.quantity
        cheese_after_sale = cheese_product.quantity

        response = authenticated_api_client.delete(
            reverse('kitchen-sale-detail', kwargs={'pk': sale_id}),
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT

        product.refresh_from_db()
        cheese_product.refresh_from_db()
        assert product.quantity == patty_after_sale + Decimal('2.00')
        assert cheese_product.quantity == cheese_after_sale + Decimal('0.50')
