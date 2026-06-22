from django.db import transaction as db_transaction
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from . import models, serializers


class ProductViewSet(viewsets.ModelViewSet):
    queryset = models.Product.objects.all()
    serializer_class = serializers.ProductSerializer
    permission_classes = [IsAuthenticated]


class AccountViewSet(viewsets.ModelViewSet):
    queryset = models.Account.objects.all()
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
    )
    serializer_class = serializers.PurchaseSerializer
    permission_classes = [IsAuthenticated]

    def perform_destroy(self, instance):
        with db_transaction.atomic():
            product = instance.product
            quantity_bought = instance.quantity_bought
            purchase_transaction = instance.transaction
            instance.delete()
            purchase_transaction.delete()
            product.quantity -= quantity_bought
            product.save(update_fields=['quantity', 'updated_at'])
