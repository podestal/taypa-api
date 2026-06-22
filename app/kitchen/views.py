from django.db import transaction as db_transaction
from django.utils.dateparse import parse_date
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import inventory, models, serializers


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
        return super().destroy(request, *args, **kwargs)


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
