import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import patch, Mock
from model_bakery import baker
from rest_framework import status
from django.urls import reverse
from django.conf import settings

from taxes import models


@pytest.mark.django_db
class TestDocumentGetTicketsView:
    """Tests for GET /api/documents/get-tickets/ - Get tickets from database"""
    
    def test_get_tickets_unauthenticated(self, api_client):
        """Test that unauthenticated requests are rejected"""
        url = reverse('document-get-tickets')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_get_tickets_empty(self, authenticated_api_client):
        """Test getting tickets when none exist"""
        url = reverse('document-get-tickets')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert 'results' in response.data or isinstance(response.data, list)
        if 'results' in response.data:
            assert response.data['results'] == []
            assert response.data['count'] == 0
        else:
            assert response.data == []
    
    def test_get_tickets_only_returns_tickets(self, authenticated_api_client):
        """Test that only tickets (type 03) are returned, not invoices"""
        # Create tickets
        ticket1 = baker.make(
            models.Document,
            document_type='03',
            serie='B001',
            numero='00000001',
            sunat_id='ticket-1',
            amount=Decimal('59.00'),
        )
        ticket2 = baker.make(
            models.Document,
            document_type='03',
            serie='B001',
            numero='00000002',
            sunat_id='ticket-2',
            amount=Decimal('118.00'),
        )
        
        # Create invoices (should not be returned)
        invoice1 = baker.make(
            models.Document,
            document_type='01',
            serie='F001',
            numero='00000001',
            sunat_id='invoice-1',
            amount=Decimal('118.00'),
        )
        
        url = reverse('document-get-tickets')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
        assert len(data) == 2
        
        # Verify all returned documents are tickets
        for doc in data:
            assert doc['document_type'] == '03'
            assert doc['id'] in [str(ticket1.id), str(ticket2.id)]
            assert doc['id'] != str(invoice1.id)
    
    def test_get_tickets_ordering_newest_first(self, authenticated_api_client):
        """Test that tickets are ordered with NULL sunat_issue_time first (newest)"""
        # Create old ticket with issue_time
        old_ticket = baker.make(
            models.Document,
            document_type='03',
            serie='B001',
            numero='00000001',
            sunat_id='ticket-old',
            amount=Decimal('59.00'),
            sunat_issue_time=int((datetime.now() - timedelta(days=5)).timestamp() * 1000),
        )
        
        # Create newer ticket with issue_time
        new_ticket = baker.make(
            models.Document,
            document_type='03',
            serie='B001',
            numero='00000002',
            sunat_id='ticket-new',
            amount=Decimal('118.00'),
            sunat_issue_time=int(datetime.now().timestamp() * 1000),
        )
        
        # Create pending ticket without issue_time (should be first)
        pending_ticket = baker.make(
            models.Document,
            document_type='03',
            serie='B001',
            numero='00000003',
            sunat_id='ticket-pending',
            amount=Decimal('120.00'),
            sunat_issue_time=None,
        )
        
        url = reverse('document-get-tickets')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
        assert len(data) == 3
        
        # Pending ticket (NULL sunat_issue_time) should be first
        assert data[0]['id'] == str(pending_ticket.id)
        # Then newer ticket
        assert data[1]['id'] == str(new_ticket.id)
        # Then older ticket
        assert data[2]['id'] == str(old_ticket.id)
    
    def test_get_tickets_pagination(self, authenticated_api_client):
        """Test that pagination works correctly"""
        # Create 15 tickets (more than default page size of 10)
        tickets = baker.make(
            models.Document,
            document_type='03',
            serie='B001',
            _quantity=15,
        )
        
        url = reverse('document-get-tickets')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert 'results' in response.data
        assert len(response.data['results']) == 10  # Default page size
        assert response.data['count'] == 15
        assert response.data['next'] is not None  # Should have next page
        assert response.data['previous'] is None  # First page
    
    def test_get_tickets_pagination_page_2(self, authenticated_api_client):
        """Test pagination page 2"""
        # Create 15 tickets
        tickets = baker.make(
            models.Document,
            document_type='03',
            serie='B001',
            _quantity=15,
        )
        
        url = reverse('document-get-tickets')
        response = authenticated_api_client.get(url, {'page': 2})
        
        assert response.status_code == status.HTTP_200_OK
        assert 'results' in response.data
        assert len(response.data['results']) == 5  # Remaining tickets
        assert response.data['count'] == 15
        assert response.data['previous'] is not None  # Should have previous page
        assert response.data['next'] is None  # Last page
    
    def test_get_tickets_custom_page_size(self, authenticated_api_client):
        """Test custom page size"""
        # Create 15 tickets
        tickets = baker.make(
            models.Document,
            document_type='03',
            serie='B001',
            _quantity=15,
        )
        
        url = reverse('document-get-tickets')
        response = authenticated_api_client.get(url, {'page_size': 20})
        
        assert response.status_code == status.HTTP_200_OK
        assert 'results' in response.data
        assert len(response.data['results']) == 15  # All tickets fit in one page
        assert response.data['count'] == 15
        assert response.data['next'] is None


