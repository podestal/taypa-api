from datetime import date, timedelta, datetime
from decimal import Decimal
from rest_framework import viewsets
from . import models, serializers
from . import pagination
from rest_framework.decorators import action
from django.db import connection
from django.db.models import Prefetch, Sum
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.utils.dateparse import parse_date
from django.utils import timezone


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = models.Category.objects.all()
    serializer_class = serializers.CategorySerializer
    # permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.request.method in ['GET', 'HEAD', 'OPTIONS']:
            return [AllowAny()]
        return [IsAuthenticated()]

    
    @action(detail=False, methods=['get'])
    def for_menu(self, request):
        """Get categories for online menu"""
        categories = self.queryset.filter(is_menu_category=True).order_by('id')
        serializer = serializers.CategorySerializer(categories, many=True)
        return Response(serializer.data)


class DishViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Dish model.
    
    Image uploads are automatically handled by Django's ImageField with R2Storage.
    When creating or updating a dish with an image, the file is automatically
    uploaded to Cloudflare R2 and the public URL is saved in the database.
    """
    queryset = models.Dish.objects.all()
    serializer_class = serializers.DishSerializer
    # permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method in ['GET', 'HEAD', 'OPTIONS']:
            return [AllowAny()]
        return [IsAuthenticated()]

    @action(detail=False, methods=['get'])
    def by_category(self, request):
        category_id = request.query_params.get('category_id')
        if not category_id:
            return Response({'error': 'category_id parameter is required'}, status=400)
        
        dishes = models.Dish.objects.filter(category_id=category_id)
        serializer = serializers.DishSerializer(dishes, many=True)
        return Response(serializer.data)


class OrderViewSet(viewsets.ModelViewSet):
    queryset = models.Order.objects.order_by('-created_at').select_related('customer', 'address', 'document')
    serializer_class = serializers.OrderSerializer
    # permission_classes = [IsAuthenticated]
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
            order=order,
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
        
        # Call parent update method - this will save the changes
        response = super().update(request, *args, **kwargs)
        
        # Check if status changed and create transaction if needed
        instance.refresh_from_db()
        new_status = instance.status
        
        if old_status != new_status and new_status in ['HA', 'DO']:
            # Check if transaction already exists for this order to avoid duplicates
            order_number_in_description = f"Order {instance.order_number}"
            existing_transaction = models.Transaction.objects.filter(
                description__contains=order_number_in_description,
                transaction_type='I'  # Only check income transactions
            ).first()
            
            if not existing_transaction:
                # Create income transaction
                self._create_income_transaction(instance, request.user)
        
        return response
    
    def partial_update(self, request, *args, **kwargs):
        """Override partial_update to create income transaction when status changes to HA or DO"""
        instance = self.get_object()
        old_status = instance.status
        
        # Call parent partial_update method - this will save the changes
        response = super().partial_update(request, *args, **kwargs)
        
        # Check if status changed and create transaction if needed
        instance.refresh_from_db()
        new_status = instance.status
        
        if old_status != new_status and new_status in ['HA', 'DO']:
            # Check if transaction already exists for this order to avoid duplicates
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
        
        # Base queryset filtered by status
        orders = models.Order.objects.filter(status=status)
        
        # Only filter by today's date if status is "HA" (Handed) or "DO" (Delivered)
        if status in ['HA', 'DO']:
            now = timezone.now()
            start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = start_of_day + timedelta(days=1)
            orders = orders.filter(
                created_at__gte=start_of_day,
                created_at__lt=end_of_day
            )
        
        orders = orders.select_related(
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
    queryset = models.Transaction.objects.select_related('account', 'category').order_by('transaction_date')
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

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """
        Get aggregated transaction stats for dashboards.

        Endpoint:
        - GET /transactions/stats/

        Query params:
        - period: today | last7days | thisWeek | thisMonth | custom | all
        - granularity: day | week | month | year
        - start_date: YYYY-MM-DD (required when period=custom)
        - end_date: YYYY-MM-DD (required when period=custom)
        - currency: string (default PEN)
        - timezone: string (default America/Lima)

        Notes:
        - income_vs_expense_by_day is bucketed according to granularity.
        - granularity=year returns one bucket per month.
        - expense_by_category only includes expense transactions.

        Example:
        - /transactions/stats/?period=all&granularity=year
        """
        period = request.query_params.get('period', 'thisMonth')
        granularity = request.query_params.get('granularity', 'day')
        currency = request.query_params.get('currency', 'PEN')
        timezone_name = request.query_params.get('timezone', 'America/Lima')

        if granularity not in ['day', 'week', 'month', 'year']:
            return Response(
                {'error': 'invalid granularity. Use day, week, month, or year'},
                status=400
            )

        today = date.today()
        start_date = None
        end_date = today

        if period == 'today':
            start_date = today
        elif period == 'last7days':
            start_date = today - timedelta(days=6)
        elif period == 'thisWeek':
            start_date = today - timedelta(days=today.weekday())
        elif period == 'thisMonth':
            start_date = today.replace(day=1)
        elif period == 'custom':
            start_date_raw = request.query_params.get('start_date')
            end_date_raw = request.query_params.get('end_date')
            if not start_date_raw or not end_date_raw:
                return Response({'error': 'start_date and end_date are required for custom period'}, status=400)

            start_date = parse_date(start_date_raw)
            end_date = parse_date(end_date_raw)
            if not start_date or not end_date:
                return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=400)
            if start_date > end_date:
                return Response({'error': 'start_date must be before or equal to end_date'}, status=400)
        elif period == 'all':
            first_transaction = models.Transaction.objects.order_by('transaction_date').first()
            start_date = first_transaction.transaction_date if first_transaction else today
        else:
            return Response(
                {'error': 'invalid period. Use today, last7days, thisWeek, thisMonth, custom, or all'},
                status=400
            )

        transactions = models.Transaction.objects.select_related('category').filter(
            transaction_date__gte=start_date,
            transaction_date__lte=end_date
        )

        income_total = transactions.filter(transaction_type='I').aggregate(total=Sum('amount'))['total'] or Decimal('0')
        expense_total = transactions.filter(transaction_type='E').aggregate(total=Sum('amount'))['total'] or Decimal('0')
        net_total = income_total - expense_total

        def _month_start(value):
            return value.replace(day=1)

        def _next_month(value):
            if value.month == 12:
                return value.replace(year=value.year + 1, month=1, day=1)
            return value.replace(month=value.month + 1, day=1)

        def _bucket_start(value):
            if granularity == 'day':
                return value
            if granularity == 'week':
                return value - timedelta(days=value.weekday())
            if granularity in ['month', 'year']:
                return _month_start(value)
            return value

        def _bucket_step(value):
            if granularity == 'day':
                return value + timedelta(days=1)
            if granularity == 'week':
                return value + timedelta(days=7)
            if granularity in ['month', 'year']:
                return _next_month(value)
            return value + timedelta(days=1)

        start_bucket = _bucket_start(start_date)
        end_bucket = _bucket_start(end_date)

        bucket_map = {}
        current_bucket = start_bucket
        while current_bucket <= end_bucket:
            bucket_map[current_bucket] = {
                'date': current_bucket.isoformat(),
                'income': Decimal('0'),
                'expense': Decimal('0'),
                'net': Decimal('0'),
            }
            current_bucket = _bucket_step(current_bucket)

        for tx in transactions:
            bucket_key = _bucket_start(tx.transaction_date)
            bucket_entry = bucket_map.get(bucket_key)
            if not bucket_entry:
                continue
            if tx.transaction_type == 'I':
                bucket_entry['income'] += tx.amount
            elif tx.transaction_type == 'E':
                bucket_entry['expense'] += tx.amount
            bucket_entry['net'] = bucket_entry['income'] - bucket_entry['expense']

        income_vs_expense_by_day = []
        for row in bucket_map.values():
            income_vs_expense_by_day.append({
                'date': row['date'],
                'income': float(row['income']),
                'expense': float(row['expense']),
                'net': float(row['net']),
            })

        expenses_by_category_qs = transactions.filter(transaction_type='E').values(
            'category_id',
            'category__name'
        ).annotate(
            value=Sum('amount')
        ).order_by('-value')

        expense_by_category = []
        for category_row in expenses_by_category_qs:
            value = category_row['value'] or Decimal('0')
            percentage = Decimal('0')
            if expense_total > 0:
                percentage = (value / expense_total) * Decimal('100')

            expense_by_category.append({
                'category_id': category_row['category_id'],
                'category_name': category_row['category__name'] or 'Uncategorized',
                'value': float(value),
                'percentage': round(float(percentage), 2),
            })

        return Response({
            'meta': {
                'currency': currency,
                'timezone': timezone_name,
                'period': period,
                'granularity': granularity,
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
            },
            'totals': {
                'income': float(income_total),
                'expense': float(expense_total),
                'net': float(net_total),
            },
            'income_vs_expense_by_day': income_vs_expense_by_day,
            'expense_by_category': expense_by_category,
        })

    
    def perform_create(self, serializer):
        """Set created_by to the current user"""
        serializer.save(created_by=self.request.user)