import pytest
from decimal import Decimal
from unittest.mock import patch, Mock, MagicMock
from model_bakery import baker
from rest_framework import status
from django.urls import reverse
from datetime import datetime

from taxes import models
from store import models as store_models


@pytest.mark.django_db
class TestDocumentGenerateTicketView:
    """Tests for POST /taxes/documents/generate-ticket/ - Generate simple ticket PDF (no Sunat)"""
    
    def test_generate_ticket_unauthenticated(self, api_client):
        """Test that unauthenticated requests are rejected"""
        url = reverse('document-generate-ticket')
        response = api_client.post(url, {})
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_generate_ticket_invalid_data(self, authenticated_api_client):
        """Test ticket generation with invalid data"""
        url = reverse('document-generate-ticket')
        response = authenticated_api_client.post(url, {}, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'document_type' in response.data
    
    def test_generate_ticket_missing_order_items(self, authenticated_api_client):
        """Test ticket generation without order_items"""
        url = reverse('document-generate-ticket')
        response = authenticated_api_client.post(
            url,
            {
                'document_type': 'ticket',
                'order_number': 'ORD-001',
                'customer_name': 'Test Customer'
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'order_items' in response.data
    
    def test_generate_ticket_invalid_order_items(self, authenticated_api_client):
        """Test ticket generation with invalid order_items format"""
        url = reverse('document-generate-ticket')
        response = authenticated_api_client.post(
            url,
            {
                'document_type': 'ticket',
                'order_items': [
                    {'id': '1', 'name': 'Producto 1'}  # Missing quantity and cost
                ]
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'order_items' in response.data
    
    def test_generate_ticket_success_basic(self, authenticated_api_client):
        """Test successful ticket generation with minimal data"""
        url = reverse('document-generate-ticket')
        response = authenticated_api_client.post(
            url,
            {
                'document_type': 'ticket',
                'order_items': [
                    {'id': '1', 'name': 'Producto 1', 'quantity': 2, 'cost': 10.00}
                ]
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert response['Content-Type'] == 'application/pdf'
        assert 'inline' in response['Content-Disposition']
        assert 'filename="ticket_' in response['Content-Disposition']
        
        # Verify PDF content is returned
        assert len(response.content) > 0
        assert response.content[:4] == b'%PDF'  # PDF file signature
    
    def test_generate_ticket_success_with_all_fields(self, authenticated_api_client):
        """Test successful ticket generation with all optional fields"""
        url = reverse('document-generate-ticket')
        response = authenticated_api_client.post(
            url,
            {
                'document_type': 'ticket',
                'order_items': [
                    {'id': '1', 'name': 'Producto 1', 'quantity': 2, 'cost': 10.00},
                    {'id': '2', 'name': 'Producto 2', 'quantity': 1, 'cost': 25.50}
                ],
                'order_number': 'ORD-001',
                'customer_name': 'Juan Pérez'
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert response['Content-Type'] == 'application/pdf'
        assert 'filename="ticket_ORD-001.pdf"' in response['Content-Disposition']
        assert response.content[:4] == b'%PDF'
    
    def test_generate_ticket_multiple_items(self, authenticated_api_client):
        """Test ticket generation with multiple order items"""
        url = reverse('document-generate-ticket')
        response = authenticated_api_client.post(
            url,
            {
                'document_type': 'ticket',
                'order_items': [
                    {'id': '1', 'name': 'Producto 1', 'quantity': 2, 'cost': 60.00},
                    {'id': '2', 'name': 'Producto 2', 'quantity': 1, 'cost': 30.00},
                    {'id': '3', 'name': 'Producto 3', 'quantity': 3, 'cost': 15.50}
                ]
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert response['Content-Type'] == 'application/pdf'
        assert response.content[:4] == b'%PDF'
    
    def test_generate_ticket_empty_order_items(self, authenticated_api_client):
        """Test ticket generation with empty order_items list"""
        url = reverse('document-generate-ticket')
        response = authenticated_api_client.post(
            url,
            {
                'document_type': 'ticket',
                'order_items': []
            },
            format='json'
        )
        
        # Should still generate PDF (just empty items)
        assert response.status_code == status.HTTP_200_OK
        assert response['Content-Type'] == 'application/pdf'
    
    def test_generate_ticket_with_order_number_only(self, authenticated_api_client):
        """Test ticket generation with only order_number"""
        url = reverse('document-generate-ticket')
        response = authenticated_api_client.post(
            url,
            {
                'document_type': 'ticket',
                'order_items': [
                    {'id': '1', 'name': 'Producto 1', 'quantity': 1, 'cost': 50.00}
                ],
                'order_number': 'ORD-123'
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert 'filename="ticket_ORD-123.pdf"' in response['Content-Disposition']
    
    def test_generate_ticket_with_customer_name_only(self, authenticated_api_client):
        """Test ticket generation with only customer_name"""
        url = reverse('document-generate-ticket')
        response = authenticated_api_client.post(
            url,
            {
                'document_type': 'ticket',
                'order_items': [
                    {'id': '1', 'name': 'Producto 1', 'quantity': 1, 'cost': 50.00}
                ],
                'customer_name': 'Maria Garcia'
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert response['Content-Type'] == 'application/pdf'
        # Filename should have timestamp since no order_number
        assert 'filename="ticket_' in response['Content-Disposition']
    
    def test_generate_ticket_empty_optional_fields(self, authenticated_api_client):
        """Test ticket generation with empty optional fields"""
        url = reverse('document-generate-ticket')
        response = authenticated_api_client.post(
            url,
            {
                'document_type': 'ticket',
                'order_items': [
                    {'id': '1', 'name': 'Producto 1', 'quantity': 1, 'cost': 50.00}
                ],
                'order_number': '',
                'customer_name': ''
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert response['Content-Type'] == 'application/pdf'
    
    def test_generate_ticket_pdf_content_structure(self, authenticated_api_client):
        """Test that generated PDF has correct structure"""
        url = reverse('document-generate-ticket')
        response = authenticated_api_client.post(
            url,
            {
                'document_type': 'ticket',
                'order_items': [
                    {'id': '1', 'name': 'Producto Test', 'quantity': 2, 'cost': 10.00}
                ],
                'order_number': 'TEST-001',
                'customer_name': 'Test Customer'
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_200_OK
        pdf_content = response.content
        
        # Verify PDF signature
        assert pdf_content[:4] == b'%PDF'
        
        # Verify PDF structure (check for PDF end marker)
        assert b'%%EOF' in pdf_content
        
        # Verify PDF is not empty
        assert len(pdf_content) > 1000  # Should be at least 1KB for a valid ticket
    
    def test_generate_ticket_decimal_precision(self, authenticated_api_client):
        """Test ticket generation with decimal quantities and costs"""
        url = reverse('document-generate-ticket')
        response = authenticated_api_client.post(
            url,
            {
                'document_type': 'ticket',
                'order_items': [
                    {'id': '1', 'name': 'Producto 1', 'quantity': 1.5, 'cost': 10.99},
                    {'id': '2', 'name': 'Producto 2', 'quantity': 2.25, 'cost': 5.50}
                ]
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert response['Content-Type'] == 'application/pdf'
    
    def test_generate_ticket_long_product_name(self, authenticated_api_client):
        """Test ticket generation with very long product names"""
        url = reverse('document-generate-ticket')
        response = authenticated_api_client.post(
            url,
            {
                'document_type': 'ticket',
                'order_items': [
                    {'id': '1', 'name': 'A' * 100, 'quantity': 1, 'cost': 10.00}
                ]
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert response['Content-Type'] == 'application/pdf'
    
    @patch('taxes.views.generate_ticket_pdf')
    def test_generate_ticket_pdf_generation_error(self, mock_generate_pdf, authenticated_api_client):
        """Test ticket generation when PDF generation fails"""
        mock_generate_pdf.side_effect = Exception("PDF generation failed")
        
        url = reverse('document-generate-ticket')
        response = authenticated_api_client.post(
            url,
            {
                'document_type': 'ticket',
                'order_items': [
                    {'id': '1', 'name': 'Producto 1', 'quantity': 1, 'cost': 10.00}
                ]
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert 'error' in response.data
        assert 'Failed to generate PDF' in response.data['error']
    
    def test_generate_ticket_verifies_pdf_function_called(self, authenticated_api_client):
        """Test that generate_ticket_pdf is called with correct parameters"""
        with patch('taxes.views.generate_ticket_pdf') as mock_generate_pdf:
            mock_buffer = MagicMock()
            mock_buffer.getvalue.return_value = b'%PDF fake pdf content'
            mock_generate_pdf.return_value = mock_buffer
            
            url = reverse('document-generate-ticket')
            response = authenticated_api_client.post(
                url,
                {
                    'document_type': 'ticket',
                    'order_items': [
                        {'id': '1', 'name': 'Producto 1', 'quantity': 2, 'cost': 10.00}
                    ],
                    'order_number': 'ORD-001',
                    'customer_name': 'Test Customer'
                },
                format='json'
            )
            
            assert response.status_code == status.HTTP_200_OK
            
            # Verify generate_ticket_pdf was called
            mock_generate_pdf.assert_called_once()
            call_kwargs = mock_generate_pdf.call_args[1]
            
            # Verify parameters
            assert len(call_kwargs['order_items']) == 1
            assert call_kwargs['order_items'][0]['name'] == 'Producto 1'
            assert call_kwargs['business_name'] == 'Taypa'
            assert call_kwargs['business_address'] == 'Avis Luz y Fuerza D-8'
            assert call_kwargs['business_ruc'] == '20482674828'
            assert call_kwargs['order_number'] == 'ORD-001'
            assert call_kwargs['customer_name'] == 'Test Customer'
            assert call_kwargs.get('document_type') is None  # Simple tickets don't pass document_type
    
    def test_generate_ticket_no_sunat_connection(self, authenticated_api_client):
        """Test that generate-ticket endpoint does not require Sunat connection"""
        # This endpoint should work without Sunat credentials
        with patch('taxes.views.settings') as mock_settings:
            mock_settings.SUNAT_PERSONA_ID = None
            mock_settings.SUNAT_PERSONA_TOKEN = None
            
            url = reverse('document-generate-ticket')
            response = authenticated_api_client.post(
                url,
                {
                    'document_type': 'ticket',
                    'order_items': [
                        {'id': '1', 'name': 'Producto 1', 'quantity': 1, 'cost': 10.00}
                    ]
                },
                format='json'
            )
            
            # Should succeed - no Sunat connection needed
            assert response.status_code == status.HTTP_200_OK
            assert response['Content-Type'] == 'application/pdf'
    
    # ============ Tests for boleta/factura PDF generation ============
    
    def test_generate_boleta_missing_document_id(self, authenticated_api_client):
        """Test boleta generation without document_id or sunat_id"""
        url = reverse('document-generate-ticket')
        response = authenticated_api_client.post(
            url,
            {
                'document_type': 'boleta'
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'document_id' in response.data
    
    def test_generate_boleta_document_not_found(self, authenticated_api_client):
        """Test boleta generation with non-existent document_id"""
        import uuid
        url = reverse('document-generate-ticket')
        response = authenticated_api_client.post(
            url,
            {
                'document_type': 'boleta',
                'document_id': str(uuid.uuid4())
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert 'not found' in response.data['error'].lower()
    
    def test_generate_factura_document_not_found(self, authenticated_api_client):
        """Test factura generation with non-existent sunat_id"""
        url = reverse('document-generate-ticket')
        response = authenticated_api_client.post(
            url,
            {
                'document_type': 'factura',
                'sunat_id': 'nonexistent-id'
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    @patch('taxes.services.download_and_extract_xml')
    @patch('taxes.services.parse_xml_customer_info')
    def test_generate_boleta_success(self, mock_parse_customer, mock_download_xml, authenticated_api_client):
        """Test successful boleta PDF generation"""
        # Mock XML functions (not used for boleta but needed for import)
        mock_download_xml.return_value = (None, None)
        mock_parse_customer.return_value = {}
        # Create a boleta document
        document = baker.make(
            models.Document,
            document_type='03',  # Boleta
            serie='B001',
            numero='00000001',
            sunat_id='test-sunat-id',
            sunat_status='ACEPTADO',
            status='accepted',
            amount=Decimal('100.00'),
            sunat_issue_time=int(datetime.now().timestamp() * 1000),
        )
        
        # Create order with items
        category = baker.make(store_models.Category, name='Burgers')
        dish = baker.make(store_models.Dish, name='Clasica', price=Decimal('10.00'), category=category)
        customer = baker.make(store_models.Customer, first_name='Juan', last_name='Perez')
        order = baker.make(store_models.Order, customer=customer, document=document)
        baker.make(
            store_models.OrderItem,
            order=order,
            dish=dish,
            category=category,
            quantity=3,
            price=Decimal('30.00')
        )
        
        url = reverse('document-generate-ticket')
        response = authenticated_api_client.post(
            url,
            {
                'document_type': 'boleta',
                'document_id': str(document.id)
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert response['Content-Type'] == 'application/pdf'
        assert 'filename="boleta_B001-00000001.pdf"' in response['Content-Disposition']
        assert response.content[:4] == b'%PDF'
    
    @patch('taxes.services.download_and_extract_xml')
    @patch('taxes.services.parse_xml_customer_info')
    def test_generate_factura_success(self, mock_parse_customer, mock_download_xml, authenticated_api_client):
        """Test successful factura PDF generation with customer info"""
        # Mock XML download and customer info extraction
        mock_download_xml.return_value = ('<?xml version="1.0"?><Invoice></Invoice>', None)
        mock_parse_customer.return_value = {
            'razon_social': 'Empresa Test S.A.C.',
            'ruc': '20123456789',
            'address': 'Av. Test 123'
        }
        
        # Create a factura document
        document = baker.make(
            models.Document,
            document_type='01',  # Factura
            serie='F001',
            numero='00000001',
            sunat_id='test-sunat-id',
            sunat_status='ACEPTADO',
            status='accepted',
            amount=Decimal('118.00'),
            xml_url='https://example.com/xml.zip',
            sunat_issue_time=int(datetime.now().timestamp() * 1000),
        )
        
        # Create order with items
        category = baker.make(store_models.Category, name='Burgers')
        dish = baker.make(store_models.Dish, name='Clasica', price=Decimal('100.00'), category=category)
        customer = baker.make(store_models.Customer, first_name='Company', last_name='Test')
        order = baker.make(store_models.Order, customer=customer, document=document)
        baker.make(
            store_models.OrderItem,
            order=order,
            dish=dish,
            category=category,
            quantity=1,
            price=Decimal('100.00')
        )
        
        url = reverse('document-generate-ticket')
        response = authenticated_api_client.post(
            url,
            {
                'document_type': 'factura',
                'document_id': str(document.id)
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert response['Content-Type'] == 'application/pdf'
        assert 'filename="factura_F001-00000001.pdf"' in response['Content-Disposition']
        assert response.content[:4] == b'%PDF'
    
    def test_generate_boleta_document_type_mismatch(self, authenticated_api_client):
        """Test boleta generation with factura document type"""
        # Create a factura document but request boleta
        document = baker.make(
            models.Document,
            document_type='01',  # Factura
            serie='F001',
            numero='00000001',
            sunat_id='test-sunat-id',
        )
        
        url = reverse('document-generate-ticket')
        response = authenticated_api_client.post(
            url,
            {
                'document_type': 'boleta',
                'document_id': str(document.id)
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'mismatch' in response.data['error'].lower()
    
    def test_generate_document_without_order(self, authenticated_api_client):
        """Test generating PDF for document without linked order"""
        document = baker.make(
            models.Document,
            document_type='03',  # Boleta
            serie='B001',
            numero='00000001',
            sunat_id='test-sunat-id',
        )
        
        url = reverse('document-generate-ticket')
        response = authenticated_api_client.post(
            url,
            {
                'document_type': 'boleta',
                'document_id': str(document.id)
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert 'order' in response.data['error'].lower()

