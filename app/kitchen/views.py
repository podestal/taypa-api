from django.db import transaction as db_transaction
from django.utils.dateparse import parse_date
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import finances, inventory, models, serializers


class ProductViewSet(viewsets.ModelViewSet):
    queryset = models.Product.objects.all()
    serializer_class = serializers.ProductSerializer
    permission_classes = [IsAuthenticated]


class AccountViewSet(viewsets.ModelViewSet):
    queryset = models.Account.objects.filter(is_active=True)
    serializer_class = serializers.AccountSerializer
    permission_classes = [IsAuthenticated]


class TransactionViewSet(viewsets.ModelViewSet):
    queryset = models.Transaction.objects.select_related('account', 'created_by')
    serializer_class = serializers.TransactionSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if hasattr(instance, 'purchase'):
            return Response(
                {
                    'error': (
                        'Cannot delete a transaction linked to a purchase. '
                        'Delete the purchase instead.'
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if hasattr(instance, 'sale'):
            return Response(
                {
                    'error': (
                        'Cannot delete a transaction linked to a sale. '
                        'Delete the sale instead.'
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = models.Category.objects.filter(is_active=True)
    serializer_class = serializers.CategorySerializer
    permission_classes = [IsAuthenticated]


class DishViewSet(viewsets.ModelViewSet):
    serializer_class = serializers.DishSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = models.Dish.objects.select_related('category').prefetch_related(
            'ingredients__product',
        )
        category_id = self.request.query_params.get('category_id')
        if category_id:
            queryset = queryset.filter(category_id=category_id)
        if self.action == 'list':
            queryset = queryset.filter(is_active=True)
        return queryset


class DishIngredientViewSet(viewsets.ModelViewSet):
    queryset = models.DishIngredient.objects.select_related('dish', 'product')
    serializer_class = serializers.DishIngredientSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        dish_id = self.request.query_params.get('dish_id')
        if dish_id:
            queryset = queryset.filter(dish_id=dish_id)
        return queryset


class ToppingViewSet(viewsets.ModelViewSet):
    serializer_class = serializers.ToppingSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = models.Topping.objects.select_related('product')
        if self.action == 'list':
            queryset = queryset.filter(is_active=True)
        return queryset


class SaleViewSet(viewsets.ModelViewSet):
    queryset = models.Sale.objects.select_related(
        'dish',
        'dish__category',
        'transaction',
        'transaction__account',
    ).prefetch_related(
        'inventory_movements',
        'sale_toppings__topping',
    )
    serializer_class = serializers.SaleSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'delete', 'head', 'options']

    def perform_destroy(self, instance):
        with db_transaction.atomic():
            inventory.delete_sale_movements(instance)
            sale_transaction = instance.transaction
            instance.delete()
            sale_transaction.delete()


class PurchaseViewSet(viewsets.ModelViewSet):
    queryset = models.Purchase.objects.select_related(
        'product',
        'transaction',
        'transaction__account',
        'inventory_movement',
    )
    serializer_class = serializers.PurchaseSerializer
    permission_classes = [IsAuthenticated]

    def perform_destroy(self, instance):
        with db_transaction.atomic():
            if hasattr(instance, 'inventory_movement'):
                inventory.delete_inventory_movement(instance.inventory_movement)
            purchase_transaction = instance.transaction
            instance.delete()
            purchase_transaction.delete()


class InventoryMovementViewSet(viewsets.ModelViewSet):
    queryset = models.InventoryMovement.objects.select_related('product', 'created_by')
    serializer_class = serializers.InventoryMovementSerializer
    # permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        queryset = super().get_queryset()
        product_id = self.request.query_params.get('product_id')
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        source = self.request.query_params.get('source')

        if product_id:
            queryset = queryset.filter(product_id=product_id)
        if start_date:
            queryset = queryset.filter(movement_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(movement_date__lte=end_date)
        if source:
            queryset = queryset.filter(source=source)

        return queryset

    def perform_create(self, serializer):
        serializer.save()


class InventoryReportView(APIView):
    # permission_classes = [IsAuthenticated]

    def get(self, request):
        start_date = parse_date(request.query_params.get('start_date', ''))
        end_date = parse_date(request.query_params.get('end_date', ''))
        product_id = request.query_params.get('product_id')

        if not start_date or not end_date:
            return Response(
                {'error': 'start_date and end_date query parameters are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if start_date > end_date:
            return Response(
                {'error': 'start_date must be on or before end_date.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if product_id:
            if not models.Product.objects.filter(pk=product_id).exists():
                return Response(
                    {'error': 'Product not found.'},
                    status=status.HTTP_404_NOT_FOUND,
                )

        report = inventory.get_inventory_report(start_date, end_date, product_id)
        for row in report:
            row['date'] = row['date'].isoformat()
            for key in ('opening_balance', 'in', 'out', 'closing_balance'):
                row[key] = f"{row[key]:.2f}"

        return Response({
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'product_id': int(product_id) if product_id else None,
            'results': report,
        })


class InventoryCurrentView(APIView):
    """Current stock snapshot from product quantities."""

    # permission_classes = [IsAuthenticated]

    def get(self, request):
        products = models.Product.objects.all().order_by('name')
        product_id = request.query_params.get('product_id')
        if product_id:
            products = products.filter(pk=product_id)

        results = [
            {
                'product_id': product.id,
                'product_name': product.name,
                'quantity': str(product.quantity),
                'updated_at': product.updated_at.isoformat(),
            }
            for product in products
        ]
        return Response({'results': results})


class FinanceReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        start_date = parse_date(request.query_params.get('start_date', ''))
        end_date = parse_date(request.query_params.get('end_date', ''))
        account_id = request.query_params.get('account_id')

        if not start_date or not end_date:
            return Response(
                {'error': 'start_date and end_date query parameters are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if start_date > end_date:
            return Response(
                {'error': 'start_date must be on or before end_date.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if account_id:
            if not models.Account.objects.filter(pk=account_id).exists():
                return Response(
                    {'error': 'Account not found.'},
                    status=status.HTTP_404_NOT_FOUND,
                )

        report = finances.get_finance_report(start_date, end_date, account_id)
        for row in report:
            row['date'] = row['date'].isoformat()
            for key in ('opening_balance', 'income', 'expenses', 'closing_balance'):
                row[key] = f"{row[key]:.2f}"

        return Response({
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'account_id': int(account_id) if account_id else None,
            'results': report,
        })
