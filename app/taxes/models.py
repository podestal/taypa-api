
"""
Django Models for SUNAT Documents
Two models approach:
1. SunatDocumentRequest - Stores what you SEND to SUNAT (for retries)
2. SunatDocument - Stores the final document with SUNAT response
"""

from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone
import uuid

# {
  
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


# class SunatDocumentRequest(models.Model):
#     """
#     Model to store the request data you send to SUNAT
#     This allows you to retry if SUNAT is down
#     """
    
#     DOCUMENT_TYPE_CHOICES = [
#         ('03', 'Boleta'),
#         ('01', 'Factura'),
#     ]
    
#     # Primary key
#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
#     # Link to order
#     order = models.ForeignKey(
#         'orders.Order',  # Adjust to your Order model path
#         on_delete=models.SET_NULL,
#         null=True,
#         blank=True,
#         related_name='sunat_requests'
#     )
    
#     # Document type
#     document_type = models.CharField(
#         max_length=2,
#         choices=DOCUMENT_TYPE_CHOICES,
#         help_text='Tipo: 03=Boleta, 01=Factura'
#     )
    
#     # Document identification
#     serie = models.CharField(max_length=10, help_text='Serie: B001, F001, etc.')
#     numero = models.CharField(max_length=20, help_text='Número: 00000001, etc.')
    
    
#     # Customer - REQUIRED
#     customer_document_type = models.CharField(
#         max_length=10,
#         help_text='Tipo de documento: 1=DNI, 6=RUC, 4=Pasaporte'
#     )
#     customer_document_number = models.CharField(max_length=20)
#     customer_name = models.CharField(max_length=255)
#     customer_address = models.TextField(null=True, blank=True, help_text='Requerido para facturas')
    
#     # Items - stored as JSON
#     items = models.JSONField(
#         help_text='Array of items: [{"id": "1", "description": "...", "quantity": 1, "unitCode": "NIU", "unitPrice": 20.00, "taxCode": "10"}]'
#     )
    
#     # Financial info (from your order)
#     amount = models.DecimalField(
#         max_digits=10,
#         decimal_places=2,
#         validators=[MinValueValidator(0)],
#         help_text='Monto total del pedido'
#     )
#     subtotal = models.DecimalField(
#         max_digits=10,
#         decimal_places=2,
#         null=True,
#         blank=True
#     )
#     igv = models.DecimalField(
#         max_digits=10,
#         decimal_places=2,
#         null=True,
#         blank=True
#     )
    
#     # Issue date/time
#     issue_date = models.DateField()
#     issue_time = models.TimeField(null=True, blank=True)
    
#     # Status tracking
#     sent_to_sunat = models.BooleanField(default=False, help_text='Si ya se envió a SUNAT')
#     sent_at = models.DateTimeField(null=True, blank=True)
    
#     # Link to created document (if successful)
#     document = models.OneToOneField(
#         'SunatDocument',
#         on_delete=models.SET_NULL,
#         null=True,
#         blank=True,
#         related_name='request',
#         help_text='Documento creado exitosamente'
#     )
    
#     # Timestamps
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)
    
#     class Meta:
#         db_table = 'sunat_document_requests'
#         verbose_name = 'Solicitud de Documento SUNAT'
#         verbose_name_plural = 'Solicitudes de Documentos SUNAT'
#         ordering = ['-created_at']
#         indexes = [
#             models.Index(fields=['sent_to_sunat']),
#             models.Index(fields=['document_type']),
#             models.Index(fields=['serie', 'numero']),
#         ]
    
#     def __str__(self):
#         return f"Request {self.get_document_type_display()} {self.serie}-{self.numero}"
    
#     def mark_as_sent(self):
#         """Mark request as sent to SUNAT"""
#         self.sent_to_sunat = True
#         self.sent_at = timezone.now()
#         self.save(update_fields=['sent_to_sunat', 'sent_at', 'updated_at'])
    
#     def to_sunat_payload(self):
#         """
#         Convert request to payload format for SUNAT API
#         Returns the JSON structure you send to SUNAT
#         """
#         return {
#             "documentType": "03" if self.document_type == "boleta" else "01",
#             "serie": self.serie,
#             "numero": self.numero,
#             "issueDate": self.issue_date.isoformat(),
#             "issueTime": self.issue_time.strftime("%H:%M:%S") if self.issue_time else None,
#             "supplier": {
#                 "ruc": self.supplier_ruc,
#                 "name": self.supplier_name,
#                 "address": self.supplier_address
#             },
#             "customer": {
#                 "documentType": self.customer_document_type,
#                 "documentNumber": self.customer_document_number,
#                 "name": self.customer_name,
#                 "address": self.customer_address
#             },
#             "items": self.items
#         }


