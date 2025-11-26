import requests
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from .models import Document
from .serializers import DocumentSerializer


class DocumentViewSet(viewsets.ModelViewSet):
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer

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
