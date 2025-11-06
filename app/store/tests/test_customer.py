import pytest
from model_bakery import baker
from rest_framework import status
from django.urls import reverse

from store import models

# Fixtures are imported from conftest.py automatically by pytest


@pytest.mark.django_db
class TestCustomerListView:
    """Tests for GET /api/customers/ - List all customers"""
    
    def test_list_customers_unauthenticated(self, api_client):
        """Test that unauthenticated requests are rejected"""
        url = reverse('customer-list')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_list_customers_empty(self, authenticated_api_client):
        """Test listing customers when none exist"""
        url = reverse('customer-list')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data == []
    
    def test_list_customers_single(self, authenticated_api_client, customer):
        """Test listing a single customer"""
        url = reverse('customer-list')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]['first_name'] == 'John'
        assert response.data[0]['last_name'] == 'Doe'
        assert response.data[0]['phone_number'] == '1234567890'
    
    def test_list_customers_multiple(self, authenticated_api_client):
        """Test listing multiple customers"""
        baker.make(models.Customer, _quantity=3)
        url = reverse('customer-list')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 3
    
    def test_list_customers_includes_all_fields(self, authenticated_api_client, customer):
        """Test that all fields are included in response"""
        url = reverse('customer-list')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.data[0]
        assert 'id' in data
        assert 'first_name' in data
        assert 'last_name' in data
        assert 'phone_number' in data
        assert 'created_at' in data
        assert 'updated_at' in data


