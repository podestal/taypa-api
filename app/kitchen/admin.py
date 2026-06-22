from django.contrib import admin
from . import models


@admin.register(models.Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'quantity', 'weight', 'volume', 'created_at', 'updated_at']
    search_fields = ['name', 'description']


@admin.register(models.Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ['name', 'balance', 'is_active', 'created_at']
    search_fields = ['name']


@admin.register(models.Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = [
        'transaction_type',
        'account',
        'amount',
        'transaction_date',
        'created_by',
        'created_at',
    ]
    list_filter = ['transaction_type', 'transaction_date']
    search_fields = ['description', 'account__name']


@admin.register(models.Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = [
        'product',
        'quantity_bought',
        'unit_price',
        'transaction',
        'created_at',
    ]
    search_fields = ['product__name', 'notes']


@admin.register(models.InventoryMovement)
class InventoryMovementAdmin(admin.ModelAdmin):
    list_display = [
        'product',
        'movement_type',
        'quantity',
        'source',
        'movement_date',
        'created_by',
        'created_at',
    ]
    list_filter = ['movement_type', 'source', 'movement_date']
    search_fields = ['product__name', 'notes']
