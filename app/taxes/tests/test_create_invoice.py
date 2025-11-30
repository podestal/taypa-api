import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import patch, Mock
from model_bakery import baker
from rest_framework import status
from django.urls import reverse
from django.conf import settings

from taxes import models
from store import models as store_models


@pytest.mark.django_db
class TestDocumentCreateInvoiceView:
    """Tests for POST /taxes/documents/create-invoice/ - Create invoice in Sunat"""
    
    def test_create_invoice_unauthenticated(self, api_client):
        """Test that unauthenticated requests are rejected"""
        url = reverse('document-create-invoice')
        response = api_client.post(url, {})
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_create_invoice_invalid_data(self, authenticated_api_client):
        """Test invoice creation with invalid data"""
        url = reverse('document-create-invoice')
        response = authenticated_api_client.post(url, {}, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'order_items' in response.data or 'ruc' in response.data
    
    def test_create_invoice_missing_credentials(self, authenticated_api_client):
        """Test invoice creation when Sunat API credentials are not configured"""
        with patch('taxes.views.settings') as mock_settings:
            mock_settings.SUNAT_PERSONA_ID = None
            mock_settings.SUNAT_PERSONA_TOKEN = None
            
            url = reverse('document-create-invoice')
            response = authenticated_api_client.post(
                url,
                {
                    'order_items': [
                        {'id': '1', 'name': 'Producto 1', 'quantity': 2, 'cost': 50.00}
                    ],
                    'ruc': '20123456789',
                    'razon_social': 'Empresa S.A.C.',
                    'address': 'Av. Principal 123'
                },
                format='json'
            )
            
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert 'error' in response.data
            assert 'credentials' in response.data['error'].lower()
    
    @patch('taxes.views.get_correlative')
    def test_create_invoice_failed_to_get_correlative(self, mock_get_correlative, authenticated_api_client):
        """Test invoice creation when getting correlative fails"""
        mock_get_correlative.return_value = None
        
        url = reverse('document-create-invoice')
        response = authenticated_api_client.post(
            url,
            {
                'order_items': [
                    {'id': '1', 'name': 'Producto 1', 'quantity': 2, 'cost': 50.00}
                ],
                'ruc': '20123456789',
                'razon_social': 'Empresa S.A.C.',
                'address': 'Av. Principal 123'
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        assert 'error' in response.data
        assert 'correlative' in response.data['error'].lower()
    
    @patch('taxes.views.requests.post')
    @patch('taxes.views.get_correlative')
    def test_create_invoice_sunat_api_error(self, mock_get_correlative, mock_post, authenticated_api_client):
        """Test invoice creation when Sunat API returns an error"""
        mock_get_correlative.return_value = '00000001'
        
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = 'Not Found'
        mock_post.return_value = mock_response
        
        url = reverse('document-create-invoice')
        response = authenticated_api_client.post(
            url,
            {
                'order_items': [
                    {'id': '1', 'name': 'Producto 1', 'quantity': 2, 'cost': 50.00}
                ],
                'ruc': '20123456789',
                'razon_social': 'Empresa S.A.C.',
                'address': 'Av. Principal 123'
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        assert 'error' in response.data
        assert 'Failed to create invoice' in response.data['error']
    
    @patch('taxes.views.requests.post')
    @patch('taxes.views.get_correlative')
    def test_create_invoice_sunat_error_status(self, mock_get_correlative, mock_post, authenticated_api_client):
        """Test invoice creation when Sunat API returns error status"""
        mock_get_correlative.return_value = '00000001'
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'status': 'ERROR',
            'error': {'message': 'Invalid data'}
        }
        mock_post.return_value = mock_response
        
        url = reverse('document-create-invoice')
        response = authenticated_api_client.post(
            url,
            {
                'order_items': [
                    {'id': '1', 'name': 'Producto 1', 'quantity': 2, 'cost': 50.00}
                ],
                'ruc': '20123456789',
                'razon_social': 'Empresa S.A.C.',
                'address': 'Av. Principal 123'
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data
        assert 'Sunat API returned an error' in response.data['error']
    
    @patch('taxes.views.requests.post')
    @patch('taxes.views.get_correlative')
    def test_create_invoice_success_without_order_id(self, mock_get_correlative, mock_post, authenticated_api_client):
        """Test successful invoice creation without order_id"""
        mock_get_correlative.return_value = '00000001'
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'documentId': 'test-document-id-123',
            'status': 'OK'
        }
        mock_post.return_value = mock_response
        
        url = reverse('document-create-invoice')
        response = authenticated_api_client.post(
            url,
            {
                'order_items': [
                    {'id': '1', 'name': 'Producto 1', 'quantity': 2, 'cost': 50.00}
                ],
                'ruc': '20123456789',
                'razon_social': 'Empresa S.A.C.',
                'address': 'Av. Principal 123'
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        assert 'id' in response.data
        assert response.data['document_type'] == '01'
        assert response.data['serie'] == 'F001'
        assert response.data['numero'] == '00000001'
        assert response.data['sunat_id'] == 'test-document-id-123'
        assert response.data['amount'] == '100.00'
        
        # Verify document was created in database
        document = models.Document.objects.get(sunat_id='test-document-id-123')
        assert document.document_type == '01'
        assert document.serie == 'F001'
        assert document.numero == '00000001'
        assert document.amount == Decimal('100.00')
    
    @patch('taxes.views.requests.post')
    @patch('taxes.views.get_correlative')
    def test_create_invoice_success_with_order_id(self, mock_get_correlative, mock_post, authenticated_api_client):
        """Test successful invoice creation with order_id"""
        mock_get_correlative.return_value = '00000002'
        
        # Create an order
        order = baker.make(store_models.Order)
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'documentId': 'test-document-id-456',
            'status': 'OK'
        }
        mock_post.return_value = mock_response
        
        url = reverse('document-create-invoice')
        response = authenticated_api_client.post(
            url,
            {
                'order_items': [
                    {'id': '1', 'name': 'Producto 1', 'quantity': 2, 'cost': 60.00}
                ],
                'ruc': '20123456789',
                'razon_social': 'Empresa S.A.C.',
                'address': 'Av. Principal 123',
                'order_id': order.id
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['amount'] == '120.00'
        
        # Verify document was created in database
        document = models.Document.objects.get(sunat_id='test-document-id-456')
        assert document.amount == Decimal('120.00')
        
        # Verify order was updated with document
        order.refresh_from_db()
        assert order.document == document
    
    @patch('taxes.views.requests.post')
    @patch('taxes.views.get_correlative')
    def test_create_invoice_order_not_found(self, mock_get_correlative, mock_post, authenticated_api_client):
        """Test invoice creation when order_id is provided but order doesn't exist"""
        mock_get_correlative.return_value = '00000003'
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'documentId': 'test-document-id-789',
            'status': 'OK'
        }
        mock_post.return_value = mock_response
        
        url = reverse('document-create-invoice')
        response = authenticated_api_client.post(
            url,
            {
                'order_items': [
                    {'id': '1', 'name': 'Producto 1', 'quantity': 1, 'cost': 100.00}
                ],
                'ruc': '20123456789',
                'razon_social': 'Empresa S.A.C.',
                'address': 'Av. Principal 123',
                'order_id': 99999  # Non-existent order ID
            },
            format='json'
        )
        
        # Should still succeed - document created but order not linked
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['sunat_id'] == 'test-document-id-789'
        
        # Verify document was created
        assert models.Document.objects.filter(sunat_id='test-document-id-789').exists()
    
    @patch('taxes.views.requests.post')
    @patch('taxes.views.get_correlative')
    def test_create_invoice_network_error(self, mock_get_correlative, mock_post, authenticated_api_client):
        """Test invoice creation when network error occurs"""
        mock_get_correlative.return_value = '00000004'
        
        import requests
        mock_post.side_effect = requests.exceptions.RequestException("Connection error")
        
        url = reverse('document-create-invoice')
        response = authenticated_api_client.post(
            url,
            {
                'order_items': [
                    {'id': '1', 'name': 'Producto 1', 'quantity': 1, 'cost': 50.00}
                ],
                'ruc': '20123456789',
                'razon_social': 'Empresa S.A.C.',
                'address': 'Av. Principal 123'
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        assert 'error' in response.data
        assert 'Failed to create invoice' in response.data['error']
    
    @patch('taxes.views.requests.post')
    @patch('taxes.views.get_correlative')
    def test_create_invoice_multiple_items(self, mock_get_correlative, mock_post, authenticated_api_client):
        """Test invoice creation with multiple order items"""
        mock_get_correlative.return_value = '00000005'
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'documentId': 'test-document-id-multi',
            'status': 'OK'
        }
        mock_post.return_value = mock_response
        
        url = reverse('document-create-invoice')
        response = authenticated_api_client.post(
            url,
            {
                'order_items': [
                    {'id': '1', 'name': 'Producto 1', 'quantity': 2, 'cost': 60.00},
                    {'id': '2', 'name': 'Producto 2', 'quantity': 1, 'cost': 30.00}
                ],
                'ruc': '20123456789',
                'razon_social': 'Empresa S.A.C.',
                'address': 'Av. Principal 123'
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        # Total: 2 * 60 + 1 * 30 = 120 + 30 = 150
        assert response.data['amount'] == '150.00'
        
        document = models.Document.objects.get(sunat_id='test-document-id-multi')
        assert document.amount == Decimal('150.00')
    
    @patch('taxes.views.requests.post')
    @patch('taxes.views.get_correlative')
    def test_create_invoice_verifies_sunat_api_call(self, mock_get_correlative, mock_post, authenticated_api_client):
        """Test that the correct data is sent to Sunat API"""
        mock_get_correlative.return_value = '00000006'
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'documentId': 'test-document-id-verify',
            'status': 'OK'
        }
        mock_post.return_value = mock_response
        
        url = reverse('document-create-invoice')
        response = authenticated_api_client.post(
            url,
            {
                'order_items': [
                    {'id': '1', 'name': 'Producto 1', 'quantity': 1, 'cost': 50.00}
                ],
                'ruc': '20123456789',
                'razon_social': 'Empresa Test S.A.C.',
                'address': 'Av. Test 123'
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
        invoice_data = call_args[1]['json']
        assert 'fileName' in invoice_data
        assert invoice_data['fileName'] == '20482674828-01-F001-00000006'

