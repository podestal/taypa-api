import requests
from decimal import Decimal
from datetime import datetime, timedelta
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from django.db.models import F, Case, When, IntegerField, Q, Sum
from django.core.exceptions import ObjectDoesNotExist
from .models import Document
from .serializers import (
    DocumentSerializer,
    CreateInvoiceSerializer,
    CreateTicketSerializer,
    GeneratePDFSerializer
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
from .pdf_utils import generate_ticket_pdf
import time
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
    permission_classes = [IsAuthenticated]

    def list(self, request, *args, **kwargs):
        """
        List documents with optional filters:
        - document_type: 'boleta' or 'factura'
        - date_filter: 'today', 'this_week', 'last_seven_days', 'this_month', 'this_year'
        - date: specific date (YYYY-MM-DD)
        - start_date and end_date: date range (YYYY-MM-DD)
        - year: filter by year (defaults to current year)
        """
        queryset = self.get_queryset()
        
        # Filter by document type
        document_type = request.query_params.get('document_type', None)
        if document_type:
            if document_type.lower() == 'boleta':
                queryset = queryset.filter(document_type='03')
            elif document_type.lower() == 'factura':
                queryset = queryset.filter(document_type='01')
        
        # Filter by date
        date_filter = request.query_params.get('date_filter', None)
        date = request.query_params.get('date', None)
        start_date = request.query_params.get('start_date', None)
        end_date = request.query_params.get('end_date', None)
        
        # Check if any date filters are specified
        has_date_filters = bool(date_filter or date or start_date or end_date)
        
        # Filter by year (defaults to current year only if no other date filters are specified)
        now = timezone.now()
        year_param = request.query_params.get('year', None)
        if year_param:
            try:
                year = int(year_param)
                if year < 1900 or year > 2100:
                    return Response(
                        {'error': 'Invalid year. Must be between 1900 and 2100'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                # Apply year filter if explicitly provided
                start_of_year = timezone.make_aware(datetime(year, 1, 1, 0, 0, 0))
                end_of_year = timezone.make_aware(datetime(year + 1, 1, 1, 0, 0, 0))
                queryset = queryset.filter(created_at__gte=start_of_year, created_at__lt=end_of_year)
            except ValueError:
                return Response(
                    {'error': 'Invalid year format. Must be a number'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        elif not has_date_filters:
            # Default to current year only if no other date filters are specified
            year = now.year
            start_of_year = timezone.make_aware(datetime(year, 1, 1, 0, 0, 0))
            end_of_year = timezone.make_aware(datetime(year + 1, 1, 1, 0, 0, 0))
            queryset = queryset.filter(created_at__gte=start_of_year, created_at__lt=end_of_year)
        
        date_filters = Q()
        
        if date_filter:
            if date_filter == 'today':
                # Today: from start of today to end of today
                start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
                end_of_day = start_of_day + timedelta(days=1)
                date_filters = Q(created_at__gte=start_of_day, created_at__lt=end_of_day)
            
            elif date_filter == 'this_week':
                # This week: from Monday of current week to end of Sunday
                days_since_monday = now.weekday()
                start_of_week = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
                end_of_week = start_of_week + timedelta(days=7)
                date_filters = Q(created_at__gte=start_of_week, created_at__lt=end_of_week)
            
            elif date_filter == 'last_seven_days':
                # Last 7 days: from 7 days ago to now
                seven_days_ago = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
                date_filters = Q(created_at__gte=seven_days_ago, created_at__lte=now)
            
            elif date_filter == 'this_month':
                # This month: from first day of current month to end of last day
                start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                if now.month == 12:
                    end_of_month = start_of_month.replace(year=now.year + 1, month=1)
                else:
                    end_of_month = start_of_month.replace(month=now.month + 1)
                date_filters = Q(created_at__gte=start_of_month, created_at__lt=end_of_month)
            
            elif date_filter == 'this_year':
                # This year: from January 1st to end of December 31st
                start_of_year = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
                end_of_year = start_of_year.replace(year=now.year + 1)
                date_filters = Q(created_at__gte=start_of_year, created_at__lt=end_of_year)
        
        elif date:
            # Specific date: YYYY-MM-DD format
            try:
                date_obj = datetime.strptime(date, '%Y-%m-%d').date()
                start_of_day = timezone.make_aware(datetime.combine(date_obj, datetime.min.time()))
                end_of_day = start_of_day + timedelta(days=1)
                date_filters = Q(created_at__gte=start_of_day, created_at__lt=end_of_day)
            except ValueError:
                return Response(
                    {'error': 'Invalid date format. Use YYYY-MM-DD'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        elif start_date or end_date:
            # Date range
            range_filters = []
            
            if start_date:
                try:
                    start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
                    start_datetime = timezone.make_aware(datetime.combine(start_date_obj, datetime.min.time()))
                    range_filters.append(Q(created_at__gte=start_datetime))
                except ValueError:
                    return Response(
                        {'error': 'Invalid start_date format. Use YYYY-MM-DD'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            if end_date:
                try:
                    end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
                    end_datetime = timezone.make_aware(datetime.combine(end_date_obj, datetime.max.time()))
                    range_filters.append(Q(created_at__lte=end_datetime))
                except ValueError:
                    return Response(
                        {'error': 'Invalid end_date format. Use YYYY-MM-DD'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            if range_filters:
                # Combine all range filters with AND
                combined_filter = range_filters[0]
                for f in range_filters[1:]:
                    combined_filter = combined_filter & f
                date_filters = combined_filter
        
        # Apply date filters if any
        if date_filters:
            queryset = queryset.filter(date_filters)
        
        # Calculate total amount from filtered queryset (before pagination)
        total_amount = queryset.aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')
        
        # Apply pagination
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            # Add total_amount to the response
            response.data['total_amount'] = str(total_amount)
            return response
        
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'results': serializer.data,
            'total_amount': str(total_amount)
        })

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

    @action(detail=False, methods=['get', 'post'], url_path='sync-single', url_name='sync-single')
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

    @action(detail=False, methods=['post'], url_path='create-invoice')
    def create_invoice(self, request):
        """
        Create an invoice (factura) in Sunat and sync it
        
        After creating the document, attempts to sync it from Sunat API
        with retries until status is ACEPTADO (1s, 2s, 3s, 5s delays)
        
        Request body:
        {
            "order_items": [
                {"id": "1", "name": "Producto 1", "quantity": 2, "cost": 50.00}
            ],
            "ruc": "20123456789",
            "razon_social": "Empresa S.A.C.",
            "address": "Av. Principal 123",
            "order_id": 123  // Optional: Link the created document to an order
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
            
            # Try to sync the document with retries (1s, 2s, 3s, 5s)
            # Keep retrying until status is ACEPTADO (accepted)
            sunat_id = document.sunat_id
            delays = [1, 2, 3, 5]  # Wait 1s before first attempt, then 2s, 3s, 5s
            sunat_url = settings.SUNAT_API_URL
            max_attempts = len(delays)
            
            sync_start_time = time.time()
            synced_successfully = False
            attempts_made = 0
            
            print(f"\n{'='*60}")
            print(f"SYNC: Starting sync for document {sunat_id} ({document.serie}-{document.numero})")
            print(f"      Will retry until status is ACEPTADO")
            print(f"{'='*60}")
            
            # Try syncing with retries until we get ACEPTADO status
            for attempt in range(max_attempts):
                attempts_made = attempt + 1
                attempt_start_time = time.time()
                
                try:
                    # Wait before each attempt (except first one)
                    if attempt > 0:
                        delay = delays[attempt - 1]
                        print(f"⏳ Waiting {delay}s before sync attempt {attempts_made}/{max_attempts}...")
                        time.sleep(delay)
                    else:
                        print(f"🔄 Sync attempt {attempts_made}/{max_attempts}: Fetching from Sunat...")
                    
                    # Fetch document from Sunat (same as sync_single)
                    endpoint = f"{sunat_url.rstrip('/')}/{sunat_id}/getById"
                    response = requests.get(
                        endpoint,
                        params={
                            'personaId': persona_id,
                            'personaToken': persona_token,
                        },
                        timeout=30
                    )
                    
                    if response.status_code == 404:
                        attempt_time = time.time() - attempt_start_time
                        print(f"❌ Attempt {attempts_made} failed: Document not found yet (took {attempt_time:.2f}s)")
                        if attempts_made < max_attempts:
                            continue
                        else:
                            break
                    
                    response.raise_for_status()
                    sunat_doc = response.json()
                    
                    if not isinstance(sunat_doc, dict) or not sunat_doc.get('id'):
                        attempt_time = time.time() - attempt_start_time
                        print(f"❌ Attempt {attempts_made} failed: Invalid response format (took {attempt_time:.2f}s)")
                        continue
                    
                    # Check the status from Sunat
                    sunat_status = sunat_doc.get('status', '').upper()
                    print(f"✅ Document found! Status: {sunat_status}")
                    
                    # Sync the document (even if status is not ACEPTADO yet)
                    synced_count, errors = process_and_sync_documents([sunat_doc], process_sunat_document)
                    
                    if synced_count > 0:
                        # Refresh the document from database to get all updates
                        document.refresh_from_db()
                        
                        # Check if status is ACEPTADO - only then we're done
                        if sunat_status == 'ACEPTADO':
                            synced_successfully = True
                            attempt_time = time.time() - attempt_start_time
                            total_time = time.time() - sync_start_time
                            
                            print(f"\n{'='*60}")
                            print(f"✅ SYNC SUCCESS - DOCUMENT ACCEPTED!")
                            print(f"   Document: {document.serie}-{document.numero}")
                            print(f"   Status: {document.sunat_status} -> {document.status}")
                            print(f"   Amount: {document.amount}")
                            print(f"   Attempts: {attempts_made}/{max_attempts}")
                            print(f"   Attempt time: {attempt_time:.2f}s")
                            print(f"   Total time: {total_time:.2f}s")
                            print(f"{'='*60}\n")
                            break
                        elif sunat_status in ['RECHAZADO', 'EXCEPCION']:
                            # Final status but not accepted - stop retrying
                            attempt_time = time.time() - attempt_start_time
                            total_time = time.time() - sync_start_time
                            print(f"\n{'='*60}")
                            print(f"⚠️  DOCUMENT NOT ACCEPTED")
                            print(f"   Document: {document.serie}-{document.numero}")
                            print(f"   Status: {document.sunat_status} -> {document.status}")
                            print(f"   Attempts: {attempts_made}/{max_attempts}")
                            print(f"   Total time: {total_time:.2f}s")
                            print(f"{'='*60}\n")
                            break
                        else:
                            # Status is still PENDIENTE or other - keep retrying
                            attempt_time = time.time() - attempt_start_time
                            print(f"⏳ Status is {sunat_status}, not ACEPTADO yet. Will retry... (took {attempt_time:.2f}s)")
                            if attempts_made < max_attempts:
                                continue
                            else:
                                print(f"⚠️  Max attempts reached. Status is still {sunat_status}, not ACEPTADO.")
                                break
                    else:
                        attempt_time = time.time() - attempt_start_time
                        print(f"⚠️  Attempt {attempts_made} failed: Sync returned 0 documents (took {attempt_time:.2f}s)")
                        
                except requests.exceptions.RequestException as e:
                    attempt_time = time.time() - attempt_start_time
                    print(f"❌ Attempt {attempts_made} failed: Network error - {str(e)} (took {attempt_time:.2f}s)")
                    if attempts_made < max_attempts:
                        continue
                except Exception as e:
                    attempt_time = time.time() - attempt_start_time
                    print(f"❌ Attempt {attempts_made} failed: {str(e)} (took {attempt_time:.2f}s)")
                    if attempts_made < max_attempts:
                        continue
            
            # Final summary
            if not synced_successfully:
                total_time = time.time() - sync_start_time
                print(f"\n{'='*60}")
                print(f"⚠️  SYNC FAILED (document created but not synced)")
                print(f"   Document: {document.serie}-{document.numero}")
                print(f"   Attempts: {attempts_made}/{max_attempts}")
                print(f"   Total time: {total_time:.2f}s")
                print(f"   Use /sync-single/?sunat_id={sunat_id} to retry later")
                print(f"{'='*60}\n")
            
            # Return created document (synced if successful)
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
        Create a ticket (boleta) in Sunat and sync it
        
        After creating the document, attempts to sync it from Sunat API
        with retries: 1s, 2s, 3s, 5s delays
        
        Request body:
        {
            "order_items": [
                {"id": "1", "name": "Producto 1", "quantity": 2, "cost": 50.00}
            ],
            "order_id": 123  // Optional: Link the created document to an order
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
            
            # Try to sync the document with retries (1s, 2s, 3s, 5s)
            # Keep retrying until status is ACEPTADO (accepted)
            sunat_id = document.sunat_id
            delays = [1, 2, 3, 5]  # Wait 1s before first attempt, then 2s, 3s, 5s
            sunat_url = settings.SUNAT_API_URL
            max_attempts = len(delays)
            
            sync_start_time = time.time()
            synced_successfully = False
            attempts_made = 0
            
            print(f"\n{'='*60}")
            print(f"SYNC: Starting sync for document {sunat_id} ({document.serie}-{document.numero})")
            print(f"      Will retry until status is ACEPTADO")
            print(f"{'='*60}")
            
            # Try syncing with retries until we get ACEPTADO status
            for attempt in range(max_attempts):
                attempts_made = attempt + 1
                attempt_start_time = time.time()
                
                try:
                    # Wait before each attempt (except first one)
                    if attempt > 0:
                        delay = delays[attempt - 1]
                        print(f"⏳ Waiting {delay}s before sync attempt {attempts_made}/{max_attempts}...")
                        time.sleep(delay)
                    else:
                        print(f"🔄 Sync attempt {attempts_made}/{max_attempts}: Fetching from Sunat...")
                    
                    # Fetch document from Sunat (same as sync_single)
                    endpoint = f"{sunat_url.rstrip('/')}/{sunat_id}/getById"
                    response = requests.get(
                        endpoint,
                        params={
                            'personaId': persona_id,
                            'personaToken': persona_token,
                        },
                        timeout=30
                    )
                    
                    if response.status_code == 404:
                        attempt_time = time.time() - attempt_start_time
                        print(f"❌ Attempt {attempts_made} failed: Document not found yet (took {attempt_time:.2f}s)")
                        if attempts_made < max_attempts:
                            continue
                        else:
                            break
                    
                    response.raise_for_status()
                    sunat_doc = response.json()
                    
                    if not isinstance(sunat_doc, dict) or not sunat_doc.get('id'):
                        attempt_time = time.time() - attempt_start_time
                        print(f"❌ Attempt {attempts_made} failed: Invalid response format (took {attempt_time:.2f}s)")
                        continue
                    
                    # Check the status from Sunat
                    sunat_status = sunat_doc.get('status', '').upper()
                    print(f"✅ Document found! Status: {sunat_status}")
                    
                    # Sync the document (even if status is not ACEPTADO yet)
                    synced_count, errors = process_and_sync_documents([sunat_doc], process_sunat_document)
                    
                    if synced_count > 0:
                        # Refresh the document from database to get all updates
                        document.refresh_from_db()
                        
                        # Check if status is ACEPTADO - only then we're done
                        if sunat_status == 'ACEPTADO':
                            synced_successfully = True
                            attempt_time = time.time() - attempt_start_time
                            total_time = time.time() - sync_start_time
                            
                            print(f"\n{'='*60}")
                            print(f"✅ SYNC SUCCESS - DOCUMENT ACCEPTED!")
                            print(f"   Document: {document.serie}-{document.numero}")
                            print(f"   Status: {document.sunat_status} -> {document.status}")
                            print(f"   Amount: {document.amount}")
                            print(f"   Attempts: {attempts_made}/{max_attempts}")
                            print(f"   Attempt time: {attempt_time:.2f}s")
                            print(f"   Total time: {total_time:.2f}s")
                            print(f"{'='*60}\n")
                            break
                        elif sunat_status in ['RECHAZADO', 'EXCEPCION']:
                            # Final status but not accepted - stop retrying
                            attempt_time = time.time() - attempt_start_time
                            total_time = time.time() - sync_start_time
                            print(f"\n{'='*60}")
                            print(f"⚠️  DOCUMENT NOT ACCEPTED")
                            print(f"   Document: {document.serie}-{document.numero}")
                            print(f"   Status: {document.sunat_status} -> {document.status}")
                            print(f"   Attempts: {attempts_made}/{max_attempts}")
                            print(f"   Total time: {total_time:.2f}s")
                            print(f"{'='*60}\n")
                            break
                        else:
                            # Status is still PENDIENTE or other - keep retrying
                            attempt_time = time.time() - attempt_start_time
                            print(f"⏳ Status is {sunat_status}, not ACEPTADO yet. Will retry... (took {attempt_time:.2f}s)")
                            if attempts_made < max_attempts:
                                continue
                            else:
                                print(f"⚠️  Max attempts reached. Status is still {sunat_status}, not ACEPTADO.")
                                break
                    else:
                        attempt_time = time.time() - attempt_start_time
                        print(f"⚠️  Attempt {attempts_made} failed: Sync returned 0 documents (took {attempt_time:.2f}s)")
                        
                except requests.exceptions.RequestException as e:
                    attempt_time = time.time() - attempt_start_time
                    print(f"❌ Attempt {attempts_made} failed: Network error - {str(e)} (took {attempt_time:.2f}s)")
                    if attempts_made < max_attempts:
                        continue
                except Exception as e:
                    attempt_time = time.time() - attempt_start_time
                    print(f"❌ Attempt {attempts_made} failed: {str(e)} (took {attempt_time:.2f}s)")
                    if attempts_made < max_attempts:
                        continue
            
            # Final summary
            if not synced_successfully:
                total_time = time.time() - sync_start_time
                print(f"\n{'='*60}")
                print(f"⚠️  SYNC FAILED (document created but not synced)")
                print(f"   Document: {document.serie}-{document.numero}")
                print(f"   Attempts: {attempts_made}/{len(delays)}")
                print(f"   Total time: {total_time:.2f}s")
                print(f"   Use /sync-single/?sunat_id={sunat_id} to retry later")
                print(f"{'='*60}\n")
            
            # Return created document (synced if successful)
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

    @action(detail=False, methods=['post'], url_path='generate-ticket')
    def generate_ticket(self, request):
        """
        Generate PDF for ticket, boleta, or factura
        
        Request body for 'ticket' (simple ticket, no Sunat):
        {
            "document_type": "ticket",
            "order_items": [
                {"id": "1", "name": "Producto 1", "quantity": 2, "cost": 10.00}
            ],
            "order_number": "ORD-001",  // Optional
            "customer_name": "Juan Pérez"  // Optional
        }
        
        Request body for 'boleta' or 'factura' (Sunat documents):
        {
            "document_type": "boleta",  // or "factura"
            "document_id": "uuid-here"  // Local database document ID
            // OR
            "sunat_id": "sunat-id-here"  // Sunat document ID
        }
        """
        from django.http import HttpResponse
        
        serializer = GeneratePDFSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            document_type = serializer.validated_data['document_type']
            
            # Handle simple ticket (no Sunat)
            if document_type == 'ticket':
                order_items = serializer.validated_data['order_items']
                order_number = serializer.validated_data.get('order_number', '')
                customer_name = serializer.validated_data.get('customer_name', '')
                
                # Generate PDF locally
                pdf_buffer = generate_ticket_pdf(
                    order_items=order_items,
                    business_name="Taypa",
                    business_address="Avis Luz y Fuerza D-8",
                    business_ruc="20482674828",
                    order_number=order_number,
                    customer_name=customer_name,
                )
                
                # Return PDF response
                response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
                filename = f"ticket_{order_number or datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                response['Content-Disposition'] = f'inline; filename="{filename}"'
                return response
            
            # Handle boleta or factura (Sunat documents) - generate PDF locally from DB data
            else:  # document_type is 'boleta' or 'factura'
                # Get document from database
                document_id = serializer.validated_data.get('document_id')
                sunat_id = serializer.validated_data.get('sunat_id')
                
                try:
                    if document_id:
                        document = Document.objects.get(id=document_id)
                    else:
                        document = Document.objects.get(sunat_id=sunat_id)
                except Document.DoesNotExist:
                    return Response(
                        {'error': f'Document not found'},
                        status=status.HTTP_404_NOT_FOUND
                    )
                
                # Verify document type matches
                expected_type = '03' if document_type == 'boleta' else '01'
                if document.document_type != expected_type:
                    return Response(
                        {
                            'error': f'Document type mismatch. Expected {document_type} (type {expected_type}), but document is type {document.document_type}'
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Get the Order linked to this Document (via reverse FK)
                from store.models import Order
                try:
                    order = Order.objects.get(document=document)
                except Order.DoesNotExist:
                    return Response(
                        {'error': 'No order linked to this document. Cannot generate PDF without order items.'},
                        status=status.HTTP_404_NOT_FOUND
                    )
                except Order.MultipleObjectsReturned:
                    # Multiple orders might be linked, get the first one
                    order = Order.objects.filter(document=document).first()
                
                # Get order items from the order
                order_items_data = []
                for order_item in order.orderitem_set.all():
                    # Use dish.price as the unit price (from Dish model)
                    # OrderItem.price might store total or outdated price, so we use dish.price
                    unit_price = float(order_item.dish.price)
                    
                    # Get category name and combine with dish name
                    category_name = order_item.category.name if order_item.category else ''
                    dish_name = order_item.dish.name
                    display_name = f"{category_name} - {dish_name}" if category_name else dish_name
                    
                    order_items_data.append({
                        'id': str(order_item.dish.id),
                        'name': display_name,  # CategoryName - DishName
                        'quantity': float(order_item.quantity),
                        'cost': unit_price,  # Unit price from Dish.price
                    })
                
                if not order_items_data:
                    return Response(
                        {'error': 'Order has no items. Cannot generate PDF.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Print order items that will go to PDF
                print(f"\n{'='*60}")
                print(f"📄 Generating PDF for {document_type.upper()}: {document.serie}-{document.numero}")
                print(f"{'='*60}")
                print(f"Order Items ({len(order_items_data)} items):")
                for idx, item in enumerate(order_items_data, 1):
                    item_total = item['quantity'] * item['cost']
                    print(f"  {idx}. {item['name']}")
                    print(f"     Quantity: {item['quantity']} x ${item['cost']:.2f} = ${item_total:.2f}")
                print(f"{'='*60}\n")
                
                # Get customer name if available
                customer_name = None
                if order.customer:
                    customer_name = f"{order.customer.first_name} {order.customer.last_name}".strip()
                
                # Generate document code (serie-numero)
                document_code = f"{document.serie}-{document.numero}"
                
                # Get document emission date (use sunat_issue_time if available, otherwise created_at)
                # sunat_issue_time is a Unix timestamp (milliseconds), convert to datetime
                if document.sunat_issue_time:
                    # Convert Unix timestamp (milliseconds) to datetime
                    # Note: fromtimestamp returns naive datetime, but created_at is timezone-aware
                    document_date = datetime.fromtimestamp(document.sunat_issue_time / 1000.0)
                else:
                    document_date = document.created_at
                
                # For factura: Get customer company info from XML
                customer_razon_social = None
                customer_ruc = None
                customer_address = None
                
                if document_type == 'factura' and document.xml_url:
                    try:
                        from .services import download_and_extract_xml, parse_xml_customer_info
                        xml_content, error = download_and_extract_xml(document.xml_url)
                        if xml_content:
                            customer_info = parse_xml_customer_info(xml_content)
                            customer_razon_social = customer_info.get('razon_social')
                            customer_ruc = customer_info.get('ruc')
                            customer_address = customer_info.get('address')
                        else:
                            print(f"Warning: Could not extract customer info from XML: {error}")
                    except Exception as e:
                        print(f"Error extracting customer info from XML: {str(e)}")
                
                # Generate PDF locally using our PDF generator
                # Don't pass order_number for boleta/factura (already shown at top)
                pdf_buffer = generate_ticket_pdf(
                    order_items=order_items_data,
                    business_name="Taypa",
                    business_address="Avis Luz y Fuerza D-8",
                    business_ruc="20482674828",
                    order_number=None,  # Not shown for boleta/factura (already at top)
                    customer_name=customer_name,
                    document_type=document_type,  # 'boleta' or 'factura'
                    document_code=document_code,  # Serie-numero like "B001-00003"
                    document_date=document_date,  # Emission date
                    customer_razon_social=customer_razon_social,  # For factura
                    customer_ruc=customer_ruc,  # For factura
                    customer_address=customer_address,  # For factura
                )
                
                # Return PDF response
                response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
                filename = f"{document_type}_{document.serie}-{document.numero}.pdf"
                response['Content-Disposition'] = f'inline; filename="{filename}"'
                return response
            
        except Exception as e:
            return Response(
                {'error': f'Failed to generate PDF: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
