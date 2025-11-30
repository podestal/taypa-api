from rest_framework import serializers
from .models import Document
from django.core.exceptions import ValidationError


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


class CreateTicketSerializer(serializers.Serializer):
    """Serializer for creating tickets"""
    order_items = OrderItemSerializer(many=True)
    order_id = serializers.IntegerField(required=False, allow_null=True)


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = '__all__'


class GeneratePDFSerializer(serializers.Serializer):
    """
    Serializer for generating PDFs (ticket, boleta, or factura)
    
    For 'ticket' type:
        - document_type: 'ticket'
        - order_items: required
        - order_number: optional
        - customer_name: optional
    
    For 'boleta' or 'factura' type:
        - document_type: 'boleta' or 'factura'
        - document_id: UUID of document in database (required)
        OR
        - sunat_id: Sunat document ID (required)
    """
    document_type = serializers.ChoiceField(
        choices=['ticket', 'boleta', 'factura'],
        help_text="Type of document: 'ticket' (simple, no Sunat), 'boleta' (ticket from Sunat), or 'factura' (invoice from Sunat)"
    )
    
    # For 'ticket' type
    order_items = OrderItemSerializer(many=True, required=False)
    order_number = serializers.CharField(required=False, allow_blank=True)
    customer_name = serializers.CharField(required=False, allow_blank=True)
    
    # For 'boleta' or 'factura' type
    document_id = serializers.UUIDField(required=False, help_text="Local database document ID")
    sunat_id = serializers.CharField(required=False, help_text="Sunat document ID")
    
    def validate(self, data):
        document_type = data.get('document_type')
        
        if document_type == 'ticket':
            # For ticket, order_items is required (but can be empty list)
            if 'order_items' not in data:
                raise serializers.ValidationError({
                    'order_items': 'order_items is required for document_type="ticket"'
                })
            # Empty list is allowed (order_items exists, just empty)
        else:
            # For boleta/factura, need either document_id or sunat_id
            document_id = data.get('document_id')
            sunat_id = data.get('sunat_id')
            
            if not document_id and not sunat_id:
                raise serializers.ValidationError({
                    'document_id': f'Either document_id or sunat_id is required for document_type="{document_type}"'
                })
        
        return data