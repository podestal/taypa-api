from django.contrib import admin
from . import models


@admin.register(models.Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'created_at']
    search_fields = ['name']


class DishIngredientInline(admin.TabularInline):
    model = models.DishIngredient
    extra = 1


@admin.register(models.Dish)
class DishAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'price', 'is_active', 'created_at']
    list_filter = ['category', 'is_active']
    search_fields = ['name']
    inlines = [DishIngredientInline]


@admin.register(models.DishIngredient)
class DishIngredientAdmin(admin.ModelAdmin):
    list_display = ['dish', 'product', 'quantity']
    search_fields = ['dish__name', 'product__name']


@admin.register(models.Topping)
class ToppingAdmin(admin.ModelAdmin):
    list_display = ['name', 'price', 'product', 'quantity', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name', 'product__name']


class SaleToppingInline(admin.TabularInline):
    model = models.SaleTopping
    extra = 0
    readonly_fields = ['unit_price']


@admin.register(models.Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ['dish', 'quantity_sold', 'unit_price', 'transaction', 'created_at']
    search_fields = ['dish__name', 'notes']
    inlines = [SaleToppingInline]


@admin.register(models.SaleTopping)
class SaleToppingAdmin(admin.ModelAdmin):
    list_display = ['sale', 'topping', 'quantity', 'unit_price']
    search_fields = ['sale__dish__name', 'topping__name']


@admin.register(models.Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'product_type', 'quantity', 'weight', 'volume', 'created_at']
    list_filter = ['product_type']
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
