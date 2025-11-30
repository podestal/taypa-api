import requests
from decimal import Decimal
from datetime import datetime
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from django.db.models import F, Case, When, IntegerField
from django.core.exceptions import ObjectDoesNotExist
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
from .sync_utils import (
    process_and_sync_documents,
    filter_today_documents
)
from rest_framework.pagination import BasePagination
from .pagination import SimplePagination
from rest_framework.permissions import IsAuthenticated


class DocumentViewSet(viewsets.ModelViewSet):
    # Order by: NULL sunat_issue_time first (newest), then by sunat_issue_time DESC, then created_at DESC
    queryset = Document.objects.annotate(
        sort_priority=Case(
            When(sunat_issue_time__isnull=True, then=0),  # NULL = highest priority (newest)
            default=1,  # Has value = lower priority
            output_field=IntegerField()
        )
    ).order_by('sort_priority', '-sunat_issue_time', '-created_at')
    serializer_class = DocumentSerializer
    pagination_class = SimplePagination
    # permission_classes = [IsAuthenticated]

    def _fetch_pdf_binary(self, sunat_id, max_retries=5, delay=3):
        """
        Helper method to fetch PDF binary data from Sunat
        Waits for document to be ready in Sunat before fetching PDF
        Returns tuple: (pdf_bytes, fileName) or (None, None) if failed
        """
        import time
        persona_id = settings.SUNAT_PERSONA_ID
        persona_token = settings.SUNAT_PERSONA_TOKEN
        sunat_url = settings.SUNAT_API_URL
        pdf_format = 'ticket80mm'
        
        if not persona_id or not persona_token:
            return None, None
        
        # First, wait for document to be ready in Sunat
        print(f"Waiting for document {sunat_id} to be ready in Sunat...")
        for attempt in range(max_retries):
            try:
                # Check if document exists and is ready in Sunat
                get_by_id_endpoint = f"{sunat_url.rstrip('/')}/{sunat_id}/getById"
                sunat_response = requests.get(
                    get_by_id_endpoint,
                    params={'personaId': persona_id, 'personaToken': persona_token},
                    timeout=30
                )
                
                # If document is found (200), it means it's available
                if sunat_response.status_code == 200:
                    sunat_doc = sunat_response.json()
                    if isinstance(sunat_doc, dict):
                        # Document exists, try to get fileName
                        fileName = None
                        if sunat_doc.get('fileName'):
                            fileName = f"{sunat_doc['fileName']}.pdf"
                        
                        # Fallback: construct from database
                        if not fileName:
                            try:
                                db_document = Document.objects.get(sunat_id=sunat_id)
                                fileName = f"20482674828-{db_document.document_type}-{db_document.serie}-{db_document.numero}.pdf"
                            except Document.DoesNotExist:
                                fileName = "document.pdf"
                        
                        # Now try to fetch PDF (may need a bit more time for PDF generation)
                        print(f"Document found. Attempting to fetch PDF (attempt {attempt + 1}/{max_retries})...")
                        base_url = sunat_url.rstrip('/')
                        endpoint = f"{base_url}/{sunat_id}/getPDF/{pdf_format}/{fileName}"
                        
                        pdf_response = requests.get(
                            endpoint,
                            params={'personaId': persona_id, 'personaToken': persona_token},
                            timeout=30,
                            stream=True,
                            allow_redirects=True
                        )
                        
                        # Check if PDF is ready
                        if pdf_response.status_code == 200:
                            content_type = pdf_response.headers.get('Content-Type', '').lower()
                            if 'pdf' in content_type:
                                print(f"PDF successfully fetched!")
                                return pdf_response.content, fileName
                            # If response is HTML (404 page), PDF not ready yet
                            elif 'html' in content_type:
                                print(f"PDF not ready yet (got HTML response), waiting...")
                            else:
                                print(f"Unexpected content type: {content_type}")
                
                # If document not found or PDF not ready, wait and retry
                if attempt < max_retries - 1:
                    print(f"Waiting {delay} seconds before retry...")
                    time.sleep(delay)
                    
            except requests.exceptions.RequestException as e:
                print(f"Request error: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(delay)
                continue
            except Exception as e:
                print(f"Unexpected error: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(delay)
                continue
        
        print(f"Failed to fetch PDF after {max_retries} attempts")
        return None, None

    @action(detail=False, methods=['get'], url_path='get-tickets')
    def get_tickets(self, request):
        """
        Fetch tickets from database
        """
        documents = Document.objects.filter(document_type='03').annotate(
            sort_priority=Case(
                When(sunat_issue_time__isnull=True, then=0),  # NULL = highest priority (newest)
                default=1,  # Has value = lower priority
                output_field=IntegerField()
            )
        ).order_by('sort_priority', '-sunat_issue_time', '-created_at')
        
        documents_page = self.paginate_queryset(documents)
        serializer = DocumentSerializer(documents_page, many=True)
        return self.get_paginated_response(serializer.data)


    @action(detail=False, methods=['get'], url_path='get-invoices')
    def get_invoices(self, request):
        """
        Fetch invoices from database
        """
        documents = Document.objects.filter(document_type='01').annotate(
            sort_priority=Case(
                When(sunat_issue_time__isnull=True, then=0),  # NULL = highest priority (newest)
                default=1,  # Has value = lower priority
                output_field=IntegerField()
            )
        ).order_by('sort_priority', '-sunat_issue_time', '-created_at')
        
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
    
    @action(detail=False, methods=['get'], url_path='sync', url_name='sync')
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
            
            # Process and sync documents
            synced_count, errors = process_and_sync_documents(sunat_documents, process_sunat_document)
            
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

    @action(detail=False, methods=['get'], url_path='sync-today', url_name='sync-today')
    def sync_today_documents(self, request):
        """
        Sync only today's documents from Sunat API to database
        Downloads XML files and extracts amount information for documents issued today
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
            
            # Filter to only today's documents
            today_documents = filter_today_documents(sunat_documents)
            
            # Check for documents created today in our DB that are missing from Sunat's response
            from django.utils import timezone
            now = timezone.now()
            db_today_documents = Document.objects.filter(created_at__date=now.date())
            
            # Get Sunat IDs from API response
            sunat_response_ids = {doc.get('id') for doc in sunat_documents if doc.get('id')}
            
            # Find documents in DB that aren't in Sunat's response
            missing_documents = []
            for db_doc in db_today_documents:
                if db_doc.sunat_id and db_doc.sunat_id not in sunat_response_ids:
                    missing_documents.append(db_doc)
            
            # Print documents that will be synced
            print(f"\n=== Syncing {len(today_documents)} documents today ===")
            for doc in today_documents:
                fileName = doc.get('fileName', '')
                # Extract serie and numero from fileName: 20482674828-01-F001-00000001
                if fileName:
                    parts = fileName.split('-')
                    if len(parts) >= 4:
                        serie = parts[2]
                        numero = parts[3]
                        doc_type = parts[1]  # '01' for invoice, '03' for ticket
                        print(f"  - Document: {serie}-{numero} (Type: {doc_type}, Sunat ID: {doc.get('id', 'N/A')})")
                    else:
                        print(f"  - Document: {fileName} (Sunat ID: {doc.get('id', 'N/A')})")
                else:
                    print(f"  - Document: No fileName (Sunat ID: {doc.get('id', 'N/A')})")
            
            # Try to fetch missing documents individually using getById
            missing_synced_count = 0
            missing_errors = []
            
            if missing_documents:
                print(f"\n⚠️  INFO: {len(missing_documents)} document(s) created today are not in Sunat API /getAll response.")
                print(f"  Attempting to fetch them individually using getById endpoint...")
                
                for db_doc in missing_documents:
                    if not db_doc.sunat_id:
                        print(f"  - SKIP: {db_doc.serie}-{db_doc.numero} (no sunat_id)")
                        continue
                    
                    try:
                        # Fetch individual document using getById
                        endpoint = f"{sunat_url.rstrip('/')}/{db_doc.sunat_id}/getById"
                        response = requests.get(
                            endpoint,
                            params={
                                'personaId': persona_id,
                                'personaToken': persona_token,
                            },
                            timeout=30
                        )
                        
                        if response.status_code == 200:
                            target_document = response.json()
                            if isinstance(target_document, dict) and target_document.get('id'):
                                # Process and sync this document
                                processed_data = process_sunat_document(target_document)
                                document = Document.sync_from_sunat(target_document, processed_data)
                                if document:
                                    missing_synced_count += 1
                                    print(f"  ✓ Synced missing: {db_doc.serie}-{db_doc.numero} (Sunat ID: {db_doc.sunat_id})")
                                    if processed_data.get('error'):
                                        missing_errors.append({
                                            'sunat_id': db_doc.sunat_id,
                                            'xml_url': target_document.get('xml'),
                                            'error': processed_data['error']
                                        })
                                else:
                                    missing_errors.append({
                                        'sunat_id': db_doc.sunat_id,
                                        'error': 'Failed to sync document'
                                    })
                            else:
                                missing_errors.append({
                                    'sunat_id': db_doc.sunat_id,
                                    'error': 'Invalid response format from getById'
                                })
                        elif response.status_code == 404:
                            print(f"  - NOT FOUND: {db_doc.serie}-{db_doc.numero} (Sunat ID: {db_doc.sunat_id}) - Document not indexed in Sunat yet")
                        else:
                            missing_errors.append({
                                'sunat_id': db_doc.sunat_id,
                                'error': f'HTTP {response.status_code}: {response.text[:200]}'
                            })
                    except Exception as e:
                        missing_errors.append({
                            'sunat_id': db_doc.sunat_id,
                            'error': str(e)
                        })
                        print(f"  - ERROR: {db_doc.serie}-{db_doc.numero} - {str(e)}")
                
                if missing_synced_count > 0:
                    print(f"  ✓ Successfully synced {missing_synced_count} missing document(s)")
            
            print("=" * 50 + "\n")
            
            # Process and sync documents from getAll
            synced_count, errors = process_and_sync_documents(today_documents, process_sunat_document)
            
            # Combine counts and errors
            total_synced = synced_count + missing_synced_count
            all_errors = errors + missing_errors
            
            return Response({
                'synced': total_synced,
                'synced_from_getall': synced_count,
                'synced_from_getbyid': missing_synced_count,
                'total_today': len(today_documents) + len(missing_documents) if missing_documents else len(today_documents),
                'total_fetched': len(sunat_documents),
                'missing_count': len(missing_documents) if missing_documents else 0,
                'errors': all_errors
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

    @action(detail=False, methods=['get'], url_path='sync-single', url_name='sync-single')
    def sync_single(self, request):
        """
        Sync a single document from Sunat API by sunat_id or document ID
        
        Query parameters:
            sunat_id: The Sunat document ID to sync (optional if document_id is provided)
            document_id: The local database document ID (UUID) to sync (optional if sunat_id is provided)
        """
        sunat_id = request.query_params.get('sunat_id')
        document_id = request.query_params.get('document_id')
        
        # If document_id is provided, look up the sunat_id from our database
        if document_id and not sunat_id:
            try:
                db_document = Document.objects.get(id=document_id)
                sunat_id = db_document.sunat_id
                if not sunat_id:
                    return Response(
                        {
                            'error': f'Document {document_id} does not have a sunat_id',
                            'document': {
                                'id': str(db_document.id),
                                'serie': db_document.serie,
                                'numero': db_document.numero,
                            }
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )
                print(f"Found document in database by ID: {db_document.serie}-{db_document.numero} (Sunat ID: {sunat_id})")
            except Document.DoesNotExist:
                return Response(
                    {'error': f'Document with id "{document_id}" not found in database'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        if not sunat_id:
            return Response(
                {'error': 'Either sunat_id or document_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        persona_id = settings.SUNAT_PERSONA_ID
        persona_token = settings.SUNAT_PERSONA_TOKEN
        
        if not persona_id or not persona_token:
            return Response(
                {'error': 'Sunat API credentials not configured'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        try:
            # Check if document exists in our database
            try:
                db_document = Document.objects.get(sunat_id=sunat_id)
                print(f"Found document in database: {db_document.serie}-{db_document.numero}")
            except Document.DoesNotExist:
                db_document = None
            
            # Fetch single document from Sunat API using getById endpoint
            sunat_url = settings.SUNAT_API_URL
            # Base URL is already https://apisunat.com/api/documents/, so we just add {id}/getById
            endpoint = f"{sunat_url.rstrip('/')}/{sunat_id}/getById"
            print(f"Fetching document from Sunat API: {endpoint}")
            print(f"Params: personaId={persona_id}, personaToken={'*' * len(persona_token) if persona_token else None}")
            
            response = requests.get(
                endpoint,
                params={
                    'personaId': persona_id,
                    'personaToken': persona_token,
                },
                timeout=30
            )
            
            print(f"Sunat API response status: {response.status_code}")
            
            # Handle 404 or other errors
            if response.status_code == 404:
                if db_document:
                    return Response(
                        {
                            'error': f'Document {db_document.serie}-{db_document.numero} not found in Sunat API',
                            'document': {
                                'serie': db_document.serie,
                                'numero': db_document.numero,
                                'sunat_id': db_document.sunat_id,
                                'status': db_document.sunat_status,
                                'amount': str(db_document.amount) if db_document.amount else None,
                            },
                            'message': 'Document exists in database but was not found in Sunat API. It may not be indexed yet.'
                        },
                        status=status.HTTP_404_NOT_FOUND
                    )
                else:
                    return Response(
                        {
                            'error': f'Document with sunat_id "{sunat_id}" not found in Sunat API',
                            'message': 'Document does not exist in Sunat API or database.'
                        },
                        status=status.HTTP_404_NOT_FOUND
                    )
            
            response.raise_for_status()
            target_document = response.json()
            
            # Check if we got a valid document object
            if not isinstance(target_document, dict) or not target_document.get('id'):
                return Response(
                    {'error': 'Invalid response format from Sunat API'},
                    status=status.HTTP_502_BAD_GATEWAY
                )
            
            # Print document info
            fileName = target_document.get('fileName', '')
            if fileName:
                parts = fileName.split('-')
                if len(parts) >= 4:
                    serie = parts[2]
                    numero = parts[3]
                    print(f"Syncing single document: {serie}-{numero} (Sunat ID: {sunat_id})")
            
            # Process and sync the document
            synced_count, errors = process_and_sync_documents([target_document], process_sunat_document)
            
            if errors:
                return Response(
                    {
                        'synced': synced_count,
                        'sunat_id': sunat_id,
                        'errors': errors
                    },
                    status=status.HTTP_200_OK if synced_count > 0 else status.HTTP_502_BAD_GATEWAY
                )
            
            # Get the updated document
            try:
                updated_document = Document.objects.get(sunat_id=sunat_id)
                doc_serializer = DocumentSerializer(updated_document)
                return Response(
                    {
                        'synced': synced_count,
                        'sunat_id': sunat_id,
                        'document': doc_serializer.data
                    },
                    status=status.HTTP_200_OK
                )
            except Document.DoesNotExist:
                return Response(
                    {
                        'synced': synced_count,
                        'sunat_id': sunat_id,
                        'message': 'Document processed but not found in database'
                    },
                    status=status.HTTP_200_OK
                )
            
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

    @action(detail=False, methods=['get'], url_path='get-pdf')
    def get_pdf(self, request):
        """
        Get PDF representation of a document from Sunat (ticket80mm format)
        
        Query parameters (one required):
            sunat_id: The Sunat document ID
            OR
            document_id: The local database document ID (UUID) - will look up sunat_id
        """
        document_id = request.query_params.get('document_id')
        sunat_id = request.query_params.get('sunat_id')
        
        # Hardcode format to ticket80mm
        pdf_format = 'ticket80mm'
        
        # Get sunat_id from document_id if not provided
        if document_id and not sunat_id:
            try:
                db_document = Document.objects.get(id=document_id)
                sunat_id = db_document.sunat_id
                if not sunat_id:
                    return Response(
                        {'error': f'Document {document_id} does not have a sunat_id'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            except Document.DoesNotExist:
                return Response(
                    {'error': f'Document with id "{document_id}" not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        if not sunat_id:
            return Response(
                {'error': 'Either document_id or sunat_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        persona_id = settings.SUNAT_PERSONA_ID
        persona_token = settings.SUNAT_PERSONA_TOKEN
        
        if not persona_id or not persona_token:
            return Response(
                {'error': 'Sunat API credentials not configured'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        try:
            # First, fetch document from Sunat to get the actual fileName
            sunat_url = settings.SUNAT_API_URL
            get_by_id_endpoint = f"{sunat_url.rstrip('/')}/{sunat_id}/getById"
            
            sunat_response = requests.get(
                get_by_id_endpoint,
                params={
                    'personaId': persona_id,
                    'personaToken': persona_token,
                },
                timeout=30
            )
            
            fileName = None
            if sunat_response.status_code == 200:
                sunat_doc = sunat_response.json()
                if isinstance(sunat_doc, dict) and sunat_doc.get('fileName'):
                    fileName = f"{sunat_doc['fileName']}.pdf"
            
            # Fallback: construct fileName from database if available
            if not fileName:
                try:
                    db_document = Document.objects.get(sunat_id=sunat_id)
                    # Construct fileName: RUC-TYPE-SERIE-NUMERO.pdf
                    fileName = f"20482674828-{db_document.document_type}-{db_document.serie}-{db_document.numero}.pdf"
                except Document.DoesNotExist:
                    fileName = "document.pdf"
            
            # Construct getPDF URL
            # Endpoint format: /api/documents/:documentId/getPDF/:format/:fileName.pdf
            # This redirects to pdf.apisunat.com, so requests will follow redirects automatically
            base_url = sunat_url.rstrip('/')
            endpoint = f"{base_url}/{sunat_id}/getPDF/{pdf_format}/{fileName}"
            
            print(f"Fetching PDF from Sunat: {endpoint}")
            
            response = requests.get(
                endpoint,
                params={
                    'personaId': persona_id,
                    'personaToken': persona_token,
                },
                timeout=30,
                stream=True,  # Stream for binary content
                allow_redirects=True  # Follow redirects to pdf.apisunat.com
            )
            
            if response.status_code == 404:
                return Response(
                    {
                        'error': 'PDF not found in Sunat',
                        'sunat_id': sunat_id,
                        'endpoint_used': endpoint,
                        'help': 'Make sure the document exists and the format/fileName are correct'
                    },
                    status=status.HTTP_404_NOT_FOUND
                )
            
            response.raise_for_status()
            
            # Check if response is PDF
            content_type = response.headers.get('Content-Type', '')
            if 'pdf' not in content_type.lower():
                return Response(
                    {
                        'error': 'Response is not a PDF',
                        'content_type': content_type,
                        'response_preview': response.text[:200] if hasattr(response, 'text') else 'N/A'
                    },
                    status=status.HTTP_502_BAD_GATEWAY
                )
            
            # Return PDF as file download
            from django.http import HttpResponse
            pdf_response = HttpResponse(
                response.content,
                content_type='application/pdf'
            )
            pdf_response['Content-Disposition'] = f'inline; filename="{fileName}"'
            return pdf_response
            
        except requests.exceptions.RequestException as e:
            return Response(
                {'error': f'Failed to fetch PDF from Sunat: {str(e)}'},
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
        Create an invoice (factura) in Sunat and optionally return PDF
        
        Request body:
        {
            "order_items": [
                {"id": "1", "name": "Producto 1", "quantity": 2, "cost": 50.00}
            ],
            "ruc": "20123456789",
            "razon_social": "Empresa S.A.C.",
            "address": "Av. Principal 123",
            "order_id": 123,  // Optional: Link the created document to an order
            "return_pdf": true  // Optional: If true, returns PDF directly in response
        }
        """
        print('create_invoice request.data', request.data)
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
                razon_social=serializer.validated_data['razon_social'],
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
            
            # Get current timestamp in milliseconds (for sunat_issue_time)
            current_timestamp = int(datetime.now().timestamp() * 1000)
            
            # Create document
            document = Document.objects.create(
                sunat_id=sunat_response.get('documentId'),
                document_type='01',
                serie=serie,
                numero=numero,
                sunat_status='PENDIENTE',
                status='pending',
                amount=Decimal(str(total_amount)),
                sunat_issue_time=current_timestamp,
            )
            
            # Update order with document if order_id is provided
            order_id = serializer.validated_data.get('order_id')
            if order_id:
                try:
                    from store.models import Order
                    order = Order.objects.get(id=order_id)
                    order.document = document
                    order.save()
                except ObjectDoesNotExist:
                    # Order doesn't exist, but document was created successfully
                    # Don't fail the request, just log or ignore
                    pass
            
            # Check if client wants PDF in response
            return_pdf = serializer.validated_data.get('return_pdf', False)
            
            # Try to fetch PDF if requested (with retry logic)
            # Note: Document creation in Sunat is async, so we wait for it to be ready first
            if return_pdf:
                pdf_bytes, fileName = self._fetch_pdf_binary(document.sunat_id, max_retries=8, delay=4)
                if pdf_bytes:
                    from django.http import HttpResponse
                    pdf_response = HttpResponse(pdf_bytes, content_type='application/pdf')
                    pdf_response['Content-Disposition'] = f'inline; filename="{fileName}"'
                    pdf_response['X-Content-Type-Options'] = 'nosniff'
                    return pdf_response
            
            # Return created document with PDF URL
            doc_serializer = DocumentSerializer(document)
            response_data = doc_serializer.data
            response_data['pdf_url'] = f"/taxes/documents/get-pdf/?sunat_id={document.sunat_id}"
            return Response(response_data, status=status.HTTP_201_CREATED)
            
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
        Create a ticket (boleta) in Sunat and optionally return PDF
        
        Request body:
        {
            "order_items": [
                {"id": "1", "name": "Producto 1", "quantity": 2, "cost": 50.00}
            ],
            "order_id": 123,  // Optional: Link the created document to an order
            "return_pdf": true  // Optional: If true, returns PDF directly in response
        }
        """
        print('create_ticket request.data', request.data)
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
            
            # Get current timestamp in milliseconds (for sunat_issue_time)
            current_timestamp = int(datetime.now().timestamp() * 1000)
            
            # Create document
            document = Document.objects.create(
                sunat_id=sunat_response.get('documentId'),
                document_type='03',
                serie=serie,
                numero=numero,
                sunat_status='PENDIENTE',
                status='pending',
                amount=Decimal(str(total_amount)),
                sunat_issue_time=current_timestamp,
            )
            
            # Update order with document if order_id is provided
            order_id = serializer.validated_data.get('order_id')
            if order_id:
                try:
                    from store.models import Order
                    order = Order.objects.get(id=order_id)
                    order.document = document
                    order.save()
                except ObjectDoesNotExist:
                    # Order doesn't exist, but document was created successfully
                    # Don't fail the request, just log or ignore
                    pass
            
            # Check if client wants PDF in response
            return_pdf = serializer.validated_data.get('return_pdf', False)
            
            # Try to fetch PDF if requested (with retry logic)
            # Note: Document creation in Sunat is async, so we wait for it to be ready first
            if return_pdf:
                pdf_bytes, fileName = self._fetch_pdf_binary(document.sunat_id, max_retries=8, delay=4)
                if pdf_bytes:
                    from django.http import HttpResponse
                    pdf_response = HttpResponse(pdf_bytes, content_type='application/pdf')
                    pdf_response['Content-Disposition'] = f'inline; filename="{fileName}"'
                    pdf_response['X-Content-Type-Options'] = 'nosniff'
                    return pdf_response
            
            # Return created document with PDF URL
            doc_serializer = DocumentSerializer(document)
            response_data = doc_serializer.data
            response_data['pdf_url'] = f"/taxes/documents/get-pdf/?sunat_id={document.sunat_id}"
            return Response(response_data, status=status.HTTP_201_CREATED)
            
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
