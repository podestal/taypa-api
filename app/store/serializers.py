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

    class Meta:
        model = models.Order
        fields = ['id', 'order_number', 'updated_at', 'categories']

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


class GetOrderByStatusSerializer(serializers.ModelSerializer):
    customer_name = serializers.SerializerMethodField()
    address_info = serializers.SerializerMethodField()
    categories = serializers.SerializerMethodField()

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

class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Customer
        fields = '__all__'


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Address
        fields = '__all__'
