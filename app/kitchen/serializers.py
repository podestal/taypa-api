from decimal import Decimal

from django.db import transaction as db_transaction
import rest_framework.serializers as serializers
from . import models


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Product
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


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

    def _apply_inventory_change(self, product, quantity, reverse=False):
        multiplier = Decimal('-1') if reverse else Decimal('1')
        product.quantity += quantity * multiplier
        product.save(update_fields=['quantity', 'updated_at'])

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
            self._apply_inventory_change(product, quantity_bought)
        return purchase

    def update(self, instance, validated_data):
        account = validated_data.pop('account', None)
        old_product = instance.product
        old_quantity = instance.quantity_bought

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        new_product = instance.product
        new_quantity = instance.quantity_bought
        new_amount = self._get_subtotal(instance.quantity_bought, instance.unit_price)

        with db_transaction.atomic():
            self._apply_inventory_change(old_product, old_quantity, reverse=True)

            purchase_transaction = instance.transaction
            purchase_transaction.amount = new_amount
            purchase_transaction.description = instance.notes or f'Purchase: {new_product.name}'
            if account:
                purchase_transaction.account = account
            purchase_transaction.save()

            instance.save()
            self._apply_inventory_change(new_product, new_quantity)

        return instance
