import pytest
from model_bakery import baker
from rest_framework import status
from django.urls import reverse

from store import models

# Fixtures are imported from conftest.py automatically by pytest


@pytest.mark.django_db
class TestAddressListView:
    """Tests for GET /api/addresses/ - List all addresses"""
    
    def test_list_addresses_unauthenticated(self, api_client):
        """Test that unauthenticated requests are rejected"""
        url = reverse('address-list')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_list_addresses_empty(self, authenticated_api_client):
        """Test listing addresses when none exist"""
        url = reverse('address-list')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data == []
    
    def test_list_addresses_single(self, authenticated_api_client, address):
        """Test listing a single address"""
        url = reverse('address-list')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]['street'] == '123 Main St'
        assert response.data[0]['reference'] == 'Apt 4B'
    
    def test_list_addresses_multiple(self, authenticated_api_client, customer):
        """Test listing multiple addresses"""
        baker.make(models.Address, customer=customer, _quantity=3)
        url = reverse('address-list')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 3
    
    def test_list_addresses_includes_all_fields(self, authenticated_api_client, address):
        """Test that all fields are included in response"""
        url = reverse('address-list')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.data[0]
        assert 'id' in data
        assert 'street' in data
        assert 'reference' in data
        assert 'customer' in data
        assert 'is_primary' in data
        assert 'created_at' in data
        assert 'updated_at' in data