@pytest.mark.django_db
class TestDocumentGetInvoicesView:
    """Tests for GET /api/documents/get-invoices/ - Get invoices from database"""
    
    def test_get_invoices_unauthenticated(self, api_client):
        """Test that unauthenticated requests are rejected"""
        url = reverse('document-get-invoices')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_get_invoices_empty(self, authenticated_api_client):
        """Test getting invoices when none exist"""
        url = reverse('document-get-invoices')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert 'results' in response.data or isinstance(response.data, list)
        if 'results' in response.data:
            assert response.data['results'] == []
            assert response.data['count'] == 0
        else:
            assert response.data == []
    
    def test_get_invoices_only_returns_invoices(self, authenticated_api_client):
        """Test that only invoices (type 01) are returned, not tickets"""
        # Create invoices
        invoice1 = baker.make(
            models.Document,
            document_type='01',
            serie='F001',
            numero='00000001',
            sunat_id='invoice-1',
            amount=Decimal('118.00'),
        )
        invoice2 = baker.make(
            models.Document,
            document_type='01',
            serie='F001',
            numero='00000002',
            sunat_id='invoice-2',
            amount=Decimal('236.00'),
        )
        
        # Create tickets (should not be returned)
        ticket1 = baker.make(
            models.Document,
            document_type='03',
            serie='B001',
            numero='00000001',
            sunat_id='ticket-1',
            amount=Decimal('59.00'),
        )
        
        url = reverse('document-get-invoices')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
        assert len(data) == 2
        
        # Verify all returned documents are invoices
        for doc in data:
            assert doc['document_type'] == '01'
            assert doc['id'] in [str(invoice1.id), str(invoice2.id)]
            assert doc['id'] != str(ticket1.id)
    
    def test_get_invoices_ordering_newest_first(self, authenticated_api_client):
        """Test that invoices are ordered with NULL sunat_issue_time first (newest)"""
        # Create old invoice with issue_time
        old_invoice = baker.make(
            models.Document,
            document_type='01',
            serie='F001',
            numero='00000001',
            sunat_id='invoice-old',
            amount=Decimal('118.00'),
            sunat_issue_time=int((datetime.now() - timedelta(days=5)).timestamp() * 1000),
        )
        
        # Create newer invoice with issue_time
        new_invoice = baker.make(
            models.Document,
            document_type='01',
            serie='F001',
            numero='00000002',
            sunat_id='invoice-new',
            amount=Decimal('236.00'),
            sunat_issue_time=int(datetime.now().timestamp() * 1000),
        )
        
        # Create pending invoice without issue_time (should be first)
        pending_invoice = baker.make(
            models.Document,
            document_type='01',
            serie='F001',
            numero='00000003',
            sunat_id='invoice-pending',
            amount=Decimal('120.00'),
            sunat_issue_time=None,
        )
        
        url = reverse('document-get-invoices')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
        assert len(data) == 3
        
        # Pending invoice (NULL sunat_issue_time) should be first
        assert data[0]['id'] == str(pending_invoice.id)
        # Then newer invoice
        assert data[1]['id'] == str(new_invoice.id)
        # Then older invoice
        assert data[2]['id'] == str(old_invoice.id)
    
    def test_get_invoices_pagination(self, authenticated_api_client):
        """Test that pagination works correctly"""
        # Create 15 invoices (more than default page size of 10)
        invoices = baker.make(
            models.Document,
            document_type='01',
            serie='F001',
            _quantity=15,
        )
        
        url = reverse('document-get-invoices')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert 'results' in response.data
        assert len(response.data['results']) == 10  # Default page size
        assert response.data['count'] == 15
        assert response.data['next'] is not None  # Should have next page
        assert response.data['previous'] is None  # First page
    
    def test_get_invoices_returns_all_fields(self, authenticated_api_client, document_invoice):
        """Test that all expected fields are returned"""
        url = reverse('document-get-invoices')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
        assert len(data) >= 1
        
        doc = data[0]
        # Check all important fields are present
        assert 'id' in doc
        assert 'document_type' in doc
        assert 'serie' in doc
        assert 'numero' in doc
        assert 'sunat_id' in doc
        assert 'sunat_status' in doc
        assert 'status' in doc
        assert 'amount' in doc
        assert 'created_at' in doc
        assert 'updated_at' in doc


