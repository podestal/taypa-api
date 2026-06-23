from datetime import date

from django.conf import settings
from django.db import models


class Product(models.Model):
    """
    Represents an inventory product.
    """
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    weight = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    volume = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Category(models.Model):
    """Menu category for kitchen dishes."""

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'categories'

    def __str__(self):
        return self.name


class Dish(models.Model):
    """Sellable menu item with a recipe defined by dish ingredients."""

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='dishes',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Topping(models.Model):
    """Optional add-on for a dish (e.g. extra cheese) with its own price and inventory."""

    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='toppings',
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text='Amount of product consumed per one topping unit.',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class DishIngredient(models.Model):
    """Amount of a product required to make one dish."""

    dish = models.ForeignKey(
        Dish,
        on_delete=models.CASCADE,
        related_name='ingredients',
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='dish_ingredients',
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['dish', 'product']
        ordering = ['id']

    def __str__(self):
        return f'{self.dish.name}: {self.quantity} x {self.product.name}'


class Account(models.Model):
    """Kitchen cash or bank account used for inventory purchases."""

    name = models.CharField(max_length=255)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - ${self.balance}"


class Transaction(models.Model):
    """Financial movement that increases or decreases an account balance."""

    TRANSACTION_TYPE_CHOICES = [
        ('I', 'Income'),
        ('E', 'Expense'),
    ]

    transaction_type = models.CharField(max_length=1, choices=TRANSACTION_TYPE_CHOICES)
    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        related_name='transactions',
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True)
    transaction_date = models.DateField(default=date.today)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='kitchen_transactions',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-transaction_date', '-created_at']

    def __str__(self):
        return f"{self.get_transaction_type_display()} - ${self.amount} - {self.transaction_date}"

    def _apply_balance_change(self, transaction_type, amount, reverse=False, account=None):
        if account is None:
            account = Account.objects.get(pk=self.account_id)
        multiplier = -1 if reverse else 1
        if transaction_type == 'I':
            account.balance += amount * multiplier
        elif transaction_type == 'E':
            account.balance -= amount * multiplier
        account.save(update_fields=['balance', 'updated_at'])

    def save(self, *args, **kwargs):
        is_new = self.pk is None

        if is_new:
            super().save(*args, **kwargs)
            self._apply_balance_change(self.transaction_type, self.amount)
            return

        old_data = (
            Transaction.objects.filter(pk=self.pk)
            .values('transaction_type', 'amount', 'account_id')
            .get()
        )
        old_account = Account.objects.get(pk=old_data['account_id'])
        self._apply_balance_change(
            old_data['transaction_type'],
            old_data['amount'],
            reverse=True,
            account=old_account,
        )
        self._apply_balance_change(self.transaction_type, self.amount)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self._apply_balance_change(self.transaction_type, self.amount, reverse=True)
        super().delete(*args, **kwargs)


class Purchase(models.Model):
    """A single product purchase that updates inventory and account balance."""

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='purchases')
    quantity_bought = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    transaction = models.OneToOneField(
        Transaction,
        on_delete=models.PROTECT,
        related_name='purchase',
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.product.name} x {self.quantity_bought}"

    @property
    def subtotal(self):
        return self.quantity_bought * self.unit_price


class Sale(models.Model):
    """Records a dish sale: income to account and inventory out per ingredient."""

    dish = models.ForeignKey(Dish, on_delete=models.PROTECT, related_name='sales')
    quantity_sold = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    transaction = models.OneToOneField(
        Transaction,
        on_delete=models.PROTECT,
        related_name='sale',
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.dish.name} x {self.quantity_sold}'

    @property
    def dish_subtotal(self):
        return self.quantity_sold * self.unit_price

    @property
    def toppings_subtotal(self):
        return sum(
            sale_topping.quantity * sale_topping.unit_price
            for sale_topping in self.sale_toppings.all()
        )

    @property
    def subtotal(self):
        return self.dish_subtotal + self.toppings_subtotal


class SaleTopping(models.Model):
    """Topping line on a sale with price snapshot at time of sale."""

    sale = models.ForeignKey(
        Sale,
        on_delete=models.CASCADE,
        related_name='sale_toppings',
    )
    topping = models.ForeignKey(
        Topping,
        on_delete=models.PROTECT,
        related_name='sale_toppings',
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['sale', 'topping']
        ordering = ['id']

    def __str__(self):
        return f'{self.topping.name} x {self.quantity}'

    @property
    def subtotal(self):
        return self.quantity * self.unit_price


class InventoryMovement(models.Model):
    """Ledger entry for every inventory change."""

    MOVEMENT_TYPE_CHOICES = [
        ('IN', 'In'),
        ('OUT', 'Out'),
    ]

    SOURCE_CHOICES = [
        ('PURCHASE', 'Purchase'),
        ('SALE', 'Sale'),
        ('USAGE', 'Usage'),
        ('WASTE', 'Waste'),
        ('ADJUSTMENT', 'Adjustment'),
    ]

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='inventory_movements',
    )
    movement_type = models.CharField(max_length=3, choices=MOVEMENT_TYPE_CHOICES)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    source = models.CharField(max_length=12, choices=SOURCE_CHOICES)
    purchase = models.OneToOneField(
        Purchase,
        on_delete=models.CASCADE,
        related_name='inventory_movement',
        null=True,
        blank=True,
    )
    sale = models.ForeignKey(
        Sale,
        on_delete=models.CASCADE,
        related_name='inventory_movements',
        null=True,
        blank=True,
    )
    movement_date = models.DateField(default=date.today)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='kitchen_inventory_movements',
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-movement_date', '-created_at']

    def __str__(self):
        return f"{self.get_movement_type_display()} {self.quantity} {self.product.name}"
