from rest_framework import viewsets
from .models import Document
from .serializers import DocumentSerializer


class DocumentViewSet(viewsets.ModelViewSet):
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer

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