@pytest.mark.django_db
class TestDocumentSyncView:
    """Tests for GET /taxes/documents/sync/ - Sync documents from Sunat API"""
    
    def test_sync_documents_unauthenticated(self, api_client):
        """Test that unauthenticated requests are rejected"""
        url = reverse('document-sync')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    @patch('taxes.views.settings')
    def test_sync_documents_missing_credentials(self, mock_settings, authenticated_api_client):
        """Test sync when Sunat API credentials are not configured"""
        mock_settings.SUNAT_PERSONA_ID = None
        mock_settings.SUNAT_PERSONA_TOKEN = None
        
        url = reverse('document-sync')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert 'error' in response.data
        assert 'credentials' in response.data['error'].lower()
    
    @patch('taxes.views.requests.get')
    @patch('taxes.views.process_sunat_document')
    def test_sync_documents_success(self, mock_process, mock_get, authenticated_api_client):
        """Test successful sync of documents from Sunat API"""
        # Mock Sunat API response
        mock_sunat_documents = [
            {
                'id': 'sunat-id-1',
                'type': '03',
                'status': 'ACEPTADO',
                'fileName': '20482674828-03-B001-00000001',
                'issueTime': int(datetime.now().timestamp() * 1000),
                'xml': 'https://cdn.apisunat.com/doc/example.xml',
                'cdr': 'https://cdn.apisunat.com/doc/example.cdr',
            },
            {
                'id': 'sunat-id-2',
                'type': '01',
                'status': 'ACEPTADO',
                'fileName': '20482674828-01-F001-00000001',
                'issueTime': int(datetime.now().timestamp() * 1000),
                'xml': 'https://cdn.apisunat.com/doc/example2.xml',
                'cdr': 'https://cdn.apisunat.com/doc/example2.cdr',
            },
        ]
        
        mock_response = Mock()
        mock_response.json.return_value = mock_sunat_documents
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        # Mock process_sunat_document to return processed data
        mock_process.return_value = {
            'amount': 118.00,
            'serie': 'B001',
            'numero': '00000001',
        }
        
        url = reverse('document-sync')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['synced'] == 2
        assert response.data['total'] == 2
        assert len(response.data['errors']) == 0
        
        # Verify documents were created in database
        assert models.Document.objects.filter(sunat_id='sunat-id-1').exists()
        assert models.Document.objects.filter(sunat_id='sunat-id-2').exists()
        
        # Verify API was called correctly
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert 'getAll' in call_args[0][0]
        assert call_args[1]['params']['personaId'] == settings.SUNAT_PERSONA_ID
    
    @patch('taxes.views.requests.get')
    @patch('taxes.views.process_sunat_document')
    def test_sync_documents_with_xml_error(self, mock_process, mock_get, authenticated_api_client):
        """Test sync when XML processing fails for some documents"""
        # Mock Sunat API response
        mock_sunat_documents = [
            {
                'id': 'sunat-id-1',
                'type': '03',
                'status': 'ACEPTADO',
                'fileName': '20482674828-03-B001-00000001',
                'issueTime': int(datetime.now().timestamp() * 1000),
                'xml': 'https://cdn.apisunat.com/doc/example.xml',
            },
            {
                'id': 'sunat-id-2',
                'type': '01',
                'status': 'ACEPTADO',
                'fileName': '20482674828-01-F001-00000001',
                'issueTime': int(datetime.now().timestamp() * 1000),
                'xml': 'https://cdn.apisunat.com/doc/invalid.xml',
            },
        ]
        
        mock_response = Mock()
        mock_response.json.return_value = mock_sunat_documents
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        # Mock process_sunat_document - first succeeds, second fails
        def mock_process_side_effect(doc):
            if doc['id'] == 'sunat-id-1':
                return {'amount': 118.00, 'serie': 'B001', 'numero': '00000001'}
            else:
                return {'error': 'Failed to download XML'}
        
        mock_process.side_effect = mock_process_side_effect
        
        url = reverse('document-sync')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['synced'] == 2  # Both documents synced to DB
        assert response.data['total'] == 2
        assert len(response.data['errors']) == 1  # One XML processing error
        assert response.data['errors'][0]['sunat_id'] == 'sunat-id-2'
        assert 'error' in response.data['errors'][0]
        
        # Verify both documents were created despite XML error
        assert models.Document.objects.filter(sunat_id='sunat-id-1').exists()
        assert models.Document.objects.filter(sunat_id='sunat-id-2').exists()
    
    @patch('taxes.views.requests.get')
    def test_sync_documents_api_request_failure(self, mock_get, authenticated_api_client):
        """Test sync when Sunat API request fails"""
        import requests
        
        # Mock API request failure
        mock_get.side_effect = requests.exceptions.RequestException("Connection error")
        
        url = reverse('document-sync')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        assert 'error' in response.data
        assert 'Failed to fetch documents' in response.data['error']
    
    @patch('taxes.views.requests.get')
    def test_sync_documents_invalid_response_format(self, mock_get, authenticated_api_client):
        """Test sync when Sunat API returns invalid response format"""
        mock_response = Mock()
        mock_response.json.return_value = {'error': 'Invalid format'}  # Not a list
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        url = reverse('document-sync')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        assert 'error' in response.data
        assert 'Invalid response format' in response.data['error']
    
    @patch('taxes.views.requests.get')
    @patch('taxes.views.process_sunat_document')
    def test_sync_documents_handles_exception(self, mock_process, mock_get, authenticated_api_client):
        """Test sync when processing a document raises an exception"""
        mock_sunat_documents = [
            {
                'id': 'sunat-id-1',
                'type': '03',
                'status': 'ACEPTADO',
                'fileName': '20482674828-03-B001-00000001',
                'issueTime': int(datetime.now().timestamp() * 1000),
                'xml': 'https://cdn.apisunat.com/doc/example.xml',
            },
        ]
        
        mock_response = Mock()
        mock_response.json.return_value = mock_sunat_documents
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        # Mock process_sunat_document to raise an exception
        mock_process.side_effect = Exception("Processing failed")
        
        url = reverse('document-sync')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['synced'] == 0  # No documents synced
        assert response.data['total'] == 1
        assert len(response.data['errors']) == 1  # Error recorded
        assert response.data['errors'][0]['sunat_id'] == 'sunat-id-1'
    
    @patch('taxes.views.requests.get')
    @patch('taxes.views.process_sunat_document')
    def test_sync_documents_empty_list(self, mock_process, mock_get, authenticated_api_client):
        """Test sync when Sunat API returns empty list"""
        mock_response = Mock()
        mock_response.json.return_value = []  # Empty list
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        url = reverse('document-sync')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['synced'] == 0
        assert response.data['total'] == 0
        assert len(response.data['errors']) == 0
    
    @patch('taxes.views.requests.get')
    @patch('taxes.views.process_sunat_document')
    def test_sync_documents_updates_existing(self, mock_process, mock_get, authenticated_api_client):
        """Test that sync updates existing documents instead of creating duplicates"""
        # Create existing document
        existing_doc = baker.make(
            models.Document,
            sunat_id='sunat-id-1',
            document_type='03',
            serie='B001',
            numero='00000001',
            sunat_status='PENDIENTE',
            status='pending',
            amount=Decimal('100.00'),
        )
        
        # Mock Sunat API response with same document
        mock_sunat_documents = [
            {
                'id': 'sunat-id-1',
                'type': '03',
                'status': 'ACEPTADO',  # Status changed
                'fileName': '20482674828-03-B001-00000001',
                'issueTime': int(datetime.now().timestamp() * 1000),
                'xml': 'https://cdn.apisunat.com/doc/example.xml',
                'cdr': 'https://cdn.apisunat.com/doc/example.cdr',
            },
        ]
        
        mock_response = Mock()
        mock_response.json.return_value = mock_sunat_documents
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        mock_process.return_value = {
            'amount': 118.00,
            'serie': 'B001',
            'numero': '00000001',
        }
        
        url = reverse('document-sync')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['synced'] == 1
        
        # Verify document was updated, not duplicated
        assert models.Document.objects.filter(sunat_id='sunat-id-1').count() == 1
        existing_doc.refresh_from_db()
        assert existing_doc.sunat_status == 'ACEPTADO'
        assert existing_doc.status == 'accepted'  # Status should be mapped
        assert existing_doc.amount == Decimal('118.00')  # Amount should be updated


