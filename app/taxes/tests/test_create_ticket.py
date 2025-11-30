import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import patch, Mock, MagicMock
from model_bakery import baker
from rest_framework import status
from django.urls import reverse
from django.conf import settings

from taxes import models
from store import models as store_models


@pytest.mark.django_db
class TestDocumentCreateTicketView:
    """Tests for POST /taxes/documents/create-ticket/ - Create ticket in Sunat"""
    
    def test_create_ticket_unauthenticated(self, api_client):
        """Test that unauthenticated requests are rejected"""
        url = reverse('document-create-ticket')
        response = api_client.post(url, {})
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_create_ticket_invalid_data(self, authenticated_api_client):
        """Test ticket creation with invalid data"""
        url = reverse('document-create-ticket')
        response = authenticated_api_client.post(url, {}, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'order_items' in response.data
    
    def test_create_ticket_missing_credentials(self, authenticated_api_client):
        """Test ticket creation when Sunat API credentials are not configured"""
        with patch('taxes.views.settings') as mock_settings:
            mock_settings.SUNAT_PERSONA_ID = None
            mock_settings.SUNAT_PERSONA_TOKEN = None
            
            url = reverse('document-create-ticket')
            response = authenticated_api_client.post(
                url,
                {
                    'order_items': [
                        {'id': '1', 'name': 'Producto 1', 'quantity': 2, 'cost': 50.00}
                    ]
                },
                format='json'
            )
            
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert 'error' in response.data
            assert 'credentials' in response.data['error'].lower()
    
    @patch('taxes.views.get_correlative')
    def test_create_ticket_failed_to_get_correlative(self, mock_get_correlative, authenticated_api_client):
        """Test ticket creation when getting correlative fails"""
        mock_get_correlative.return_value = None
        
        url = reverse('document-create-ticket')
        response = authenticated_api_client.post(
            url,
            {
                'order_items': [
                    {'id': '1', 'name': 'Producto 1', 'quantity': 2, 'cost': 50.00}
                ]
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        assert 'error' in response.data
        assert 'correlative' in response.data['error'].lower()
    
    @patch('taxes.views.requests.post')
    @patch('taxes.views.get_correlative')
    def test_create_ticket_sunat_api_error(self, mock_get_correlative, mock_post, authenticated_api_client):
        """Test ticket creation when Sunat API returns an error"""
        mock_get_correlative.return_value = '00000001'
        
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = 'Not Found'
        mock_post.return_value = mock_response
        
        url = reverse('document-create-ticket')
        response = authenticated_api_client.post(
            url,
            {
                'order_items': [
                    {'id': '1', 'name': 'Producto 1', 'quantity': 2, 'cost': 50.00}
                ]
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        assert 'error' in response.data
        assert 'Failed to create ticket' in response.data['error']
    
    @patch('taxes.views.requests.post')
    @patch('taxes.views.get_correlative')
    def test_create_ticket_sunat_error_status(self, mock_get_correlative, mock_post, authenticated_api_client):
        """Test ticket creation when Sunat API returns error status"""
        mock_get_correlative.return_value = '00000001'
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'status': 'ERROR',
            'error': {'message': 'Invalid data'}
        }
        mock_post.return_value = mock_response
        
        url = reverse('document-create-ticket')
        response = authenticated_api_client.post(
            url,
            {
                'order_items': [
                    {'id': '1', 'name': 'Producto 1', 'quantity': 2, 'cost': 50.00}
                ]
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data
        assert 'Sunat API returned an error' in response.data['error']
    
    @patch('taxes.views.time.sleep')
    @patch('taxes.views.process_and_sync_documents')
    @patch('taxes.views.requests.get')
    @patch('taxes.views.requests.post')
    @patch('taxes.views.get_correlative')
    def test_create_ticket_success_without_order_id(self, mock_get_correlative, mock_post, mock_get, mock_sync, mock_sleep, authenticated_api_client):
        """Test successful ticket creation without order_id and sync succeeds with ACEPTADO"""
        mock_get_correlative.return_value = '00000001'
        
        # Mock POST response (create ticket)
        mock_post_response = Mock()
        mock_post_response.status_code = 200
        mock_post_response.json.return_value = {
            'documentId': 'test-ticket-id-123',
            'status': 'OK'
        }
        mock_post.return_value = mock_post_response
        
        # Mock GET response (sync - document is accepted)
        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {
            'id': 'test-ticket-id-123',
            'type': '03',
            'status': 'ACEPTADO',
            'fileName': '20482674828-03-B001-00000001',
            'issueTime': int(datetime.now().timestamp() * 1000),
            'xml': 'https://cdn.apisunat.com/doc/example.xml',
            'cdr': 'https://cdn.apisunat.com/doc/example.cdr',
        }
        mock_get.return_value = mock_get_response
        
        # Mock sync process
        mock_sync.return_value = (1, [])  # synced_count, errors
        
        url = reverse('document-create-ticket')
        response = authenticated_api_client.post(
            url,
            {
                'order_items': [
                    {'id': '1', 'name': 'Producto 1', 'quantity': 2, 'cost': 50.00}
                ]
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        assert 'id' in response.data
        assert response.data['document_type'] == '03'
        assert response.data['serie'] == 'B001'
        assert response.data['numero'] == '00000001'
        assert response.data['sunat_id'] == 'test-ticket-id-123'
        
        # Verify document was created in database
        document = models.Document.objects.get(sunat_id='test-ticket-id-123')
        assert document.document_type == '03'
        assert document.serie == 'B001'
        assert document.numero == '00000001'
        
        # Verify sync was called (GET request for sync)
        mock_get.assert_called()
    
    @patch('taxes.views.time.sleep')
    @patch('taxes.views.process_and_sync_documents')
    @patch('taxes.views.requests.get')
    @patch('taxes.views.requests.post')
    @patch('taxes.views.get_correlative')
    def test_create_ticket_success_with_order_id(self, mock_get_correlative, mock_post, mock_get, mock_sync, mock_sleep, authenticated_api_client):
        """Test successful ticket creation with order_id and sync succeeds"""
        mock_get_correlative.return_value = '00000002'
        
        # Create an order
        order = baker.make(store_models.Order)
        
        # Mock POST response (create ticket)
        mock_post_response = Mock()
        mock_post_response.status_code = 200
        mock_post_response.json.return_value = {
            'documentId': 'test-ticket-id-456',
            'status': 'OK'
        }
        mock_post.return_value = mock_post_response
        
        # Mock GET response (sync - document is accepted)
        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {
            'id': 'test-ticket-id-456',
            'type': '03',
            'status': 'ACEPTADO',
            'fileName': '20482674828-03-B001-00000002',
            'issueTime': int(datetime.now().timestamp() * 1000),
        }
        mock_get.return_value = mock_get_response
        
        # Mock sync process
        mock_sync.return_value = (1, [])  # synced_count, errors
        
        url = reverse('document-create-ticket')
        response = authenticated_api_client.post(
            url,
            {
                'order_items': [
                    {'id': '1', 'name': 'Producto 1', 'quantity': 2, 'cost': 60.00}
                ],
                'order_id': order.id
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['amount'] == '120.00'
        
        # Verify document was created in database
        document = models.Document.objects.get(sunat_id='test-ticket-id-456')
        assert document.amount == Decimal('120.00')
        
        # Verify order was updated with document
        order.refresh_from_db()
        assert order.document == document
    
    @patch('taxes.views.time.sleep')
    @patch('taxes.views.process_and_sync_documents')
    @patch('taxes.views.requests.get')
    @patch('taxes.views.requests.post')
    @patch('taxes.views.get_correlative')
    def test_create_ticket_order_not_found(self, mock_get_correlative, mock_post, mock_get, mock_sync, mock_sleep, authenticated_api_client):
        """Test ticket creation when order_id is provided but order doesn't exist"""
        mock_get_correlative.return_value = '00000003'
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'documentId': 'test-ticket-id-789',
            'status': 'OK'
        }
        mock_post.return_value = mock_response
        
        # Mock sync - document accepted
        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {
            'id': 'test-ticket-id-789',
            'type': '03',
            'status': 'ACEPTADO',
            'fileName': '20482674828-03-B001-00000003',
        }
        mock_get.return_value = mock_get_response
        mock_sync.return_value = (1, [])
        
        url = reverse('document-create-ticket')
        response = authenticated_api_client.post(
            url,
            {
                'order_items': [
                    {'id': '1', 'name': 'Producto 1', 'quantity': 1, 'cost': 100.00}
                ],
                'order_id': 99999  # Non-existent order ID
            },
            format='json'
        )
        
        # Should still succeed - document created but order not linked
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['sunat_id'] == 'test-ticket-id-789'
        
        # Verify document was created
        assert models.Document.objects.filter(sunat_id='test-ticket-id-789').exists()
    
    @patch('taxes.views.requests.post')
    @patch('taxes.views.get_correlative')
    def test_create_ticket_network_error(self, mock_get_correlative, mock_post, authenticated_api_client):
        """Test ticket creation when network error occurs"""
        mock_get_correlative.return_value = '00000004'
        
        import requests
        mock_post.side_effect = requests.exceptions.RequestException("Connection error")
        
        url = reverse('document-create-ticket')
        response = authenticated_api_client.post(
            url,
            {
                'order_items': [
                    {'id': '1', 'name': 'Producto 1', 'quantity': 1, 'cost': 50.00}
                ]
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        assert 'error' in response.data
        assert 'Failed to create ticket' in response.data['error']
    
    @patch('taxes.views.time.sleep')
    @patch('taxes.views.process_and_sync_documents')
    @patch('taxes.views.requests.get')
    @patch('taxes.views.requests.post')
    @patch('taxes.views.get_correlative')
    def test_create_ticket_multiple_items(self, mock_get_correlative, mock_post, mock_get, mock_sync, mock_sleep, authenticated_api_client):
        """Test ticket creation with multiple order items"""
        mock_get_correlative.return_value = '00000005'
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'documentId': 'test-ticket-id-multi',
            'status': 'OK'
        }
        mock_post.return_value = mock_response
        
        # Mock sync - document accepted
        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {
            'id': 'test-ticket-id-multi',
            'type': '03',
            'status': 'ACEPTADO',
            'fileName': '20482674828-03-B001-00000005',
        }
        mock_get.return_value = mock_get_response
        mock_sync.return_value = (1, [])
        
        url = reverse('document-create-ticket')
        response = authenticated_api_client.post(
            url,
            {
                'order_items': [
                    {'id': '1', 'name': 'Producto 1', 'quantity': 2, 'cost': 60.00},
                    {'id': '2', 'name': 'Producto 2', 'quantity': 1, 'cost': 30.00}
                ]
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        # Total: 2 * 60 + 1 * 30 = 120 + 30 = 150
        assert response.data['amount'] == '150.00'
        
        document = models.Document.objects.get(sunat_id='test-ticket-id-multi')
        assert document.amount == Decimal('150.00')
    
    @patch('taxes.views.time.sleep')
    @patch('taxes.views.process_and_sync_documents')
    @patch('taxes.views.requests.get')
    @patch('taxes.views.requests.post')
    @patch('taxes.views.get_correlative')
    def test_create_ticket_verifies_sunat_api_call(self, mock_get_correlative, mock_post, mock_get, mock_sync, mock_sleep, authenticated_api_client):
        """Test that the correct data is sent to Sunat API"""
        mock_get_correlative.return_value = '00000006'
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'documentId': 'test-ticket-id-verify',
            'status': 'OK'
        }
        mock_post.return_value = mock_response
        
        # Mock sync - document accepted
        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {
            'id': 'test-ticket-id-verify',
            'type': '03',
            'status': 'ACEPTADO',
            'fileName': '20482674828-03-B001-00000006',
        }
        mock_get.return_value = mock_get_response
        mock_sync.return_value = (1, [])
        
        url = reverse('document-create-ticket')
        response = authenticated_api_client.post(
            url,
            {
                'order_items': [
                    {'id': '1', 'name': 'Producto 1', 'quantity': 1, 'cost': 50.00}
                ]
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        
        # Verify API was called with correct endpoint
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert 'sendBill' in call_args[0][0] or 'sendBill' in str(call_args[0][0])
        
        # Verify request data structure
        assert 'json' in call_args[1]
        ticket_data = call_args[1]['json']
        assert 'fileName' in ticket_data
        assert ticket_data['fileName'] == '20482674828-03-B001-00000006'
    
    @patch('taxes.views.time.sleep')
    @patch('taxes.views.process_and_sync_documents')
    @patch('taxes.views.requests.get')
    @patch('taxes.views.requests.post')
    @patch('taxes.views.get_correlative')
    def test_create_ticket_uses_ticket_type(self, mock_get_correlative, mock_post, mock_get, mock_sync, mock_sleep, authenticated_api_client):
        """Test that get_correlative is called with 'T' for ticket"""
        mock_get_correlative.return_value = '00000007'
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'documentId': 'test-ticket-id-type',
            'status': 'OK'
        }
        mock_post.return_value = mock_response
        
        # Mock sync - document accepted
        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {
            'id': 'test-ticket-id-type',
            'type': '03',
            'status': 'ACEPTADO',
            'fileName': '20482674828-03-B001-00000007',
        }
        mock_get.return_value = mock_get_response
        mock_sync.return_value = (1, [])
        
        url = reverse('document-create-ticket')
        response = authenticated_api_client.post(
            url,
            {
                'order_items': [
                    {'id': '1', 'name': 'Producto 1', 'quantity': 1, 'cost': 50.00}
                ]
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        
        # Verify get_correlative was called with 'T' for ticket
        mock_get_correlative.assert_called_once_with('T')
    
    @patch('taxes.views.time.sleep')
    @patch('taxes.views.process_and_sync_documents')
    @patch('taxes.views.requests.get')
    @patch('taxes.views.requests.post')
    @patch('taxes.views.get_correlative')
    def test_create_ticket_sync_retries_until_aceptado(self, mock_get_correlative, mock_post, mock_get, mock_sync, mock_sleep, authenticated_api_client):
        """Test that sync retries until status is ACEPTADO"""
        mock_get_correlative.return_value = '00000008'
        
        # Mock POST response (create ticket)
        mock_post_response = Mock()
        mock_post_response.status_code = 200
        mock_post_response.json.return_value = {
            'documentId': 'test-ticket-retry',
            'status': 'OK'
        }
        mock_post.return_value = mock_post_response
        
        # Mock GET responses - first PENDIENTE, then ACEPTADO
        mock_get_responses = [
            Mock(status_code=200, json=lambda: {
                'id': 'test-ticket-retry',
                'type': '03',
                'status': 'PENDIENTE',
                'fileName': '20482674828-03-B001-00000008',
            }),
            Mock(status_code=200, json=lambda: {
                'id': 'test-ticket-retry',
                'type': '03',
                'status': 'ACEPTADO',
                'fileName': '20482674828-03-B001-00000008',
                'issueTime': int(datetime.now().timestamp() * 1000),
                'xml': 'https://cdn.apisunat.com/doc/example.xml',
                'cdr': 'https://cdn.apisunat.com/doc/example.cdr',
            }),
        ]
        mock_get.side_effect = mock_get_responses
        
        # Mock sync process (returns synced for both attempts)
        mock_sync.return_value = (1, [])  # synced_count, errors
        
        url = reverse('document-create-ticket')
        response = authenticated_api_client.post(
            url,
            {
                'order_items': [
                    {'id': '1', 'name': 'Producto 1', 'quantity': 1, 'cost': 50.00}
                ]
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        
        # Verify GET was called multiple times (retry logic)
        assert mock_get.call_count >= 2
        
        # Verify sleep was called between retries
        mock_sleep.assert_called()
    
    @patch('taxes.views.time.sleep')
    @patch('taxes.views.process_and_sync_documents')
    @patch('taxes.views.requests.get')
    @patch('taxes.views.requests.post')
    @patch('taxes.views.get_correlative')
    def test_create_ticket_sync_stops_on_rechazado(self, mock_get_correlative, mock_post, mock_get, mock_sync, mock_sleep, authenticated_api_client):
        """Test that sync stops when status is RECHAZADO"""
        mock_get_correlative.return_value = '00000009'
        
        # Mock POST response (create ticket)
        mock_post_response = Mock()
        mock_post_response.status_code = 200
        mock_post_response.json.return_value = {
            'documentId': 'test-ticket-rejected',
            'status': 'OK'
        }
        mock_post.return_value = mock_post_response
        
        # Mock GET response - document is rejected
        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {
            'id': 'test-ticket-rejected',
            'type': '03',
            'status': 'RECHAZADO',
            'fileName': '20482674828-03-B001-00000009',
        }
        mock_get.return_value = mock_get_response
        
        # Mock sync process
        mock_sync.return_value = (1, [])  # synced_count, errors
        
        url = reverse('document-create-ticket')
        response = authenticated_api_client.post(
            url,
            {
                'order_items': [
                    {'id': '1', 'name': 'Producto 1', 'quantity': 1, 'cost': 50.00}
                ]
            },
            format='json'
        )
        
        # Should still return 201 (document created, just not accepted)
        assert response.status_code == status.HTTP_201_CREATED
        
        # Verify GET was called (sync attempted)
        mock_get.assert_called()
        
        # Verify document exists in database
        assert models.Document.objects.filter(sunat_id='test-ticket-rejected').exists()
    
    @patch('taxes.views.time.sleep')
    @patch('taxes.views.process_and_sync_documents')
    @patch('taxes.views.requests.get')
    @patch('taxes.views.requests.post')
    @patch('taxes.views.get_correlative')
    def test_create_ticket_sync_handles_404(self, mock_get_correlative, mock_post, mock_get, mock_sync, mock_sleep, authenticated_api_client):
        """Test that sync handles 404 (document not found yet) and retries"""
        mock_get_correlative.return_value = '00000010'
        
        # Mock POST response (create ticket)
        mock_post_response = Mock()
        mock_post_response.status_code = 200
        mock_post_response.json.return_value = {
            'documentId': 'test-ticket-404',
            'status': 'OK'
        }
        mock_post.return_value = mock_post_response
        
        # Mock GET responses - first 404, then found with ACEPTADO
        mock_get_responses = [
            Mock(status_code=404, json=lambda: {}),
            Mock(status_code=200, json=lambda: {
                'id': 'test-ticket-404',
                'type': '03',
                'status': 'ACEPTADO',
                'fileName': '20482674828-03-B001-00000010',
                'issueTime': int(datetime.now().timestamp() * 1000),
            }),
        ]
        mock_get.side_effect = mock_get_responses
        
        # Mock sync process
        mock_sync.return_value = (1, [])  # synced_count, errors
        
        url = reverse('document-create-ticket')
        response = authenticated_api_client.post(
            url,
            {
                'order_items': [
                    {'id': '1', 'name': 'Producto 1', 'quantity': 1, 'cost': 50.00}
                ]
            },
            format='json'
        )
        
        # Should still succeed (document created, sync may fail but that's ok)
        assert response.status_code == status.HTTP_201_CREATED
        
        # Verify GET was called multiple times (retry after 404)
        assert mock_get.call_count >= 2