class Document(models.Model):
    """
    Model to store the final SUNAT document with response data
    Created after SUNAT accepts/rejects the request
    """
    
    STATUS_CHOICES = [
        ('pending', 'Pendiente'),
        ('processing', 'Procesando'),
        ('accepted', 'Aceptado'),
        ('rejected', 'Rechazado'),
        ('exception', 'Excepción'),
        ('failed', 'Fallido'),
    ]
    
    # Primary key
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document_type = models.CharField(
        max_length=20,
    )
    serie = models.CharField(max_length=20)
    numero = models.CharField(max_length=20)
    
    # ====== DATA FROM SUNAT RESPONSE ======
    
    # SUNAT response ID
    sunat_id = models.CharField(
        max_length=100,
        unique=True,
        null=True,
        blank=True,
        help_text='ID que SUNAT devuelve (ej: 675c532840264100151a3644)'
    )
    
    # SUNAT status
    sunat_status = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text='Estado de SUNAT: ACEPTADO, RECHAZADO, EXCEPCION'
    )
    
    # Your internal status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='processing'
    )
    
    # SUNAT URLs
    xml_url = models.URLField(
        max_length=500,
        null=True,
        blank=True,
        help_text='URL del XML en CDN de SUNAT'
    )
    cdr_url = models.URLField(
        max_length=500,
        null=True,
        blank=True,
        help_text='URL del CDR en CDN de SUNAT'
    )
    
    # SUNAT timestamps
    sunat_issue_time = models.BigIntegerField(
        null=True,
        blank=True,
        help_text='Timestamp Unix de emisión (de SUNAT)'
    )
    sunat_response_time = models.BigIntegerField(
        null=True,
        blank=True,
        help_text='Timestamp Unix de respuesta (de SUNAT)'
    )
    
    # Environment flags
    production = models.BooleanField(default=False)
    is_purchase = models.BooleanField(default=False)
    
    # Errors
    faults = models.JSONField(
        null=True,
        blank=True,
        help_text='Errores de SUNAT si los hay'
    )
    error_message = models.TextField(
        null=True,
        blank=True,
        help_text='Error interno si falló'
    )
    
    # Amount (from request or parsed from XML later)
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Monto total (del request o parseado del XML)'
    )
    
    # PDF file (Cloudflare R2)
    pdf_file = models.FileField(
        upload_to='sunat_documents/pdf/%Y/%m/%d/',
        null=True,
        blank=True,
        storage=None,  # Set to your R2 storage
        help_text='PDF generado y almacenado en R2'
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    @classmethod
    def _extract_serie_numero_from_filename(cls, filename: str):
        """
        Extract serie and numero from filename
        Expected format: "B001-00000001.xml" or "F001-00000001.xml"
        """
        if not filename:
            return None, None
        
        # Remove extension
        name_without_ext = filename.replace('.xml', '').replace('.zip', '')
        
        # Try to split by dash
        if '-' in name_without_ext:
            parts = name_without_ext.split('-', 1)
            if len(parts) == 2:
                return parts[0], parts[1]
        
        return None, None
    
    @classmethod
    def sync_from_sunat(cls, sunat_data: dict, processed_data: dict = None):
        """
        Create or update a Document from Sunat API response
        
        Args:
            sunat_data: Document data from Sunat API
            processed_data: Optional processed data (e.g., amount from XML)
            
        Returns:
            Document instance
        """
        sunat_id = sunat_data.get('id')
        if not sunat_id:
            raise ValueError("Sunat document must have an 'id' field")
        
        # Extract serie and numero from multiple sources
        serie = sunat_data.get('serie', '')
        numero = sunat_data.get('numero', '')
        
        # Try from processed_data (extracted from XML)
        if processed_data:
            if processed_data.get('serie'):
                serie = processed_data.get('serie')
            if processed_data.get('numero'):
                numero = processed_data.get('numero')
        
        # Fallback to fileName if still not found
        if not serie or not numero:
            filename = sunat_data.get('fileName', '')
            extracted_serie, extracted_numero = cls._extract_serie_numero_from_filename(filename)
            if extracted_serie:
                serie = extracted_serie
            if extracted_numero:
                numero = extracted_numero
        
        # Try to get existing document by sunat_id
        document, created = cls.objects.get_or_create(
            sunat_id=sunat_id,
            defaults={
                'document_type': sunat_data.get('type', ''),
                'serie': serie,
                'numero': numero,
                'sunat_status': sunat_data.get('status', ''),
                'xml_url': sunat_data.get('xml'),
                'cdr_url': sunat_data.get('cdr'),
                'sunat_issue_time': sunat_data.get('issueTime'),
                'sunat_response_time': sunat_data.get('responseTime'),
                'production': sunat_data.get('production', False),
                'is_purchase': sunat_data.get('isPurchase', False),
                'faults': sunat_data.get('faults'),
            }
        )
        
        # Update fields if document already exists
        if not created:
            # Only update if we have new values
            if sunat_data.get('type'):
                document.document_type = sunat_data.get('type')
            if serie:
                document.serie = serie
            if numero:
                document.numero = numero
            if sunat_data.get('status'):
                document.sunat_status = sunat_data.get('status')
            if sunat_data.get('xml'):
                document.xml_url = sunat_data.get('xml')
            if sunat_data.get('cdr'):
                document.cdr_url = sunat_data.get('cdr')
            if sunat_data.get('issueTime'):
                document.sunat_issue_time = sunat_data.get('issueTime')
            if sunat_data.get('responseTime'):
                document.sunat_response_time = sunat_data.get('responseTime')
            if 'production' in sunat_data:
                document.production = sunat_data.get('production')
            if 'isPurchase' in sunat_data:
                document.is_purchase = sunat_data.get('isPurchase')
            if 'faults' in sunat_data:
                document.faults = sunat_data.get('faults')
        
        # Update status based on sunat_status
        sunat_status = sunat_data.get('status', '').upper()
        if sunat_status == 'ACEPTADO':
            document.status = 'accepted'
        elif sunat_status == 'RECHAZADO':
            document.status = 'rejected'
        elif sunat_status == 'EXCEPCION':
            document.status = 'exception'
        else:
            document.status = 'processing'
        
        # Update amount from processed data if available
        if processed_data and processed_data.get('amount'):
            from decimal import Decimal
            document.amount = Decimal(str(processed_data['amount']))
        
        document.save()
        return document
    
    def __str__(self):
        return f"{self.document_type} {self.serie}-{self.numero} ({self.sunat_id})"