@pytest.mark.django_db
class TestDocumentSyncTodayView:
    """Tests for GET /taxes/documents/sync-today/ - Sync today's documents from Sunat API"""
    
    def test_sync_today_documents_unauthenticated(self, api_client):
        """Test that unauthenticated requests are rejected"""
        url = reverse('document-sync-today')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    @patch('taxes.views.settings')
    def test_sync_today_documents_missing_credentials(self, mock_settings, authenticated_api_client):
        """Test sync when Sunat API credentials are not configured"""
        mock_settings.SUNAT_PERSONA_ID = None
        mock_settings.SUNAT_PERSONA_TOKEN = None
        
        url = reverse('document-sync-today')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert 'error' in response.data
        assert 'credentials' in response.data['error'].lower()
    
    @patch('taxes.views.requests.get')
    @patch('taxes.views.process_sunat_document')
    def test_sync_today_documents_filters_by_today(self, mock_process, mock_get, authenticated_api_client):
        """Test that only documents created today (based on created_at) are synced"""
        from django.utils import timezone
        now = timezone.now()
        yesterday = now - timedelta(days=1)
        
        # Create documents in DB with different created_at dates
        # Document created today - should be included
        baker.make(
            models.Document,
            sunat_id='sunat-id-today-1',
            document_type='03',
            created_at=now,
        )
        # Document created yesterday - should be excluded
        baker.make(
            models.Document,
            sunat_id='sunat-id-yesterday',
            document_type='03',
            created_at=yesterday,
        )
        # Document created today - should be included
        baker.make(
            models.Document,
            sunat_id='sunat-id-today-2',
            document_type='01',
            created_at=now,
        )
        
        # Mock Sunat API response with all documents
        mock_sunat_documents = [
            {
                'id': 'sunat-id-today-1',
                'type': '03',
                'status': 'ACEPTADO',
                'fileName': '20482674828-03-B001-00000001',
                'xml': 'https://cdn.apisunat.com/doc/today1.xml',
            },
            {
                'id': 'sunat-id-yesterday',
                'type': '03',
                'status': 'ACEPTADO',
                'fileName': '20482674828-03-B001-00000002',
                'xml': 'https://cdn.apisunat.com/doc/yesterday.xml',
            },
            {
                'id': 'sunat-id-today-2',
                'type': '01',
                'status': 'ACEPTADO',
                'fileName': '20482674828-01-F001-00000001',
                'xml': 'https://cdn.apisunat.com/doc/today2.xml',
            },
            {
                'id': 'sunat-id-new',
                'type': '03',
                'status': 'PENDIENTE',
                'fileName': '20482674828-03-B001-00000003',
                'xml': 'https://cdn.apisunat.com/doc/new.xml',
            },
        ]
        
        mock_response = Mock()
        mock_response.json.return_value = mock_sunat_documents
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        # Mock process_sunat_document
        mock_process.return_value = {
            'amount': 118.00,
            'serie': 'B001',
            'numero': '00000001',
        }
        
        url = reverse('document-sync-today')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        # Should include: 2 documents created today + 1 new document not in DB
        # Should exclude: 1 document created yesterday
        assert response.data['synced'] == 3
        assert response.data['total_today'] == 3  # 2 created today + 1 new (not in DB)
        assert response.data['total_fetched'] == 4  # All fetched from API
        
        # Verify documents were synced (including new one, excluding yesterday's)
        assert models.Document.objects.filter(sunat_id='sunat-id-today-1').exists()
        assert models.Document.objects.filter(sunat_id='sunat-id-today-2').exists()
        assert models.Document.objects.filter(sunat_id='sunat-id-new').exists()  # Included as new document
        # sunat-id-yesterday exists but was not synced (created_at is not today)
    
    @patch('taxes.views.requests.get')
    @patch('taxes.views.process_sunat_document')
    def test_sync_today_documents_includes_new_documents(self, mock_process, mock_get, authenticated_api_client):
        """Test that new documents without issueTime are included if not in DB"""
        from django.utils import timezone
        now = timezone.now()
        today_ms = int(now.timestamp() * 1000)
        
        # Mock Sunat API response with document without issueTime (new document)
        mock_sunat_documents = [
            {
                'id': 'sunat-id-new',
                'type': '03',
                'status': 'PENDIENTE',
                'fileName': '20482674828-03-B001-00000001',
                # No issueTime - should be included as new document
                'xml': 'https://cdn.apisunat.com/doc/new.xml',
            },
        ]
        
        mock_response = Mock()
        mock_response.json.return_value = mock_sunat_documents
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        mock_process.return_value = {
            'amount': 120.00,
            'serie': 'B001',
            'numero': '00000001',
        }
        
        url = reverse('document-sync-today')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['synced'] == 1
        assert response.data['total_today'] == 1  # New document included
        
        # Verify new document was created
        assert models.Document.objects.filter(sunat_id='sunat-id-new').exists()
    
    @patch('taxes.views.requests.get')
    @patch('taxes.views.process_sunat_document')
    def test_sync_today_documents_includes_existing_today_documents(self, mock_process, mock_get, authenticated_api_client):
        """Test that documents created today in DB are included for updating"""
        from django.utils import timezone
        now = timezone.now()
        
        # Create a document in DB that was created today
        existing_doc = baker.make(
            models.Document,
            sunat_id='sunat-id-existing',
            document_type='03',
            serie='B001',
            numero='00000001',
            sunat_status='PENDIENTE',
            status='pending',
            created_at=now,  # Created today
        )
        
        # Mock Sunat API response with same document
        mock_sunat_documents = [
            {
                'id': 'sunat-id-existing',
                'type': '03',
                'status': 'ACEPTADO',  # Status changed
                'fileName': '20482674828-03-B001-00000001',
                # No issueTime, but exists in DB
                'xml': 'https://cdn.apisunat.com/doc/existing.xml',
            },
        ]
        
        mock_response = Mock()
        mock_response.json.return_value = mock_sunat_documents
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        mock_process.return_value = {
            'amount': 118.00,
            'serie': 'B001',
            'numero': '00000001',
        }
        
        url = reverse('document-sync-today')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['synced'] == 1
        assert response.data['total_today'] == 1  # Existing today document included
        
        # Verify document was updated
        existing_doc.refresh_from_db()
        assert existing_doc.sunat_status == 'ACEPTADO'
    
    @patch('taxes.views.requests.get')
    @patch('taxes.views.process_sunat_document')
    def test_sync_today_documents_excludes_old_existing_documents(self, mock_process, mock_get, authenticated_api_client):
        """Test that documents not created today are excluded even if they exist"""
        from django.utils import timezone
        now = timezone.now()
        yesterday = now - timedelta(days=1)
        
        # Create a document in DB that was created yesterday
        existing_doc = baker.make(
            models.Document,
            sunat_id='sunat-id-old',
            document_type='03',
            serie='B001',
            numero='00000001',
            sunat_status='PENDIENTE',
            status='pending',
            created_at=yesterday,  # Created yesterday
        )
        
        # Mock Sunat API response
        mock_sunat_documents = [
            {
                'id': 'sunat-id-old',
                'type': '03',
                'status': 'ACEPTADO',
                'fileName': '20482674828-03-B001-00000001',
                # No issueTime and not created today - should be excluded
                'xml': 'https://cdn.apisunat.com/doc/old.xml',
            },
        ]
        
        mock_response = Mock()
        mock_response.json.return_value = mock_sunat_documents
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        url = reverse('document-sync-today')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['synced'] == 0
        assert response.data['total_today'] == 0  # No documents from today
    
    @patch('taxes.views.requests.get')
    def test_sync_today_documents_api_failure(self, mock_get, authenticated_api_client):
        """Test sync when Sunat API request fails"""
        import requests
        
        mock_get.side_effect = requests.exceptions.RequestException("Connection error")
        
        url = reverse('document-sync-today')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        assert 'error' in response.data
        assert 'Failed to fetch documents' in response.data['error']
    
    @patch('taxes.views.requests.get')
    def test_sync_today_documents_empty_list(self, mock_get, authenticated_api_client):
        """Test sync when Sunat API returns empty list"""
        mock_response = Mock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        url = reverse('document-sync-today')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['synced'] == 0
        assert response.data['total_today'] == 0
        assert response.data['total_fetched'] == 0
    
    @patch('taxes.views.requests.get')
    @patch('taxes.views.process_sunat_document')
    def test_sync_today_documents_mixed_scenario(self, mock_process, mock_get, authenticated_api_client):
        """Test sync with mixed scenario: documents created today, yesterday, and new docs"""
        from django.utils import timezone
        now = timezone.now()
        yesterday = now - timedelta(days=1)
        
        # Create existing document from today - should be included
        existing_today_doc = baker.make(
            models.Document,
            sunat_id='sunat-id-existing-today',
            document_type='01',
            created_at=now,
        )
        
        # Create existing document from yesterday - should be excluded
        baker.make(
            models.Document,
            sunat_id='sunat-id-yesterday',
            document_type='03',
            created_at=yesterday,
        )
        
        # Mock Sunat API response
        mock_sunat_documents = [
            {
                'id': 'sunat-id-new',
                'type': '03',
                'status': 'PENDIENTE',
                'fileName': '20482674828-03-B001-00000001',
                # Not in DB - should be included as new
                'xml': 'https://cdn.apisunat.com/doc/new.xml',
            },
            {
                'id': 'sunat-id-existing-today',
                'type': '01',
                'status': 'ACEPTADO',
                'fileName': '20482674828-01-F001-00000001',
                # Exists in DB and created today - should be included
                'xml': 'https://cdn.apisunat.com/doc/existing.xml',
            },
            {
                'id': 'sunat-id-yesterday',
                'type': '03',
                'status': 'ACEPTADO',
                'fileName': '20482674828-03-B001-00000002',
                # Exists in DB but created yesterday - should be excluded
                'xml': 'https://cdn.apisunat.com/doc/yesterday.xml',
            },
        ]
        
        mock_response = Mock()
        mock_response.json.return_value = mock_sunat_documents
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        mock_process.return_value = {
            'amount': 118.00,
            'serie': 'B001',
            'numero': '00000001',
        }
        
        url = reverse('document-sync-today')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['total_fetched'] == 3
        # Should include: 1 existing today doc + 1 new doc
        # Should exclude: 1 doc created yesterday
        assert response.data['total_today'] == 2  # 1 existing today + 1 new
        assert response.data['synced'] == 2
        
        # Verify correct documents were synced
        assert models.Document.objects.filter(sunat_id='sunat-id-new').exists()
        assert models.Document.objects.filter(sunat_id='sunat-id-existing-today').exists()
        # sunat-id-yesterday exists but was not synced (created_at is not today)
