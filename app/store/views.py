from datetime import date, timedelta, datetime
from decimal import Decimal
from rest_framework import viewsets
from . import models, serializers
from . import pagination
from rest_framework.decorators import action
from django.db import connection
from django.db.models import Prefetch
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils.dateparse import parse_date
from django.utils import timezone


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
    pagination_class = pagination.SimplePagination
    
    def _get_default_account(self):
        """Get the default account (first active account, or create one if none exists)"""
        try:
            account = models.Account.objects.filter(is_active=True).first()
            if not account:
                # Create a default account if none exists
                account = models.Account.objects.create(
                    name='Default Account',
                    balance=Decimal('0.00'),
                    account_type='CH',
                    is_active=True
                )
            return account
        except Exception:
            # Fallback: create a default account
            return models.Account.objects.create(
                name='Default Account',
                balance=Decimal('0.00'),
                account_type='CH',
                is_active=True
            )
    
    def _calculate_order_total(self, order):
        """Calculate total amount from order items"""
        items = order.orderitem_set.all()
        # item.price already includes the total for that item (price * quantity)
        return sum(item.price for item in items)
    
    def _create_income_transaction(self, order, user):
        """Create an income transaction for the order"""
        account = self._get_default_account()
        total_amount = self._calculate_order_total(order)
        
        # Create income transaction
        models.Transaction.objects.create(
            transaction_type='I',  # Income
            account=account,
            amount=total_amount,
            description=f"Order {order.order_number} - {order.get_status_display()}",
            transaction_date=date.today(),
            created_by=user
        )
    
    def update(self, request, *args, **kwargs):
        """Override update to create income transaction when status changes to HA or DO"""
        instance = self.get_object()
        old_status = instance.status
        
        # Call parent update method
        response = super().update(request, *args, **kwargs)
        
        # Check if status changed to HA or DO
        instance.refresh_from_db()
        new_status = instance.status
        
        if old_status != new_status and new_status in ['HA', 'DO']:
            # Check if transaction already exists for this order to avoid duplicates
            # We check by order number in description to prevent creating multiple transactions
            order_number_in_description = f"Order {instance.order_number}"
            existing_transaction = models.Transaction.objects.filter(
                description__contains=order_number_in_description,
                transaction_type='I'  # Only check income transactions
            ).first()
            
            if not existing_transaction:
                # Create income transaction
                self._create_income_transaction(instance, request.user)
        
        return response

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
        
        # Filter by today's date using timezone-aware datetime range
        now = timezone.now()
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)
        
        orders = models.Order.objects.filter(
            status=status,
            created_at__gte=start_of_day,
            created_at__lt=end_of_day
        ).select_related(
            'customer', 'address'
        ).prefetch_related(
            Prefetch(
                'orderitem_set',
                queryset=models.OrderItem.objects.select_related('dish__category', 'category')
            )
        )
        serializer = serializers.GetOrderByStatusSerializer(orders, many=True)
        return Response(serializer.data)

    
    @action(detail=False, methods=['get'], url_path='for-billing')
    def for_billing(self, request):
        """
        Get orders for billing with filters and pagination.
        Filters:
        - status: Filter by order status (IP, IK, PA, HA, IT, DO, CA)
        - date: Filter by specific date (YYYY-MM-DD)
        - start_date: Start date for date range (YYYY-MM-DD)
        - end_date: End date for date range (YYYY-MM-DD)
        """
        # Start with base queryset - prefetch related data for performance
        orders = models.Order.objects.select_related(
            'customer', 'address', 'document'
        ).prefetch_related(
            Prefetch(
                'orderitem_set',
                queryset=models.OrderItem.objects.select_related('dish', 'category')
            )
        ).order_by('-created_at')
        
        # Filter by status
        status = request.query_params.get('status')
        if status:
            if status not in dict(models.Order.ORDER_STATUS_CHOICES):
                return Response(
                    {'error': f'Invalid status. Valid options: {", ".join([s[0] for s in models.Order.ORDER_STATUS_CHOICES])}'},
                    status=400
                )
            orders = orders.filter(status=status)
        
        # Filter by date (single day)
        date_filter = request.query_params.get('date')
        if date_filter:
            try:
                filter_date = parse_date(date_filter)
                if not filter_date:
                    return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=400)
                orders = orders.filter(created_at__date=filter_date)
            except ValueError:
                return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=400)
        
        # Filter by date range
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        if start_date and end_date:
            try:
                start = parse_date(start_date)
                end = parse_date(end_date)
                if not start or not end:
                    return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=400)
                if start > end:
                    return Response({'error': 'start_date must be before or equal to end_date'}, status=400)
                orders = orders.filter(created_at__date__gte=start, created_at__date__lte=end)
            except ValueError:
                return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=400)
        elif start_date or end_date:
            return Response({'error': 'Both start_date and end_date are required for date range filter'}, status=400)
        
        # Paginate results
        page = self.paginate_queryset(orders)
        if page is not None:
            serializer = serializers.OrderForBillingSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        # If no pagination, return all results
        serializer = serializers.OrderForBillingSerializer(orders, many=True)
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
    queryset = models.Transaction.objects.select_related('account', 'category').order_by('-transaction_date')
    serializer_class = serializers.TransactionSerializer
    # permission_classes = [IsAuthenticated]
    pagination_class = pagination.SimplePagination

    def list(self, request, *args, **kwargs):
        """
        Filter transactions by date and transaction type.
        date_filter: 'today' | 'last7days' | 'thisWeek' | 'thisMonth' | 'custom' | 'all'
        transaction_type: 'I' | 'E' | 'all'
        sort_by: 'date' | 'amount'
        """
        date_filter = request.query_params.get('date_filter', 'today')
        transaction_type = request.query_params.get('transaction_type', 'all')
        sort_by = request.query_params.get('sort_by', 'date')
        
        # Start with base queryset
        transactions = self.queryset

        # Sort by date or amount
        if sort_by == 'date':
            transactions = transactions.order_by('-transaction_date')
        elif sort_by == 'amount':
            transactions = transactions.order_by('-amount')

        # Filter by transaction type
        if transaction_type == 'I':
            transactions = transactions.filter(transaction_type='I')
        elif transaction_type == 'E':
            transactions = transactions.filter(transaction_type='E')
        elif transaction_type != 'all':
            return Response({'error': 'invalid transaction_type parameter. Use I, E, or all'}, status=400)

        # Filter by date (chain on the already filtered transactions)
        if date_filter == 'today':
            transactions = transactions.filter(transaction_date=date.today())
        elif date_filter == 'last7days':
            transactions = transactions.filter(transaction_date__gte=date.today() - timedelta(days=7))
        elif date_filter == 'thisWeek':
            # Get start of week (Monday)
            today = date.today()
            start_of_week = today - timedelta(days=today.weekday())
            transactions = transactions.filter(transaction_date__gte=start_of_week)
        elif date_filter == 'thisMonth':
            # Get start of month
            today = date.today()
            start_of_month = today.replace(day=1)
            transactions = transactions.filter(transaction_date__gte=start_of_month)
        elif date_filter == 'custom':
            start_date = request.query_params.get('start_date')
            end_date = request.query_params.get('end_date')
            if not start_date or not end_date:
                return Response({'error': 'start_date and end_date parameters are required for custom filter'}, status=400)
            transactions = transactions.filter(transaction_date__gte=start_date, transaction_date__lte=end_date)
        elif date_filter != 'all':
            return Response({'error': 'invalid date_filter parameter'}, status=400)
        
        page = self.paginate_queryset(transactions)
        if page is not None:
            serializer = serializers.TransactionSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = serializers.TransactionSerializer(transactions, many=True)
        return Response(serializer.data)
    
    def perform_create(self, serializer):
        """Set created_by to the current user"""
        serializer.save(created_by=self.request.user)