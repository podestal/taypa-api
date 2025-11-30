from rest_framework import serializers
from .models import Document


class OrderItemSerializer(serializers.Serializer):
    """Serializer for order items"""
    id = serializers.CharField()
    name = serializers.CharField()
    quantity = serializers.FloatField()
    cost = serializers.FloatField()


class CreateInvoiceSerializer(serializers.Serializer):
    """Serializer for creating invoices"""
    order_items = OrderItemSerializer(many=True)
    ruc = serializers.CharField()
    razon_social = serializers.CharField()
    address = serializers.CharField()
    order_id = serializers.IntegerField(required=False, allow_null=True)
    return_pdf = serializers.BooleanField(required=False, default=False)


class CreateTicketSerializer(serializers.Serializer):
    """Serializer for creating tickets"""
    order_items = OrderItemSerializer(many=True)
    order_id = serializers.IntegerField(required=False, allow_null=True)
    return_pdf = serializers.BooleanField(required=False, default=False)


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = '__all__'