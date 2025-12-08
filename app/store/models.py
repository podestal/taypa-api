from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import date, timedelta
from taxes.models import Document


class Category(models.Model):
    """
    Represents a category
    """
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    is_menu_category = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class Dish(models.Model):
    """
    Represents a dish
    """
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(upload_to='dishes/', blank=True, null=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Customer(models.Model):
    """
    Represents a customer
    """
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Address(models.Model):
    """
    Represents an address
    """
    street = models.CharField(max_length=255)
    reference = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_primary = models.BooleanField(default=False)
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name='addresses')

    def __str__(self):
        return f"{self.street} - {self.reference}"


class Order(models.Model):
    """
    Represents an order
    """
    ORDER_STATUS_CHOICES = [
        ('IP', 'In Progress'),
        ('IK', 'In Kitchen'),
        ('PA', 'Packing'),
        ('HA', 'Handed'),
        ('IT', 'In Transit'),
        ('DO', 'Delivered'),
        ('CA', 'Cancelled'),
    ]

    ORDER_TYPE_CHOICES = [
        ('T', 'Table'),
        ('D', 'Delivery'),
        ('G', 'To Go'),
    ]

    order_type = models.CharField(max_length=2, choices=ORDER_TYPE_CHOICES, default='G')
    status = models.CharField(max_length=2, choices=ORDER_STATUS_CHOICES, default='IP')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='orders'
    )
    order_number = models.CharField(max_length=255)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, blank=True, null=True)
    address = models.ForeignKey(Address, on_delete=models.CASCADE, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Status timestamp fields - automatically populated when status changes
    in_kitchen_at = models.DateTimeField(null=True, blank=True)
    packing_at = models.DateTimeField(null=True, blank=True)
    handed_at = models.DateTimeField(null=True, blank=True)
    in_transit_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    document = models.ForeignKey(Document, on_delete=models.SET_NULL, null=True, blank=True)

    def save(self, *args, **kwargs):
        # Generate order number if not set
        if not self.order_number:
            today = date.today()
            
            # Count how many orders were created today
            today_orders = Order.objects.filter(
                created_at__date=today
            ).count()
            
            # Add 1 to get the next number
            next_number = today_orders + 1
            
            # Format: YYYYMMDD-1, YYYYMMDD-2, etc.
            self.order_number = f"{today.strftime('%Y%m%d')}-{next_number}"
        
        # Track status changes and set timestamps
        old_status = None
        if self.pk:  # Only check for status changes if order already exists
            try:
                old_instance = Order.objects.get(pk=self.pk)
                old_status = old_instance.status
                
                # If status changed, update the corresponding timestamp
                if old_status != self.status:
                    now = timezone.now()
                    
                    if self.status == 'IK' and not self.in_kitchen_at:
                        self.in_kitchen_at = now
                    elif self.status == 'PA' and not self.packing_at:
                        self.packing_at = now
                    elif self.status == 'HA' and not self.handed_at:
                        self.handed_at = now
                    elif self.status == 'IT' and not self.in_transit_at:
                        self.in_transit_at = now
                    elif self.status == 'DO' and not self.delivered_at:
                        self.delivered_at = now
                    elif self.status == 'CA' and not self.cancelled_at:
                        self.cancelled_at = now
            except Order.DoesNotExist:
                pass
        
        # Save the order first
        super().save(*args, **kwargs)
        
        # Send WebSocket messages after save if status changed
        if old_status is not None and old_status != self.status:
            self._send_websocket_update(old_status, self.status)
    
    def _send_websocket_update(self, old_status, new_status):
        """Send WebSocket update when order status changes"""
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            
            channel_layer = get_channel_layer()
            if channel_layer:
                # Send WebSocket update when order status becomes IK (add to kitchen)
                if new_status == 'IK':
                    async_to_sync(channel_layer.group_send)(
                        'order_updates',
                        {
                            'type': 'order_update',
                            'order_id': str(self.id),
                            'status': new_status,
                            'action': 'added',
                        }
                    )
                
                # Send WebSocket update when order moves from IK to PA (remove from kitchen)
                elif old_status == 'IK' and new_status == 'PA':
                    async_to_sync(channel_layer.group_send)(
                        'order_updates',
                        {
                            'type': 'order_update',
                            'order_id': str(self.id),
                            'status': new_status,
                            'action': 'removed',
                        }
                    )
        except Exception:
            # Silently fail - don't break order saving if WebSocket fails
            pass
    
    # Helper methods to calculate duration for each stage
    def get_current_stage_duration(self):
        """Returns how long the order has been in the current stage"""
        stage_start_map = {
            'IP': self.created_at,
            'IK': self.in_kitchen_at,
            'PA': self.packing_at,
            'HA': self.handed_at,
            'IT': self.in_transit_at,
            'DO': self.delivered_at,
            'CA': self.cancelled_at,
        }
        
        stage_start = stage_start_map.get(self.status)
        if stage_start:
            return timezone.now() - stage_start
        return None


class OrderItem(models.Model):
    """
    Represents an item in an order
    """
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    dish = models.ForeignKey(Dish, on_delete=models.PROTECT)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.IntegerField()
    observation = models.TextField(blank=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Account(models.Model):
    """Represents a bank account or savings account"""
    name = models.CharField(max_length=255, help_text="Account name (e.g., 'Main Bank', 'Savings')")
    balance = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0.00,
        help_text="Current balance in the account"
    )
    account_type = models.CharField(
        max_length=50,
        choices=[
            ('CH', 'Checking'),
            ('SA', 'Savings'),
            ('CA', 'Cash'),
            ('OT', 'Other'),
        ],
        default='CH'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} - ${self.balance}"


class Transaction(models.Model):
    """Represents a financial transaction (income or expense)"""
    
    TRANSACTION_TYPE_CHOICES = [
        ('I', 'Income'),
        ('E', 'Expense'),
    ]
    
    transaction_type = models.CharField(
        max_length=10,
        choices=TRANSACTION_TYPE_CHOICES
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Transaction amount (always positive)"
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='transactions',
        null=True,
        blank=True
    )
    description = models.TextField(
        blank=True,
        help_text="Description or notes about the transaction"
    )
    transaction_date = models.DateField(
        default=date.today,
        help_text="Date when the transaction occurred"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    
    def __str__(self):
        return f"{self.get_transaction_type_display()} - ${self.amount} - {self.transaction_date}"
    
    def save(self, *args, **kwargs):
        """
        Override save to automatically update account balance.
        This ensures balance is always correct regardless of how transaction is created/updated.
        """
        is_new = self.pk is None
        
        # If this is a new transaction, update the account balance
        if is_new:
            super().save(*args, **kwargs)
            # Update account balance based on transaction type
            if self.transaction_type == 'I':  # Income
                self.account.balance += self.amount
            elif self.transaction_type == 'E':  # Expense
                self.account.balance -= self.amount
            self.account.save()
        else:
            # For updates, we need to handle balance correction
            # Get the old transaction to reverse its effect
            old_transaction = Transaction.objects.get(pk=self.pk)
            
            # Reverse old transaction effect
            if old_transaction.transaction_type == 'I':  # Income
                self.account.balance -= old_transaction.amount
            elif old_transaction.transaction_type == 'E':  # Expense
                self.account.balance += old_transaction.amount
            
            # Apply new transaction effect
            if self.transaction_type == 'I':  # Income
                self.account.balance += self.amount
            elif self.transaction_type == 'E':  # Expense
                self.account.balance -= self.amount
            
            self.account.save()
            super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        # Reverse the transaction effect on account balance before deleting
        if self.transaction_type == 'I':  # Income
            self.account.balance -= self.amount
        elif self.transaction_type == 'E':  # Expense
            self.account.balance += self.amount
        self.account.save()
        super().delete(*args, **kwargs)