@pytest.mark.django_db
class TestCustomerCreateView:
    """Tests for POST /api/customers/ - Create customer"""
    
    def test_create_customer_unauthenticated(self, api_client):
        """Test that unauthenticated requests are rejected"""
        url = reverse('customer-list')
        data = {
            'first_name': 'Jane',
            'last_name': 'Smith',
            'phone_number': '9876543210'
        }
        response = api_client.post(url, data)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_create_customer_success(self, authenticated_api_client):
        """Test creating a customer successfully"""
        url = reverse('customer-list')
        data = {
            'first_name': 'Jane',
            'last_name': 'Smith',
            'phone_number': '9876543210'
        }
        response = authenticated_api_client.post(url, data)
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['first_name'] == 'Jane'
        assert response.data['last_name'] == 'Smith'
        assert response.data['phone_number'] == '9876543210'
        
        # Verify customer was created in database
        assert models.Customer.objects.filter(first_name='Jane').exists()
    
    def test_create_customer_missing_first_name(self, authenticated_api_client):
        """Test creating customer without first_name (required field)"""
        url = reverse('customer-list')
        data = {
            'last_name': 'Smith',
            'phone_number': '9876543210'
        }
        response = authenticated_api_client.post(url, data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_create_customer_missing_last_name(self, authenticated_api_client):
        """Test creating customer without last_name (required field)"""
        url = reverse('customer-list')
        data = {
            'first_name': 'Jane',
            'phone_number': '9876543210'
        }
        response = authenticated_api_client.post(url, data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_create_customer_missing_phone_number(self, authenticated_api_client):
        """Test creating customer without phone_number (required field)"""
        url = reverse('customer-list')
        data = {
            'first_name': 'Jane',
            'last_name': 'Smith'
        }
        response = authenticated_api_client.post(url, data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_create_customer_empty_first_name(self, authenticated_api_client):
        """Test creating customer with empty first_name"""
        url = reverse('customer-list')
        data = {
            'first_name': '',
            'last_name': 'Smith',
            'phone_number': '9876543210'
        }
        response = authenticated_api_client.post(url, data)
        
        # Empty string should fail validation
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_create_customer_special_characters_in_name(self, authenticated_api_client):
        """Test creating customer with special characters in name"""
        url = reverse('customer-list')
        data = {
            'first_name': "O'Brien",
            'last_name': "Smith-Jones",
            'phone_number': '9876543210'
        }
        response = authenticated_api_client.post(url, data)
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['first_name'] == "O'Brien"
        assert response.data['last_name'] == "Smith-Jones"


@pytest.mark.django_db
class TestCustomerDetailView:
    """Tests for GET /api/customers/{id}/ - Retrieve customer"""
    
    def test_retrieve_customer_unauthenticated(self, api_client, customer):
        """Test that unauthenticated requests are rejected"""
        url = reverse('customer-detail', kwargs={'pk': customer.id})
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_retrieve_customer_success(self, authenticated_api_client, customer):
        """Test retrieving a customer successfully"""
        url = reverse('customer-detail', kwargs={'pk': customer.id})
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == customer.id
        assert response.data['first_name'] == 'John'
        assert response.data['last_name'] == 'Doe'
        assert response.data['phone_number'] == '1234567890'
    
    def test_retrieve_customer_not_found(self, authenticated_api_client):
        """Test retrieving non-existent customer"""
        url = reverse('customer-detail', kwargs={'pk': 99999})
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestCustomerUpdateView:
    """Tests for PUT/PATCH /api/customers/{id}/ - Update customer"""
    
    def test_update_customer_unauthenticated(self, api_client, customer):
        """Test that unauthenticated requests are rejected"""
        url = reverse('customer-detail', kwargs={'pk': customer.id})
        data = {'first_name': 'Updated'}
        response = api_client.patch(url, data)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_update_customer_put_success(self, authenticated_api_client, customer):
        """Test full update (PUT) of customer"""
        url = reverse('customer-detail', kwargs={'pk': customer.id})
        data = {
            'first_name': 'Jane',
            'last_name': 'Smith',
            'phone_number': '9876543210'
        }
        response = authenticated_api_client.put(url, data)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['first_name'] == 'Jane'
        assert response.data['last_name'] == 'Smith'
        assert response.data['phone_number'] == '9876543210'
        
        # Verify in database
        customer.refresh_from_db()
        assert customer.first_name == 'Jane'
        assert customer.last_name == 'Smith'
    
    def test_partial_update_customer_patch_success(self, authenticated_api_client, customer):
        """Test partial update (PATCH) of customer"""
        url = reverse('customer-detail', kwargs={'pk': customer.id})
        data = {'first_name': 'Jane'}
        response = authenticated_api_client.patch(url, data)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['first_name'] == 'Jane'
        # Other fields should remain unchanged
        assert response.data['last_name'] == 'Doe'
        assert response.data['phone_number'] == '1234567890'
        
        # Verify in database
        customer.refresh_from_db()
        assert customer.first_name == 'Jane'
        assert customer.last_name == 'Doe'
    
    def test_update_customer_phone_number(self, authenticated_api_client, customer):
        """Test updating only the phone number"""
        url = reverse('customer-detail', kwargs={'pk': customer.id})
        data = {'phone_number': '9999999999'}
        response = authenticated_api_client.patch(url, data)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['phone_number'] == '9999999999'
    
    def test_update_customer_last_name(self, authenticated_api_client, customer):
        """Test updating only the last name"""
        url = reverse('customer-detail', kwargs={'pk': customer.id})
        data = {'last_name': 'UpdatedLast'}
        response = authenticated_api_client.patch(url, data)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['last_name'] == 'UpdatedLast'
    
    def test_update_customer_not_found(self, authenticated_api_client):
        """Test updating non-existent customer"""
        url = reverse('customer-detail', kwargs={'pk': 99999})
        data = {'first_name': 'Updated'}
        response = authenticated_api_client.patch(url, data)
        
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestCustomerDeleteView:
    """Tests for DELETE /api/customers/{id}/ - Delete customer"""
    
    def test_delete_customer_unauthenticated(self, api_client, customer):
        """Test that unauthenticated requests are rejected"""
        url = reverse('customer-detail', kwargs={'pk': customer.id})
        response = api_client.delete(url)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_delete_customer_success(self, authenticated_api_client, customer):
        """Test deleting a customer successfully"""
        customer_id = customer.id
        url = reverse('customer-detail', kwargs={'pk': customer_id})
        response = authenticated_api_client.delete(url)
        
        assert response.status_code == status.HTTP_204_NO_CONTENT
        
        # Verify customer was deleted from database
        assert not models.Customer.objects.filter(id=customer_id).exists()
    
    def test_delete_customer_not_found(self, authenticated_api_client):
        """Test deleting non-existent customer"""
        url = reverse('customer-detail', kwargs={'pk': 99999})
        response = authenticated_api_client.delete(url)
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_delete_customer_with_addresses_cascade(self, authenticated_api_client, customer):
        """Test that addresses are deleted when customer is deleted (CASCADE)"""
        address = baker.make(models.Address, customer=customer, street='Test St')
        address_id = address.id
        
        # Delete customer
        customer_id = customer.id
        url = reverse('customer-detail', kwargs={'pk': customer_id})
        response = authenticated_api_client.delete(url)
        
        assert response.status_code == status.HTTP_204_NO_CONTENT
        
        # Verify customer and address were deleted (CASCADE)
        assert not models.Customer.objects.filter(id=customer_id).exists()
        assert not models.Address.objects.filter(id=address_id).exists()


@pytest.mark.django_db
class TestCustomerByNameAction:
    """Tests for GET /api/customers/by_name/?name={name} - Custom action"""
    
    def test_by_name_unauthenticated(self, api_client):
        """Test that unauthenticated requests are rejected"""
        url = reverse('customer-by-name')
        response = api_client.get(url, {'name': 'John'})
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_by_name_success_first_name_match(self, authenticated_api_client):
        """Test getting customers by first name"""
        customer1 = baker.make(models.Customer, first_name='John', last_name='Doe')
        customer2 = baker.make(models.Customer, first_name='John', last_name='Smith')
        baker.make(models.Customer, first_name='Jane', last_name='Doe')  # Should not appear
        
        url = reverse('customer-by-name')
        response = authenticated_api_client.get(url, {'name': 'John'})
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2
        first_names = [c['first_name'] for c in response.data]
        assert 'John' in first_names
        assert 'Jane' not in first_names
    
    def test_by_name_success_last_name_match(self, authenticated_api_client):
        """Test getting customers by last name"""
        customer1 = baker.make(models.Customer, first_name='John', last_name='Smith')
        customer2 = baker.make(models.Customer, first_name='Jane', last_name='Smith')
        baker.make(models.Customer, first_name='John', last_name='Doe')  # Should not appear
        
        url = reverse('customer-by-name')
        response = authenticated_api_client.get(url, {'name': 'Smith'})
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2
        last_names = [c['last_name'] for c in response.data]
        assert all(name == 'Smith' for name in last_names)
    
    def test_by_name_success_partial_match(self, authenticated_api_client):
        """Test that by_name uses icontains (partial match)"""
        customer1 = baker.make(models.Customer, first_name='Johnny', last_name='Doe')
        customer2 = baker.make(models.Customer, first_name='Jane', last_name='Johnson')
        
        url = reverse('customer-by-name')
        response = authenticated_api_client.get(url, {'name': 'John'})
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2  # Matches both 'Johnny' and 'Johnson'
    
    def test_by_name_case_insensitive(self, authenticated_api_client):
        """Test that by_name is case insensitive"""
        customer = baker.make(models.Customer, first_name='John', last_name='Doe')
        
        url = reverse('customer-by-name')
        response = authenticated_api_client.get(url, {'name': 'john'})
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]['first_name'] == 'John'
    
    def test_by_name_empty_result(self, authenticated_api_client):
        """Test getting customers with no matches"""
        baker.make(models.Customer, first_name='John', last_name='Doe')
        
        url = reverse('customer-by-name')
        response = authenticated_api_client.get(url, {'name': 'NonExistent'})
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data == []
    
    def test_by_name_missing_parameter(self, authenticated_api_client):
        """Test by_name without name parameter"""
        url = reverse('customer-by-name')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data
        assert 'name' in response.data['error'].lower()
    
    def test_by_name_empty_string(self, authenticated_api_client):
        """Test by_name with empty string"""
        url = reverse('customer-by-name')
        response = authenticated_api_client.get(url, {'name': ''})
        
        # Should return 400 since empty string is falsy
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_by_name_multiple_customers(self, authenticated_api_client):
        """Test filtering works correctly with multiple customers"""
        # Create customers with different names
        customer1 = baker.make(models.Customer, first_name='Alice', last_name='Smith')
        customer2 = baker.make(models.Customer, first_name='Bob', last_name='Smith')
        customer3 = baker.make(models.Customer, first_name='Charlie', last_name='Brown')
        
        url = reverse('customer-by-name')
        response = authenticated_api_client.get(url, {'name': 'Smith'})
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2
        last_names = [c['last_name'] for c in response.data]
        assert all(name == 'Smith' for name in last_names)


@pytest.mark.django_db
class TestCustomerEdgeCases:
    """Tests for edge cases and special scenarios"""
    
    def test_customer_long_first_name(self, authenticated_api_client):
        """Test creating customer with very long first name"""
        url = reverse('customer-list')
        data = {
            'first_name': 'A' * 255,  # Max length
            'last_name': 'Doe',
            'phone_number': '1234567890'
        }
        response = authenticated_api_client.post(url, data)
        
        assert response.status_code == status.HTTP_201_CREATED
    
    def test_customer_first_name_exceeds_max_length(self, authenticated_api_client):
        """Test creating customer with first name exceeding max length"""
        url = reverse('customer-list')
        data = {
            'first_name': 'A' * 256,  # Exceeds max length
            'last_name': 'Doe',
            'phone_number': '1234567890'
        }
        response = authenticated_api_client.post(url, data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_customer_long_phone_number(self, authenticated_api_client):
        """Test creating customer with very long phone number"""
        url = reverse('customer-list')
        data = {
            'first_name': 'John',
            'last_name': 'Doe',
            'phone_number': '1' * 255  # Max length
        }
        response = authenticated_api_client.post(url, data)
        
        assert response.status_code == status.HTTP_201_CREATED
    
    def test_customer_unicode_characters(self, authenticated_api_client):
        """Test creating customer with unicode characters"""
        url = reverse('customer-list')
        data = {
            'first_name': 'José',
            'last_name': 'García-López',
            'phone_number': '1234567890'
        }
        response = authenticated_api_client.post(url, data)
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['first_name'] == 'José'
        assert response.data['last_name'] == 'García-López'
    
    def test_customer_phone_number_formats(self, authenticated_api_client):
        """Test creating customer with different phone number formats"""
        url = reverse('customer-list')
        data = {
            'first_name': 'John',
            'last_name': 'Doe',
            'phone_number': '+1-555-123-4567'  # Formatted phone number
        }
        response = authenticated_api_client.post(url, data)
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['phone_number'] == '+1-555-123-4567'
    
    def test_customer_relationship_with_addresses(self, authenticated_api_client, customer):
        """Test customer-address relationship"""
        address = baker.make(models.Address, customer=customer, street='Test St')
        
        # Verify relationship
        assert address.customer == customer
        assert address in customer.addresses.all()
        
        # Verify through API
        url = reverse('customer-detail', kwargs={'pk': customer.id})
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == customer.id

