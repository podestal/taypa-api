from decimal import Decimal

from django.db import transaction as db_transaction
from django.utils import timezone
import rest_framework.serializers as serializers
from . import inventory, models


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Product
        fields = '__all__'
        read_only_fields = ['quantity', 'created_at', 'updated_at']


class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Account
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class TransactionSerializer(serializers.ModelSerializer):
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = models.Transaction
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class InventoryMovementSerializer(serializers.ModelSerializer):
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = models.InventoryMovement
        fields = [
            'id',
            'product',
            'product_name',
            'movement_type',
            'quantity',
            'source',
            'purchase',
            'sale',
            'movement_date',
            'notes',
            'created_by',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['purchase', 'sale', 'created_at', 'updated_at']

    def validate(self, attrs):
        source = attrs.get('source', getattr(self.instance, 'source', None))
        movement_type = attrs.get(
            'movement_type',
            getattr(self.instance, 'movement_type', None),
        )
        quantity = attrs.get('quantity', getattr(self.instance, 'quantity', None))

        if quantity is not None and quantity <= 0:
            raise serializers.ValidationError({'quantity': 'Quantity must be greater than zero.'})

        if source == 'PURCHASE':
            raise serializers.ValidationError(
                {'source': 'Purchase movements are created automatically when recording a purchase.'},
            )

        if source == 'SALE':
            raise serializers.ValidationError(
                {'source': 'Sale movements are created automatically when recording a sale.'},
            )

        if source in ('USAGE', 'WASTE') and movement_type != 'OUT':
            raise serializers.ValidationError(
                {'movement_type': 'Usage and waste movements must be type OUT.'},
            )

        return attrs

    def create(self, validated_data):
        user = self.context['request'].user
        validated_data.setdefault('movement_date', timezone.localdate())
        return inventory.create_inventory_movement(
            created_by=user,
            **validated_data,
        )


class PurchaseSerializer(serializers.ModelSerializer):
    account = serializers.PrimaryKeyRelatedField(
        queryset=models.Account.objects.filter(is_active=True),
        write_only=True,
    )
    transaction = TransactionSerializer(read_only=True)
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = models.Purchase
        fields = [
            'id',
            'product',
            'quantity_bought',
            'unit_price',
            'account',
            'transaction',
            'subtotal',
            'notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_subtotal(self, obj):
        return obj.subtotal

    def _get_subtotal(self, quantity_bought, unit_price):
        return Decimal(quantity_bought) * Decimal(unit_price)

    def _create_purchase_transaction(self, account, amount, product, notes, user):
        description = notes or f'Purchase: {product.name}'
        return models.Transaction.objects.create(
            transaction_type='E',
            account=account,
            amount=amount,
            description=description,
            created_by=user,
        )

    def create(self, validated_data):
        account = validated_data.pop('account')
        product = validated_data['product']
        quantity_bought = validated_data['quantity_bought']
        unit_price = validated_data['unit_price']
        notes = validated_data.get('notes', '')
        amount = self._get_subtotal(quantity_bought, unit_price)
        user = self.context['request'].user

        with db_transaction.atomic():
            purchase_transaction = self._create_purchase_transaction(
                account, amount, product, notes, user
            )
            purchase = models.Purchase.objects.create(
                transaction=purchase_transaction,
                **validated_data,
            )
            inventory.sync_purchase_movement(purchase, user)
        return purchase

    def update(self, instance, validated_data):
        account = validated_data.pop('account', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        new_amount = self._get_subtotal(instance.quantity_bought, instance.unit_price)
        user = self.context['request'].user

        with db_transaction.atomic():
            purchase_transaction = instance.transaction
            purchase_transaction.amount = new_amount
            purchase_transaction.description = instance.notes or f'Purchase: {instance.product.name}'
            if account:
                purchase_transaction.account = account
            purchase_transaction.save()

            instance.save()
            inventory.sync_purchase_movement(instance, user)

        return instance


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Category
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class DishIngredientSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = models.DishIngredient
        fields = [
            'id',
            'product',
            'product_name',
            'quantity',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class DishSerializer(serializers.ModelSerializer):
    ingredients = DishIngredientSerializer(many=True, required=False)
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model = models.Dish
        fields = [
            'id',
            'name',
            'description',
            'price',
            'category',
            'category_name',
            'is_active',
            'ingredients',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def _sync_ingredients(self, dish, ingredients_data):
        dish.ingredients.all().delete()
        for ingredient in ingredients_data:
            models.DishIngredient.objects.create(dish=dish, **ingredient)

    def create(self, validated_data):
        ingredients_data = validated_data.pop('ingredients', [])
        with db_transaction.atomic():
            dish = models.Dish.objects.create(**validated_data)
            for ingredient in ingredients_data:
                models.DishIngredient.objects.create(dish=dish, **ingredient)
        return dish

    def update(self, instance, validated_data):
        ingredients_data = validated_data.pop('ingredients', None)
        with db_transaction.atomic():
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()
            if ingredients_data is not None:
                self._sync_ingredients(instance, ingredients_data)
        return instance


class ToppingSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = models.Topping
        fields = [
            'id',
            'name',
            'price',
            'product',
            'product_name',
            'quantity',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError('Quantity must be greater than zero.')
        return value


class SaleToppingSerializer(serializers.ModelSerializer):
    topping_name = serializers.CharField(source='topping.name', read_only=True)
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = models.SaleTopping
        fields = [
            'id',
            'topping',
            'topping_name',
            'quantity',
            'unit_price',
            'subtotal',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['unit_price', 'created_at', 'updated_at']

    def get_subtotal(self, obj):
        return obj.subtotal


class SaleToppingWriteSerializer(serializers.Serializer):
    topping = serializers.PrimaryKeyRelatedField(
        queryset=models.Topping.objects.filter(is_active=True),
    )
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2)

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError('Quantity must be greater than zero.')
        return value


class SaleSerializer(serializers.ModelSerializer):
    account = serializers.PrimaryKeyRelatedField(
        queryset=models.Account.objects.filter(is_active=True),
        write_only=True,
    )
    transaction = TransactionSerializer(read_only=True)
    subtotal = serializers.SerializerMethodField()
    dish_subtotal = serializers.SerializerMethodField()
    toppings_subtotal = serializers.SerializerMethodField()
    dish_name = serializers.CharField(source='dish.name', read_only=True)
    toppings = SaleToppingWriteSerializer(many=True, required=False, write_only=True)
    sale_toppings = SaleToppingSerializer(many=True, read_only=True)
    unit_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
    )

    class Meta:
        model = models.Sale
        fields = [
            'id',
            'dish',
            'dish_name',
            'quantity_sold',
            'unit_price',
            'account',
            'transaction',
            'dish_subtotal',
            'toppings_subtotal',
            'subtotal',
            'toppings',
            'sale_toppings',
            'notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_subtotal(self, obj):
        return obj.subtotal

    def get_dish_subtotal(self, obj):
        return obj.dish_subtotal

    def get_toppings_subtotal(self, obj):
        return obj.toppings_subtotal

    def validate(self, attrs):
        dish = attrs.get('dish', getattr(self.instance, 'dish', None))
        quantity_sold = attrs.get(
            'quantity_sold',
            getattr(self.instance, 'quantity_sold', None),
        )
        toppings_data = attrs.get('toppings', [])

        if dish and not dish.is_active:
            raise serializers.ValidationError({'dish': 'This dish is not active.'})

        if toppings_data:
            topping_ids = [item['topping'].id for item in toppings_data]
            if len(topping_ids) != len(set(topping_ids)):
                raise serializers.ValidationError(
                    {'toppings': 'Duplicate toppings are not allowed on the same sale.'},
                )

        if dish and quantity_sold is not None:
            if not dish.ingredients.exists():
                raise serializers.ValidationError(
                    {'dish': 'This dish has no ingredients defined.'},
                )
            shortages = inventory.get_sale_stock_shortages(
                dish,
                quantity_sold,
                toppings_data,
            )
            if shortages:
                raise serializers.ValidationError({'stock': shortages})

        return attrs

    def create(self, validated_data):
        account = validated_data.pop('account')
        toppings_data = validated_data.pop('toppings', [])
        dish = validated_data['dish']
        quantity_sold = validated_data['quantity_sold']
        unit_price = validated_data.pop('unit_price', dish.price)
        notes = validated_data.get('notes', '')
        dish_amount = Decimal(quantity_sold) * Decimal(unit_price)
        toppings_amount = sum(
            Decimal(item['quantity']) * Decimal(item['topping'].price)
            for item in toppings_data
        )
        amount = dish_amount + toppings_amount
        user = self.context['request'].user
        description = notes or f'Sale: {dish.name}'

        with db_transaction.atomic():
            sale_transaction = models.Transaction.objects.create(
                transaction_type='I',
                account=account,
                amount=amount,
                description=description,
                created_by=user,
            )
            sale = models.Sale.objects.create(
                transaction=sale_transaction,
                unit_price=unit_price,
                **validated_data,
            )
            for item in toppings_data:
                models.SaleTopping.objects.create(
                    sale=sale,
                    topping=item['topping'],
                    quantity=item['quantity'],
                    unit_price=item['topping'].price,
                )
            inventory.record_sale_movements(sale, user)
        return sale
