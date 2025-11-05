from rest_framework import viewsets
from . import models, serializers
from rest_framework.decorators import action
from django.db import connection
from django.db.models import Prefetch
from rest_framework.response import Response
from django.db import transaction
from rest_framework.permissions import IsAuthenticated


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = models.Category.objects.all()
    serializer_class = serializers.CategorySerializer
    permission_classes = [IsAuthenticated]


class DishViewSet(viewsets.ModelViewSet):
    queryset = models.Dish.objects.all()
    serializer_class = serializers.DishSerializer
    permission_classes = [IsAuthenticated]

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
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def in_kitchen(self, request):
        orders = models.Order.objects.filter(status='IK').prefetch_related(
            Prefetch(
                'orderitem_set',
                queryset=models.OrderItem.objects.select_related('dish__category', 'dish')
            )
        )
        serializer = serializers.GetOrderInKitchenSerializer(orders, many=True)
        return Response(serializer.data)


    @action(detail=False, methods=['get'])
    def by_status(self, request):
        status = request.query_params.get('status')
        if not status:
            return Response({'error': 'status parameter is required'}, status=400)
        
        orders = models.Order.objects.filter(status=status).select_related(
            'customer', 'address'
        ).prefetch_related(
            Prefetch(
                'orderitem_set',
                queryset=models.OrderItem.objects.select_related('dish__category', 'category')
            )
        )
        serializer = serializers.GetOrderByStatusSerializer(orders, many=True)
        return Response(serializer.data)


class OrderItemViewSet(viewsets.ModelViewSet):
    queryset = models.OrderItem.objects.select_related('dish', 'category', 'order')
    serializer_class = serializers.OrderItemSerializer
    permission_classes = [IsAuthenticated]

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
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def by_name(self, request):
        name = request.query_params.get('name')
        if not name:
            return Response({'error': 'name parameter is required'}, status=400)
        
        customers = models.Customer.objects.filter(first_name__icontains=name) | models.Customer.objects.filter(last_name__icontains=name)
        serializer = serializers.CustomerSerializer(customers, many=True)
        return Response(serializer.data)


class AddressViewSet(viewsets.ModelViewSet):
    queryset = models.Address.objects.all()
    serializer_class = serializers.AddressSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def by_customer(self, request):
        customer_id = request.query_params.get('customer_id')
        if not customer_id:
            return Response({'error': 'customer_id parameter is required'}, status=400)
        
        addresses = models.Address.objects.filter(customer_id=customer_id)
        serializer = serializers.AddressSerializer(addresses, many=True)
        return Response(serializer.data)


class AccountViewSet(viewsets.ModelViewSet):
    queryset = models.Account.objects.all()
    serializer_class = serializers.AccountSerializer
    permission_classes = [IsAuthenticated]


class TransactionViewSet(viewsets.ModelViewSet):
    queryset = models.Transaction.objects.all()
    serializer_class = serializers.TransactionSerializer
    permission_classes = [IsAuthenticated]