import requests
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from .models import Document
from .serializers import DocumentSerializer
from .services import process_sunat_document
from rest_framework.pagination import BasePagination
from .pagination import SimplePagination


class DocumentViewSet(viewsets.ModelViewSet):
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    pagination_class = SimplePagination

    @action(detail=False, methods=['get'], url_path='get-tickets')
    def get_ticket(self, request):
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
