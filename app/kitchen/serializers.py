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
            'movement_date',
            'notes',
            'created_by',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['purchase', 'created_at', 'updated_at']

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
