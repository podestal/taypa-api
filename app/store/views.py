from rest_framework import viewsets
from . import models, serializers
from rest_framework.decorators import action
from django.db import connection
from rest_framework.response import Response
from django.db import transaction


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = models.Category.objects.all()
    serializer_class = serializers.CategorySerializer


class DishViewSet(viewsets.ModelViewSet):
    queryset = models.Dish.objects.all()
    serializer_class = serializers.DishSerializer

    @action(detail=False, methods=['get'])
    def by_category(self, request):
        category_id = request.query_params.get('category_id')
        if not category_id:
            return Response({'error': 'category_id parameter is required'}, status=400)
        
        dishes = models.Dish.objects.filter(category_id=category_id)
        serializer = serializers.DishSerializer(dishes, many=True)
        return Response(serializer.data)


class OrderViewSet(viewsets.ModelViewSet):
    queryset = models.Order.objects.all()
    serializer_class = serializers.OrderSerializer


class OrderItemViewSet(viewsets.ModelViewSet):
    queryset = models.OrderItem.objects.select_related('dish', 'category', 'order')
    serializer_class = serializers.OrderItemSerializer

    @action(detail=False, methods=['get'])
    def by_order(self, request):
        order_id = request.query_params.get('order_id')
        if not order_id:
            return Response({'error': 'order_id parameter is required'}, status=400)
        
        order_items = models.OrderItem.objects.filter(order_id=order_id)
        serializer = serializers.GetOrderItemByOrderSerializer(order_items, many=True)
        return Response(serializer.data)


class CustomerViewSet(viewsets.ModelViewSet):
    queryset = models.Customer.objects.all()
    serializer_class = serializers.CustomerSerializer

    @action(detail=False, methods=['get'])
    def by_name(self, request):
        name = request.query_params.get('name')
        if not name:
            return Response({'error': 'name parameter is required'}, status=400)
        
        customers = models.Customer.objects.filter(first_name__icontains=name) | models.Customer.objects.filter(last_name__icontains=name)
        serializer = serializers.CustomerSerializer(customers, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_first_name(self, request):
        first_name = request.query_params.get('first_name')
        if not first_name:
            return Response({'error': 'first_name parameter is required'}, status=400)
        
        sql_query = 'SELECT id FROM store_customer WHERE first_name ILIKE %s LIMIT 10'
        with connection.cursor() as cursor:
            cursor.execute(sql_query, [f'{first_name}%'])
            results = cursor.fetchall()  
        customer_ids = [row[0] for row in results]
        customers = models.Customer.objects.filter(id__in=customer_ids)
        serializer = serializers.CustomerSerializer(customers, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_last_name(self, request):
        last_name = request.query_params.get('last_name')
        if not last_name:
            return Response({'error': 'last_name parameter is required'}, status=400)
        
        sql_query = 'SELECT id FROM store_customer WHERE last_name ILIKE %s LIMIT 10'
        with connection.cursor() as cursor:
            cursor.execute(sql_query, [f'{last_name}%'])
            results = cursor.fetchall()
        customer_ids = [row[0] for row in results]
        customers = models.Customer.objects.filter(id__in=customer_ids)
        serializer = serializers.CustomerSerializer(customers, many=True)
        return Response(serializer.data)


class AddressViewSet(viewsets.ModelViewSet):
    queryset = models.Address.objects.all()
    serializer_class = serializers.AddressSerializer

    @action(detail=False, methods=['get'])
    def by_customer(self, request):
        customer_id = request.query_params.get('customer_id')
        if not customer_id:
            return Response({'error': 'customer_id parameter is required'}, status=400)
        
        addresses = models.Address.objects.filter(customer_id=customer_id)
        serializer = serializers.AddressSerializer(addresses, many=True)
        return Response(serializer.data)
