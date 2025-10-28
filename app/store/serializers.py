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


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Customer
        fields = '__all__'


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Address
        fields = '__all__'
