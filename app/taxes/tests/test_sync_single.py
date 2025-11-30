import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import patch, Mock
from model_bakery import baker
from rest_framework import status
from django.urls import reverse
from django.conf import settings

from taxes import models


@pytest.mark.django_db
class TestDocumentSyncSingleView:
    """Tests for GET /taxes/documents/sync-single/ - Sync a single document by sunat_id or document_id"""
    
    def test_sync_single_unauthenticated(self, api_client):
        """Test that unauthenticated requests are rejected"""
        url = reverse('document-sync-single')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_sync_single_missing_both_parameters(self, authenticated_api_client):
        """Test sync when neither sunat_id nor document_id is provided"""
        url = reverse('document-sync-single')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data
        assert 'sunat_id' in response.data['error'].lower() or 'document_id' in response.data['error'].lower()
    
    def test_sync_single_document_id_not_found(self, authenticated_api_client):
        """Test sync when document_id is provided but document doesn't exist in database"""
        url = reverse('document-sync-single')
        response = authenticated_api_client.get(url, {'document_id': '00000000-0000-0000-0000-000000000000'})
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert 'error' in response.data
        assert 'not found' in response.data['error'].lower()
    
    def test_sync_single_document_id_no_sunat_id(self, authenticated_api_client):
        """Test sync when document_id is provided but document doesn't have sunat_id"""
        # Create a document without sunat_id
        doc = baker.make(
            models.Document,
            sunat_id=None,
            serie='B001',
            numero='00000001',
            document_type='03',
        )
        
        url = reverse('document-sync-single')
        response = authenticated_api_client.get(url, {'document_id': str(doc.id)})
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data
        assert 'sunat_id' in response.data['error'].lower()
    
    @patch('taxes.views.settings')
    def test_sync_single_missing_credentials(self, mock_settings, authenticated_api_client):
        """Test sync when Sunat API credentials are not configured"""
        mock_settings.SUNAT_PERSONA_ID = None
        mock_settings.SUNAT_PERSONA_TOKEN = None
        mock_settings.SUNAT_API_URL = "http://mock.sunat.api"
        
        url = reverse('document-sync-single')
        response = authenticated_api_client.get(url, {'sunat_id': 'test-sunat-id'})
        
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert 'error' in response.data
        assert 'credentials' in response.data['error'].lower()
    
    @patch('taxes.views.requests.get')
    def test_sync_single_document_not_found_in_sunat(self, mock_get, authenticated_api_client):
        """Test sync when document doesn't exist in Sunat API (404)"""
        sunat_id = 'non-existent-sunat-id'
        
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = 'Not Found'
        mock_get.return_value = mock_response
        
        url = reverse('document-sync-single')
        response = authenticated_api_client.get(url, {'sunat_id': sunat_id})
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert 'error' in response.data
        assert 'not found' in response.data['error'].lower()
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert 'getById' in call_args[0][0]
        assert sunat_id in call_args[0][0]
    
    @patch('taxes.views.requests.get')
    def test_sync_single_document_exists_in_db_not_in_sunat(self, mock_get, authenticated_api_client):
        """Test sync when document exists in DB but not in Sunat API"""
        # Create document in database
        db_doc = baker.make(
            models.Document,
            sunat_id='test-sunat-id-404',
            serie='B001',
            numero='00000001',
            document_type='03',
            amount=Decimal('50.00'),
        )
        
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = 'Not Found'
        mock_get.return_value = mock_response
        
        url = reverse('document-sync-single')
        response = authenticated_api_client.get(url, {'sunat_id': db_doc.sunat_id})
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert 'error' in response.data
        assert db_doc.serie in response.data['error']
        assert db_doc.numero in response.data['error']
        assert 'document' in response.data
        assert response.data['document']['serie'] == db_doc.serie
    
    @patch('taxes.views.requests.get')
    @patch('taxes.views.process_sunat_document')
    def test_sync_single_success_by_sunat_id(self, mock_process, mock_get, authenticated_api_client):
        """Test successful sync using sunat_id"""
        sunat_id = 'test-sunat-id-success'
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'id': sunat_id,
            'type': '03',
            'status': 'ACEPTADO',
            'fileName': '20482674828-03-B001-00000001',
            'issueTime': int(datetime.now().timestamp() * 1000),
            'xml': 'https://cdn.apisunat.com/doc/example.xml',
            'cdr': 'https://cdn.apisunat.com/doc/example.cdr',
        }
        mock_get.return_value = mock_response
        
        mock_process.return_value = {
            'amount': 118.00,
            'serie': 'B001',
            'numero': '00000001',
        }
        
        url = reverse('document-sync-single')
        response = authenticated_api_client.get(url, {'sunat_id': sunat_id})
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['synced'] == 1
        assert response.data['sunat_id'] == sunat_id
        assert 'document' in response.data
        assert response.data['document']['sunat_id'] == sunat_id
        assert response.data['document']['serie'] == 'B001'
        assert response.data['document']['numero'] == '00000001'
        
        # Verify document was created/updated in database
        assert models.Document.objects.filter(sunat_id=sunat_id).exists()
        document = models.Document.objects.get(sunat_id=sunat_id)
        assert document.serie == 'B001'
        assert document.numero == '00000001'
        
        # Verify API was called with correct endpoint
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert 'getById' in call_args[0][0]
        assert sunat_id in call_args[0][0]
        assert call_args[1]['params']['personaId'] == settings.SUNAT_PERSONA_ID
        assert call_args[1]['params']['personaToken'] == settings.SUNAT_PERSONA_TOKEN
    
    @patch('taxes.views.requests.get')
    @patch('taxes.views.process_sunat_document')
    def test_sync_single_success_by_document_id(self, mock_process, mock_get, authenticated_api_client):
        """Test successful sync using document_id (local DB ID)"""
        # Create document in database
        db_doc = baker.make(
            models.Document,
            sunat_id='test-sunat-id-from-doc-id',
            serie='B001',
            numero='00000002',
            document_type='03',
        )
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'id': db_doc.sunat_id,
            'type': '03',
            'status': 'ACEPTADO',
            'fileName': '20482674828-03-B001-00000002',
            'issueTime': int(datetime.now().timestamp() * 1000),
            'xml': 'https://cdn.apisunat.com/doc/example.xml',
        }
        mock_get.return_value = mock_response
        
        mock_process.return_value = {
            'amount': 120.00,
            'serie': 'B001',
            'numero': '00000002',
        }
        
        url = reverse('document-sync-single')
        response = authenticated_api_client.get(url, {'document_id': str(db_doc.id)})
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['synced'] == 1
        assert response.data['sunat_id'] == db_doc.sunat_id
        assert 'document' in response.data
        
        # Verify API was called with correct sunat_id (from document lookup)
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert db_doc.sunat_id in call_args[0][0]
    
    @patch('taxes.views.requests.get')
    @patch('taxes.views.process_sunat_document')
    def test_sync_single_updates_existing_document(self, mock_process, mock_get, authenticated_api_client):
        """Test that sync updates existing document in database"""
        # Create existing document
        existing_doc = baker.make(
            models.Document,
            sunat_id='test-sunat-id-update',
            serie='B001',
            numero='00000003',
            document_type='03',
            sunat_status='PENDIENTE',
            status='pending',
            amount=Decimal('100.00'),
        )
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'id': existing_doc.sunat_id,
            'type': '03',
            'status': 'ACEPTADO',  # Status changed
            'fileName': '20482674828-03-B001-00000003',
            'issueTime': int(datetime.now().timestamp() * 1000),
            'xml': 'https://cdn.apisunat.com/doc/example.xml',
        }
        mock_get.return_value = mock_response
        
        mock_process.return_value = {
            'amount': 118.00,
            'serie': 'B001',
            'numero': '00000003',
        }
        
        url = reverse('document-sync-single')
        response = authenticated_api_client.get(url, {'sunat_id': existing_doc.sunat_id})
        
        assert response.status_code == status.HTTP_200_OK
        
        # Verify document was updated
        existing_doc.refresh_from_db()
        assert existing_doc.sunat_status == 'ACEPTADO'
        assert existing_doc.status == 'accepted'
        assert existing_doc.amount == Decimal('118.00')
    
    @patch('taxes.views.requests.get')
    def test_sync_single_invalid_response_format(self, mock_get, authenticated_api_client):
        """Test sync when Sunat API returns invalid response format"""
        sunat_id = 'test-sunat-id-invalid'
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = 'invalid format'  # Not a dict
        mock_get.return_value = mock_response
        
        url = reverse('document-sync-single')
        response = authenticated_api_client.get(url, {'sunat_id': sunat_id})
        
        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        assert 'error' in response.data
        assert 'Invalid response format' in response.data['error']
    
    @patch('taxes.views.requests.get')
    @patch('taxes.views.process_sunat_document')
    def test_sync_single_with_xml_error(self, mock_process, mock_get, authenticated_api_client):
        """Test sync when XML processing fails but document still gets synced"""
        sunat_id = 'test-sunat-id-xml-error'
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'id': sunat_id,
            'type': '03',
            'status': 'ACEPTADO',
            'fileName': '20482674828-03-B001-00000004',
            'xml': 'https://cdn.apisunat.com/doc/invalid.xml',
        }
        mock_get.return_value = mock_response
        
        mock_process.return_value = {
            'error': 'Failed to download XML'
        }
        
        url = reverse('document-sync-single')
        response = authenticated_api_client.get(url, {'sunat_id': sunat_id})
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['synced'] == 1
        assert len(response.data['errors']) > 0
        assert 'error' in response.data['errors'][0]
        
        # Document should still be created even with XML error
        assert models.Document.objects.filter(sunat_id=sunat_id).exists()
    
    @patch('taxes.views.requests.get')
    def test_sync_single_network_error(self, mock_get, authenticated_api_client):
        """Test sync when network error occurs"""
        sunat_id = 'test-sunat-id-network-error'
        
        import requests
        mock_get.side_effect = requests.exceptions.RequestException("Connection error")
        
        url = reverse('document-sync-single')
        response = authenticated_api_client.get(url, {'sunat_id': sunat_id})
        
        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        assert 'error' in response.data
        assert 'Failed to fetch' in response.data['error']
    
    @patch('taxes.views.requests.get')
    @patch('taxes.views.process_sunat_document')
    def test_sync_single_verifies_endpoint_format(self, mock_process, mock_get, authenticated_api_client):
        """Test that the correct endpoint format is used"""
        sunat_id = 'test-sunat-id-endpoint'
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'id': sunat_id,
            'type': '01',
            'status': 'ACEPTADO',
            'fileName': '20482674828-01-F001-00000001',
            'xml': 'https://cdn.apisunat.com/doc/example.xml',
        }
        mock_get.return_value = mock_response
        
        mock_process.return_value = {
            'amount': 118.00,
            'serie': 'F001',
            'numero': '00000001',
        }
        
        url = reverse('document-sync-single')
        response = authenticated_api_client.get(url, {'sunat_id': sunat_id})
        
        assert response.status_code == status.HTTP_200_OK
        
        # Verify endpoint format
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        endpoint = call_args[0][0]
        
        # Should be: {base_url}/{sunat_id}/getById
        assert sunat_id in endpoint
        assert 'getById' in endpoint
        assert endpoint.endswith(f'/{sunat_id}/getById') or f'/{sunat_id}/getById' in endpoint

