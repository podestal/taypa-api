import rest_framework.serializers as serializers
from . import models


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Category
        fields = '__all__'


class DishSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Dish
        fields = '__all__'
    
    def to_representation(self, instance):
        """Override to ensure image URL uses R2 storage URL"""
        representation = super().to_representation(instance)
        if instance.image:
            # Force use of storage's url method to get the correct R2 URL
            # This ensures we get the R2 public URL, not the local MEDIA_URL
            try:
                # Get the storage instance
                storage = instance.image.storage
                # Get the file name/path
                file_name = instance.image.name
                # Call the storage's url method directly
                representation['image'] = storage.url(file_name)
            except Exception as e:
                # If URL generation fails, try fallback
                try:
                    representation['image'] = instance.image.url
                except Exception:
                    representation['image'] = None
        return representation


class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Order
        fields = '__all__'
        read_only_fields = ['order_number']


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.OrderItem
        fields = '__all__'


class GetOrderItemByOrderSerializer(serializers.ModelSerializer):
    dish = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    
    class Meta:
        model = models.OrderItem
        fields = ['id', 'dish', 'category', 'quantity', 'price', 'observation']

    def get_dish(self, obj):
        return obj.dish.name

    def get_category(self, obj):
        return obj.dish.category.name


class GetOrderInKitchenSerializer(serializers.ModelSerializer):
    categories = serializers.SerializerMethodField()
    time_in_current_stage = serializers.SerializerMethodField()

    class Meta:
        model = models.Order
        fields = ['id', 'order_number', 'updated_at', 'in_kitchen_at', 'time_in_current_stage', 'categories']

    def get_categories(self, obj):
        items = getattr(obj, 'orderitem_set').all()
        grouped = {}
        for item in items:
            category_name = item.dish.category.name if item.dish and item.dish.category else 'Sin Categoria'
            if category_name not in grouped:
                grouped[category_name] = []
            grouped[category_name].append({
                'id': item.id,
                'dish': item.dish.name,
                'quantity': item.quantity,
                'observation': item.observation,
            })
        return grouped
    
    def get_time_in_current_stage(self, obj):
        """Returns time in minutes the order has been in current stage"""
        duration = obj.get_current_stage_duration()
        if duration:
            return round(duration.total_seconds() / 60, 1)  # Returns minutes
        return None


class GetOrderByStatusSerializer(serializers.ModelSerializer):
    customer_name = serializers.SerializerMethodField()
    address_info = serializers.SerializerMethodField()
    categories = serializers.SerializerMethodField()
    time_in_current_stage = serializers.SerializerMethodField()

    class Meta:
        model = models.Order
        fields = [
            'id', 
            'order_number', 
            'order_type', 
            'created_at', 
            'updated_at', 
            'status', 
            'customer_name',
            'address_info',
            'created_by',
            'categories',
            'time_in_current_stage',
            # Timestamp fields for each stage
            'in_kitchen_at',
            'packing_at',
            'handed_at',
            'in_transit_at',
            'delivered_at',
            'cancelled_at',
        ]
    
    def get_customer_name(self, obj):
        """Return customer full name or empty string if no customer"""
        if obj.customer:
            return f"{obj.customer.first_name} {obj.customer.last_name}"
        return ""
    
    def get_address_info(self, obj):
        """Return address street and reference or empty string if no address"""
        if obj.address:
            return f"{obj.address.street} - {obj.address.reference}"
        return ""

    def get_categories(self, obj):
        items = getattr(obj, 'orderitem_set').all()
        grouped = {}
        for item in items:
            category_name = item.dish.category.name if item.dish and item.dish.category else 'Sin Categoria'
            if category_name not in grouped:
                grouped[category_name] = []
            grouped[category_name].append({
                'id': item.id,
                'dish': item.dish.name,
                'quantity': item.quantity,
                'observation': item.observation,
                'price': item.price,
            })
        return grouped
    
    def get_time_in_current_stage(self, obj):
        """Returns time in minutes the order has been in current stage"""
        duration = obj.get_current_stage_duration()
        if duration:
            return round(duration.total_seconds() / 60, 1)  # Returns minutes
        return None


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Customer
        fields = '__all__'


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Address
        fields = '__all__'


class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Account
        fields = '__all__'


class TransactionSerializer(serializers.ModelSerializer):
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta:
        model = models.Transaction
        fields = '__all__'


class OrderForBillingSerializer(serializers.ModelSerializer):
    """Serializer for orders in billing view - includes all info needed for Sunat document creation"""
    order_items = serializers.SerializerMethodField()
    total_amount = serializers.SerializerMethodField()
    customer_name = serializers.SerializerMethodField()
    customer_phone = serializers.SerializerMethodField()
    customer_ruc = serializers.SerializerMethodField()
    customer_address = serializers.SerializerMethodField()
    has_document = serializers.SerializerMethodField()
    
    class Meta:
        model = models.Order
        fields = [
            'id',
            'order_number',
            'status',
            'created_at',
            'order_type',
            'customer_name',
            'customer_phone',
            'customer_ruc',
            'customer_address',
            'order_items',
            'total_amount',
            'has_document',
            'document',  # Document ID if exists
        ]
    
    def get_order_items(self, obj):
        """Format order items for Sunat document creation"""
        items = obj.orderitem_set.all()
        return [
            {
                'id': str(item.dish.id) if item.dish else str(item.id),
                'name': f"{item.dish.category.name} - {item.dish.name}" if item.dish and item.dish.category else 'Producto',
                'quantity': item.quantity,
                'cost': float(item.price),  # Price already includes IGV
            }
            for item in items
        ]
    
    def get_total_amount(self, obj):
        """Calculate total amount from order items"""
        items = obj.orderitem_set.all()
        return float(sum(item.price for item in items))
    
    def get_customer_name(self, obj):
        """Return customer full name"""
        if obj.customer:
            return f"{obj.customer.first_name} {obj.customer.last_name}"
        return ""
    
    def get_customer_phone(self, obj):
        """Return customer phone"""
        if obj.customer:
            return obj.customer.phone_number
        return ""
    
    def get_customer_ruc(self, obj):
        """Return customer RUC (if available)"""
        # TODO: Add RUC field to Customer model if needed
        # For now, return empty string
        return ""
    
    def get_customer_address(self, obj):
        """Return customer address"""
        if obj.address:
            return f"{obj.address.street} - {obj.address.reference}"
        return ""
    
    def get_has_document(self, obj):
        """Check if order already has a Sunat document"""
        return obj.document is not None