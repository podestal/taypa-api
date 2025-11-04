from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import date, timedelta


class Category(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Dish(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Customer(models.Model):
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Address(models.Model):
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
        
        super().save(*args, **kwargs)
    
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
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    dish = models.ForeignKey(Dish, on_delete=models.PROTECT)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.IntegerField()
    observation = models.TextField(blank=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