@pytest.mark.django_db
class TestAddressCreateView:
    """Tests for POST /api/addresses/ - Create address"""
    
    def test_create_address_unauthenticated(self, api_client, customer):
        """Test that unauthenticated requests are rejected"""
        url = reverse('address-list')
        data = {
            'street': '456 Oak Ave',
            'reference': 'Suite 100',
            'customer': customer.id
        }
        response = api_client.post(url, data)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_create_address_success(self, authenticated_api_client, customer):
        """Test creating an address successfully"""
        url = reverse('address-list')
        data = {
            'street': '456 Oak Ave',
            'reference': 'Suite 100',
            'customer': customer.id,
            'is_primary': True
        }
        response = authenticated_api_client.post(url, data)
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['street'] == '456 Oak Ave'
        assert response.data['reference'] == 'Suite 100'
        assert response.data['customer'] == customer.id
        assert response.data['is_primary'] is True
        
        # Verify address was created in database
        assert models.Address.objects.filter(street='456 Oak Ave').exists()
    
    def test_create_address_missing_street(self, authenticated_api_client, customer):
        """Test creating address without street (required field)"""
        url = reverse('address-list')
        data = {
            'reference': 'Test',
            'customer': customer.id
        }
        response = authenticated_api_client.post(url, data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_create_address_missing_customer(self, authenticated_api_client):
        """Test creating address without customer (required field)"""
        url = reverse('address-list')
        data = {
            'street': '123 Test St',
            'reference': 'Test'
        }
        response = authenticated_api_client.post(url, data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_create_address_invalid_customer(self, authenticated_api_client):
        """Test creating address with non-existent customer"""
        url = reverse('address-list')
        data = {
            'street': '123 Test St',
            'reference': 'Test',
            'customer': 99999  # Non-existent ID
        }
        response = authenticated_api_client.post(url, data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_create_address_empty_reference(self, authenticated_api_client, customer):
        """Test creating address with empty reference (should be allowed)"""
        url = reverse('address-list')
        data = {
            'street': '123 Test St',
            'reference': '',
            'customer': customer.id
        }
        response = authenticated_api_client.post(url, data)
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['reference'] == ''
    
    def test_create_address_default_is_primary(self, authenticated_api_client, customer):
        """Test that is_primary defaults to False when not provided"""
        url = reverse('address-list')
        data = {
            'street': '123 Test St',
            'customer': customer.id
        }
        response = authenticated_api_client.post(url, data)
        
        assert response.status_code == status.HTTP_201_CREATED
        
        # Verify the default value in the database (model default is False)
        address = models.Address.objects.get(id=response.data['id'])
        assert address.is_primary is False


@pytest.mark.django_db
class TestAddressDetailView:
    """Tests for GET /api/addresses/{id}/ - Retrieve address"""
    
    def test_retrieve_address_unauthenticated(self, api_client, address):
        """Test that unauthenticated requests are rejected"""
        url = reverse('address-detail', kwargs={'pk': address.id})
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_retrieve_address_success(self, authenticated_api_client, address):
        """Test retrieving an address successfully"""
        url = reverse('address-detail', kwargs={'pk': address.id})
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == address.id
        assert response.data['street'] == '123 Main St'
        assert response.data['reference'] == 'Apt 4B'
    
    def test_retrieve_address_not_found(self, authenticated_api_client):
        """Test retrieving non-existent address"""
        url = reverse('address-detail', kwargs={'pk': 99999})
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestAddressUpdateView:
    """Tests for PUT/PATCH /api/addresses/{id}/ - Update address"""
    
    def test_update_address_unauthenticated(self, api_client, address):
        """Test that unauthenticated requests are rejected"""
        url = reverse('address-detail', kwargs={'pk': address.id})
        data = {'street': 'Updated Street'}
        response = api_client.patch(url, data)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_update_address_put_success(self, authenticated_api_client, address):
        """Test full update (PUT) of address"""
        url = reverse('address-detail', kwargs={'pk': address.id})
        data = {
            'street': '789 Updated St',
            'reference': 'Updated Reference',
            'customer': address.customer.id,
            'is_primary': True
        }
        response = authenticated_api_client.put(url, data)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['street'] == '789 Updated St'
        assert response.data['reference'] == 'Updated Reference'
        assert response.data['is_primary'] is True
        
        # Verify in database
        address.refresh_from_db()
        assert address.street == '789 Updated St'
        assert address.reference == 'Updated Reference'
    
    def test_partial_update_address_patch_success(self, authenticated_api_client, address):
        """Test partial update (PATCH) of address"""
        url = reverse('address-detail', kwargs={'pk': address.id})
        data = {'street': 'Partially Updated St'}
        response = authenticated_api_client.patch(url, data)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['street'] == 'Partially Updated St'
        # Other fields should remain unchanged
        assert response.data['reference'] == 'Apt 4B'
        
        # Verify in database
        address.refresh_from_db()
        assert address.street == 'Partially Updated St'
        assert address.reference == 'Apt 4B'
    
    def test_update_address_street(self, authenticated_api_client, address):
        """Test updating only the street"""
        url = reverse('address-detail', kwargs={'pk': address.id})
        data = {'street': 'New Street Name'}
        response = authenticated_api_client.patch(url, data)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['street'] == 'New Street Name'
    
    def test_update_address_toggle_is_primary(self, authenticated_api_client, address):
        """Test toggling is_primary field"""
        assert address.is_primary is False
        
        url = reverse('address-detail', kwargs={'pk': address.id})
        data = {'is_primary': True}
        response = authenticated_api_client.patch(url, data)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['is_primary'] is True
        
        address.refresh_from_db()
        assert address.is_primary is True
    
    def test_update_address_not_found(self, authenticated_api_client):
        """Test updating non-existent address"""
        url = reverse('address-detail', kwargs={'pk': 99999})
        data = {'street': 'Updated'}
        response = authenticated_api_client.patch(url, data)
        
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestAddressDeleteView:
    """Tests for DELETE /api/addresses/{id}/ - Delete address"""
    
    def test_delete_address_unauthenticated(self, api_client, address):
        """Test that unauthenticated requests are rejected"""
        url = reverse('address-detail', kwargs={'pk': address.id})
        response = api_client.delete(url)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_delete_address_success(self, authenticated_api_client, address):
        """Test deleting an address successfully"""
        address_id = address.id
        url = reverse('address-detail', kwargs={'pk': address_id})
        response = authenticated_api_client.delete(url)
        
        assert response.status_code == status.HTTP_204_NO_CONTENT
        
        # Verify address was deleted from database
        assert not models.Address.objects.filter(id=address_id).exists()
    
    def test_delete_address_not_found(self, authenticated_api_client):
        """Test deleting non-existent address"""
        url = reverse('address-detail', kwargs={'pk': 99999})
        response = authenticated_api_client.delete(url)
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_delete_address_cascade_from_customer(self, authenticated_api_client, customer):
        """Test that addresses are deleted when customer is deleted (CASCADE)"""
        address = baker.make(models.Address, customer=customer, street='Test St')
        address_id = address.id
        
        # Delete customer
        customer.delete()
        
        # Verify address was also deleted (CASCADE)
        assert not models.Address.objects.filter(id=address_id).exists()


@pytest.mark.django_db
class TestAddressByCustomerAction:
    """Tests for GET /api/addresses/by_customer/?customer_id={id} - Custom action"""
    
    def test_by_customer_unauthenticated(self, api_client, customer):
        """Test that unauthenticated requests are rejected"""
        url = reverse('address-by-customer')
        response = api_client.get(url, {'customer_id': customer.id})
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_by_customer_success(self, authenticated_api_client, customer):
        """Test getting addresses by customer successfully"""
        # Create addresses for the customer
        address1 = baker.make(models.Address, customer=customer, street='Address 1')
        address2 = baker.make(models.Address, customer=customer, street='Address 2')
        
        # Create address for different customer (should not appear)
        other_customer = baker.make(models.Customer)
        baker.make(models.Address, customer=other_customer, street='Other Address')
        
        url = reverse('address-by-customer')
        response = authenticated_api_client.get(url, {'customer_id': customer.id})
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2
        street_names = [addr['street'] for addr in response.data]
        assert 'Address 1' in street_names
        assert 'Address 2' in street_names
        assert 'Other Address' not in street_names
    
    def test_by_customer_empty_result(self, authenticated_api_client, customer):
        """Test getting addresses from customer with no addresses"""
        url = reverse('address-by-customer')
        response = authenticated_api_client.get(url, {'customer_id': customer.id})
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data == []
    
    def test_by_customer_missing_parameter(self, authenticated_api_client):
        """Test by_customer without customer_id parameter"""
        url = reverse('address-by-customer')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data
        assert 'customer_id' in response.data['error'].lower()
    
    def test_by_customer_invalid_customer_id(self, authenticated_api_client):
        """Test by_customer with non-existent customer_id"""
        url = reverse('address-by-customer')
        response = authenticated_api_client.get(url, {'customer_id': 99999})
        
        # Should return empty list (no error, just no results)
        assert response.status_code == status.HTTP_200_OK
        assert response.data == []
    
    def test_by_customer_invalid_customer_id_format(self, authenticated_api_client):
        """Test by_customer with invalid customer_id format"""
        url = reverse('address-by-customer')
        
        # The view doesn't validate the customer_id format, so Django will raise
        # a ValueError when trying to convert 'invalid' to int for the filter.
        # In a real scenario, you'd want to add validation to the view to return 400 instead.
        # This test documents the current behavior (raises ValueError) and could be
        # updated if the view is improved to validate input.
        with pytest.raises(ValueError, match="Field 'id' expected a number"):
            authenticated_api_client.get(url, {'customer_id': 'invalid'})
    
    def test_by_customer_multiple_customers(self, authenticated_api_client):
        """Test filtering works correctly with multiple customers"""
        customer1 = baker.make(models.Customer, first_name='Customer', last_name='One')
        customer2 = baker.make(models.Customer, first_name='Customer', last_name='Two')
        
        address1 = baker.make(models.Address, customer=customer1, street='Address 1')
        address2 = baker.make(models.Address, customer=customer1, street='Address 2')
        address3 = baker.make(models.Address, customer=customer2, street='Address 3')
        
        url = reverse('address-by-customer')
        response = authenticated_api_client.get(url, {'customer_id': customer1.id})
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2
        street_names = [addr['street'] for addr in response.data]
        assert 'Address 1' in street_names
        assert 'Address 2' in street_names
        assert 'Address 3' not in street_names


@pytest.mark.django_db
class TestAddressEdgeCases:
    """Tests for edge cases and special scenarios"""
    
    def test_address_long_street(self, authenticated_api_client, customer):
        """Test creating address with very long street"""
        url = reverse('address-list')
        data = {
            'street': 'A' * 255,  # Max length
            'customer': customer.id
        }
        response = authenticated_api_client.post(url, data)
        
        assert response.status_code == status.HTTP_201_CREATED
    
    def test_address_street_exceeds_max_length(self, authenticated_api_client, customer):
        """Test creating address with street exceeding max length"""
        url = reverse('address-list')
        data = {
            'street': 'A' * 256,  # Exceeds max length
            'customer': customer.id
        }
        response = authenticated_api_client.post(url, data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_address_long_reference(self, authenticated_api_client, customer):
        """Test creating address with very long reference"""
        url = reverse('address-list')
        data = {
            'street': '123 Test St',
            'reference': 'A' * 1000,  # Long reference
            'customer': customer.id
        }
        response = authenticated_api_client.post(url, data)
        
        assert response.status_code == status.HTTP_201_CREATED
    
    def test_address_unicode_characters(self, authenticated_api_client, customer):
        """Test creating address with unicode characters"""
        url = reverse('address-list')
        data = {
            'street': 'Calle Principal 123 🏠',
            'reference': 'Cerca del parque, entre calle áéíóú',
            'customer': customer.id
        }
        response = authenticated_api_client.post(url, data)
        
        assert response.status_code == status.HTTP_201_CREATED
        assert 'Calle Principal' in response.data['street']
        assert 'áéíóú' in response.data['reference']
    
    def test_address_multiple_primary_addresses(self, authenticated_api_client, customer):
        """Test that multiple addresses can be marked as primary"""
        # This tests that the system allows multiple primary addresses
        # (no unique constraint on is_primary)
        address1 = baker.make(models.Address, customer=customer, is_primary=True)
        address2 = baker.make(models.Address, customer=customer, is_primary=True)
        
        assert address1.is_primary is True
        assert address2.is_primary is True
    
    def test_address_customer_relationship(self, authenticated_api_client, customer):
        """Test address-customer relationship"""
        address = baker.make(models.Address, customer=customer, street='Test St')
        
        # Verify relationship
        assert address.customer == customer
        assert address in customer.addresses.all()
        
        # Verify through API
        url = reverse('address-detail', kwargs={'pk': address.id})
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['customer'] == customer.id

