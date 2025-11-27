import requests
from decimal import Decimal
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from .models import Document
from .serializers import (
    DocumentSerializer,
    CreateInvoiceSerializer,
    CreateTicketSerializer
)
from .services import process_sunat_document
from .sunat_utils import (
    get_correlative,
    generate_invoice_data,
    generate_ticket_data
)
from rest_framework.pagination import BasePagination
from .pagination import SimplePagination


class DocumentViewSet(viewsets.ModelViewSet):
    queryset = Document.objects.order_by('-created_at')
    serializer_class = DocumentSerializer
    pagination_class = SimplePagination

    @action(detail=False, methods=['get'], url_path='get-tickets')
    def get_tickets(self, request):
        """
        Fetch a ticket from Sunat API
        """
        documents = Document.objects.filter(document_type='03')
        
        documents_page = self.paginate_queryset(documents)
        serializer = DocumentSerializer(documents_page, many=True)
        return self.get_paginated_response(serializer.data)


    @action(detail=False, methods=['get'], url_path='get-invoices')
    def get_invoices(self, request):
        """
        Fetch invoices from Sunat API
        """
        documents = Document.objects.filter(document_type='01')
        documents_page = self.paginate_queryset(documents)
        serializer = DocumentSerializer(documents_page, many=True)
        return self.get_paginated_response(serializer.data)

    @action(detail=False, methods=['get'], url_path='get-all')
    def get_documents(self, request):
        """
        Fetch all documents from Sunat API
        """
        sunat_url = settings.SUNAT_API_URL
        persona_id = settings.SUNAT_PERSONA_ID
        persona_token = settings.SUNAT_PERSONA_TOKEN

        if not persona_id or not persona_token:
            return Response(
                {'error': 'Sunat API credentials not configured'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        try:
            # Construct the full URL with endpoint
            endpoint = f"{sunat_url.rstrip('/')}/getAll"
            
            # Make request to Sunat API
            response = requests.get(
                endpoint,
                params={
                    'personaId': persona_id,
                    'personaToken': persona_token,
                    'limit': 100
                },
                timeout=30
            )
            
            # Raise an exception for bad status codes
            response.raise_for_status()
            serializer = DocumentSerializer(response.json())

            # Return the response data as-is
            return Response(response.json(), status=status.HTTP_200_OK)
            
        except requests.exceptions.RequestException as e:
            return Response(
                {'error': f'Failed to fetch documents from Sunat API: {str(e)}'},
                status=status.HTTP_502_BAD_GATEWAY
            )
        except Exception as e:
            return Response(
                {'error': f'Unexpected error: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'], url_path='sync')
    def sync_documents(self, request):
        """
        Sync documents from Sunat API to database
        Downloads XML files and extracts amount information
        """
        sunat_url = settings.SUNAT_API_URL
        persona_id = settings.SUNAT_PERSONA_ID
        persona_token = settings.SUNAT_PERSONA_TOKEN

        if not persona_id or not persona_token:
            return Response(
                {'error': 'Sunat API credentials not configured'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        try:
            # Fetch documents from Sunat API
            endpoint = f"{sunat_url.rstrip('/')}/getAll"
            response = requests.get(
                endpoint,
                params={
                    'personaId': persona_id,
                    'personaToken': persona_token,
                    'limit': 100
                },
                timeout=30
            )
            response.raise_for_status()
            sunat_documents = response.json()
            
            # Ensure it's a list
            if not isinstance(sunat_documents, list):
                return Response(
                    {'error': 'Invalid response format from Sunat API'},
                    status=status.HTTP_502_BAD_GATEWAY
                )
            
            synced_count = 0
            updated_count = 0
            errors = []
            
            # Process each document
            for sunat_doc in sunat_documents:
                try:
                    # Process XML to extract amount (this may fail, but we still want to save the document)
                    processed_data = process_sunat_document(sunat_doc)
                    
                    # Sync to database even if XML processing failed
                    # This way we at least have the basic document info
                    document = Document.sync_from_sunat(sunat_doc, processed_data)
                    
                    if document:
                        synced_count += 1
                        # Only report error if XML processing failed
                        if processed_data.get('error'):
                            errors.append({
                                'sunat_id': sunat_doc.get('id'),
                                'xml_url': sunat_doc.get('xml'),
                                'error': processed_data['error']
                            })
                
                except Exception as e:
                    errors.append({
                        'sunat_id': sunat_doc.get('id', 'unknown'),
                        'xml_url': sunat_doc.get('xml'),
                        'error': str(e)
                    })
            
            return Response({
                'synced': synced_count,
                'total': len(sunat_documents),
                'errors': errors
            }, status=status.HTTP_200_OK)
            
        except requests.exceptions.RequestException as e:
            return Response(
                {'error': f'Failed to fetch documents from Sunat API: {str(e)}'},
                status=status.HTTP_502_BAD_GATEWAY
            )
        except Exception as e:
            return Response(
                {'error': f'Unexpected error: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'], url_path='create-invoice')
    def create_invoice(self, request):
        """
        Create an invoice (factura) in Sunat
        
        Request body:
        {
            "order_items": [
                {"id": "1", "name": "Producto 1", "quantity": 2, "cost": 50.00}
            ],
            "ruc": "20123456789",
            "address": "Av. Principal 123"
        }
        """
        serializer = CreateInvoiceSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        persona_id = settings.SUNAT_PERSONA_ID
        persona_token = settings.SUNAT_PERSONA_TOKEN
        
        if not persona_id or not persona_token:
            return Response(
                {'error': 'Sunat API credentials not configured'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        try:
            # Get next correlative number
            correlative = get_correlative('I')
            if not correlative:
                return Response(
                    {'error': 'Failed to get correlative number from Sunat'},
                    status=status.HTTP_502_BAD_GATEWAY
                )
            
            # Generate invoice data
            order_items = serializer.validated_data['order_items']
            invoice_data = generate_invoice_data(
                correlative=correlative,
                order_items=[dict(item) for item in order_items],
                ruc=serializer.validated_data['ruc'],
                address=serializer.validated_data['address']
            )
            
            # Send to Sunat API
            # According to docs: POST /personas/v1/sendBill
            send_bill_url = "https://back.apisunat.com/personas/v1/sendBill"
            response = requests.post(
                send_bill_url,
                json=invoice_data,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
            # Check response
            if response.status_code not in [200, 201]:
                return Response(
                    {
                        'error': f'Failed to create invoice in Sunat',
                        'status_code': response.status_code,
                        'response': response.text[:500],
                        'endpoint_used': send_bill_url,
                    },
                    status=status.HTTP_502_BAD_GATEWAY
                )
            
            sunat_response = response.json()
            
            # Check if Sunat returned an error
            if sunat_response.get('status') == 'ERROR':
                return Response(
                    {
                        'error': 'Sunat API returned an error',
                        'sunat_error': sunat_response.get('error', {}),
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create document in database
            fileName = invoice_data.get('fileName', '')
            
            # Parse fileName: 20482674828-01-F001-00000001
            parts = fileName.split('-')
            serie = parts[2] if len(parts) >= 4 else ''
            numero = parts[3] if len(parts) >= 4 else ''
            
            # Calculate total from order items (exactly what user sent)
            total_amount = sum(float(item.get('cost', 0)) * float(item.get('quantity', 0)) for item in order_items)
            
            # Create document
            document = Document.objects.create(
                sunat_id=sunat_response.get('documentId'),
                document_type='01',
                serie=serie,
                numero=numero,
                sunat_status='PENDIENTE',
                status='pending',
                amount=Decimal(str(total_amount)),
            )
            
            # Return created document
            doc_serializer = DocumentSerializer(document)
            return Response(doc_serializer.data, status=status.HTTP_201_CREATED)
            
        except requests.exceptions.RequestException as e:
            return Response(
                {'error': f'Failed to create invoice in Sunat: {str(e)}'},
                status=status.HTTP_502_BAD_GATEWAY
            )
        except Exception as e:
            return Response(
                {'error': f'Unexpected error: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'], url_path='create-ticket')
    def create_ticket(self, request):
        """
        Create a ticket (boleta) in Sunat
        
        Request body:
        {
            "order_items": [
                {"id": "1", "name": "Producto 1", "quantity": 2, "cost": 50.00}
            ]
        }
        """
        serializer = CreateTicketSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        persona_id = settings.SUNAT_PERSONA_ID
        persona_token = settings.SUNAT_PERSONA_TOKEN
        
        if not persona_id or not persona_token:
            return Response(
                {'error': 'Sunat API credentials not configured'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        try:
            # Get next correlative number
            correlative = get_correlative('T')
            if not correlative:
                return Response(
                    {'error': 'Failed to get correlative number from Sunat'},
                    status=status.HTTP_502_BAD_GATEWAY
                )
            
            # Generate ticket data
            order_items = serializer.validated_data['order_items']
            ticket_data = generate_ticket_data(
                correlative=correlative,
                order_items=[dict(item) for item in order_items]
            )
            
            # Send to Sunat API
            # According to docs: POST /personas/v1/sendBill
            send_bill_url = "https://back.apisunat.com/personas/v1/sendBill"
            response = requests.post(
                send_bill_url,
                json=ticket_data,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
            # Check response
            if response.status_code not in [200, 201]:
                return Response(
                    {
                        'error': f'Failed to create ticket in Sunat',
                        'status_code': response.status_code,
                        'response': response.text[:500],
                        'endpoint_used': send_bill_url,
                    },
                    status=status.HTTP_502_BAD_GATEWAY
                )
            
            sunat_response = response.json()
            
            # Check if Sunat returned an error
            if sunat_response.get('status') == 'ERROR':
                return Response(
                    {
                        'error': 'Sunat API returned an error',
                        'sunat_error': sunat_response.get('error', {}),
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create document in database
            fileName = ticket_data.get('fileName', '')
            
            # Parse fileName: 20482674828-03-B001-00000001
            parts = fileName.split('-')
            serie = parts[2] if len(parts) >= 4 else ''
            numero = parts[3] if len(parts) >= 4 else ''
            
            # Calculate total from order items (exactly what user sent)
            total_amount = sum(float(item.get('cost', 0)) * float(item.get('quantity', 0)) for item in order_items)
            
            # Create document
            document = Document.objects.create(
                sunat_id=sunat_response.get('documentId'),
                document_type='03',
                serie=serie,
                numero=numero,
                sunat_status='PENDIENTE',
                status='pending',
                amount=Decimal(str(total_amount)),
            )
            
            # Return created document
            doc_serializer = DocumentSerializer(document)
            return Response(doc_serializer.data, status=status.HTTP_201_CREATED)
            
        except requests.exceptions.RequestException as e:
            return Response(
                {'error': f'Failed to create ticket in Sunat: {str(e)}'},
                status=status.HTTP_502_BAD_GATEWAY
            )
        except Exception as e:
            return Response(
                {'error': f'Unexpected error: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

# {
#   "personaId": "675c4d5b40264100151a3492",
#   "personaToken": "DEV_ARMXKt1dLYTkhbI6bhp1ErGVimApMLB8CayiMsvjDulEWYFK7lUpLIKN4kAdWHsX",
  
#   "documentType": "03",  // "03" = Boleta, "01" = Factura
  
#   "supplier": {
#     "ruc": "20482674828",
#     "name": "Axios",
#     "address": "217 primera"
#   },
  
#   "customer": {
#     "documentType": "1",        // "1" = DNI
#     "documentNumber": "12345678",
#     "name": "Juan Pérez"
#   },
  
#   "items": [
#     {
#       "id": "1",
#       "description": "Producto o servicio",
#       "quantity": 1,
#       "unitCode": "NIU",
#       "unitPrice": 20.00,
#       "taxCode": "10"           // 10 = Gravado con IGV
#     }
#   ],
  
#   "serie": "B001",
#   "numero": "00000001",
#   "issueDate": "2024-12-13",
#   "issueTime": "10:30:48"
# }
