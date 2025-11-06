import pytest
from decimal import Decimal
from datetime import date, timedelta
from model_bakery import baker
from rest_framework import status
from django.urls import reverse

from store import models

# Fixtures are imported from conftest.py automatically by pytest


@pytest.mark.django_db
class TestTransactionListView:
    """Tests for GET /api/transactions/ - List all transactions"""
    
    def test_list_transactions_unauthenticated(self, api_client):
        """Test that unauthenticated requests are rejected"""
        url = reverse('transaction-list')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_list_transactions_empty(self, authenticated_api_client):
        """Test listing transactions when none exist"""
        url = reverse('transaction-list')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert 'results' in response.data or isinstance(response.data, list)
        if 'results' in response.data:
            assert response.data['results'] == []
        else:
            assert response.data == []
    
    def test_list_transactions_single(self, authenticated_api_client, transaction):
        """Test listing a single transaction"""
        url = reverse('transaction-list')
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
        assert len(data) == 1
        assert data[0]['transaction_type'] == 'I'
        assert data[0]['amount'] == '100.00'
    
    def test_list_transactions_filter_by_type_income(self, authenticated_api_client, account, user, category):
        """Test filtering transactions by type - Income only"""
        # Create income and expense transactions
        baker.make(models.Transaction, transaction_type='I', account=account, amount=Decimal('100.00'), created_by=user)
        baker.make(models.Transaction, transaction_type='E', account=account, amount=Decimal('50.00'), created_by=user)
        
        url = reverse('transaction-list')
        response = authenticated_api_client.get(url, {'transaction_type': 'I'})
        
        assert response.status_code == status.HTTP_200_OK
        data = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
        assert len(data) == 1
        assert all(t['transaction_type'] == 'I' for t in data)
    
    def test_list_transactions_filter_by_type_expense(self, authenticated_api_client, account, user, category):
        """Test filtering transactions by type - Expense only"""
        # Create income and expense transactions
        baker.make(models.Transaction, transaction_type='I', account=account, amount=Decimal('100.00'), created_by=user)
        baker.make(models.Transaction, transaction_type='E', account=account, amount=Decimal('50.00'), created_by=user)
        
        url = reverse('transaction-list')
        response = authenticated_api_client.get(url, {'transaction_type': 'E'})
        
        assert response.status_code == status.HTTP_200_OK
        data = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
        assert len(data) == 1
        assert all(t['transaction_type'] == 'E' for t in data)
    
    def test_list_transactions_filter_by_type_all(self, authenticated_api_client, account, user, category):
        """Test filtering transactions by type - All"""
        # Create income and expense transactions
        baker.make(models.Transaction, transaction_type='I', account=account, amount=Decimal('100.00'), created_by=user)
        baker.make(models.Transaction, transaction_type='E', account=account, amount=Decimal('50.00'), created_by=user)
        
        url = reverse('transaction-list')
        response = authenticated_api_client.get(url, {'transaction_type': 'all'})
        
        assert response.status_code == status.HTTP_200_OK
        data = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
        assert len(data) == 2
    
    def test_list_transactions_filter_by_type_invalid(self, authenticated_api_client):
        """Test filtering with invalid transaction type"""
        url = reverse('transaction-list')
        response = authenticated_api_client.get(url, {'transaction_type': 'invalid'})
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data
    
    def test_list_transactions_filter_by_date_today(self, authenticated_api_client, account, user, category):
        """Test filtering transactions by date - Today"""
        # Create transaction for today
        baker.make(
            models.Transaction,
            transaction_type='I',
            account=account,
            amount=Decimal('100.00'),
            transaction_date=date.today(),
            created_by=user
        )
        # Create transaction for yesterday
        baker.make(
            models.Transaction,
            transaction_type='I',
            account=account,
            amount=Decimal('50.00'),
            transaction_date=date.today() - timedelta(days=1),
            created_by=user
        )
        
        url = reverse('transaction-list')
        response = authenticated_api_client.get(url, {'date_filter': 'today'})
        
        assert response.status_code == status.HTTP_200_OK
        data = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
        assert len(data) == 1
        assert data[0]['transaction_date'] == str(date.today())
    
    def test_list_transactions_filter_by_date_last7days(self, authenticated_api_client, account, user, category):
        """Test filtering transactions by date - Last 7 days"""
        # Create transaction 5 days ago (should be included)
        baker.make(
            models.Transaction,
            transaction_type='I',
            account=account,
            amount=Decimal('100.00'),
            transaction_date=date.today() - timedelta(days=5),
            created_by=user
        )
        # Create transaction 10 days ago (should NOT be included)
        baker.make(
            models.Transaction,
            transaction_type='I',
            account=account,
            amount=Decimal('50.00'),
            transaction_date=date.today() - timedelta(days=10),
            created_by=user
        )
        
        url = reverse('transaction-list')
        response = authenticated_api_client.get(url, {'date_filter': 'last7days'})
        
        assert response.status_code == status.HTTP_200_OK
        data = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
        assert len(data) == 1
    
    def test_list_transactions_filter_by_date_this_month(self, authenticated_api_client, account, user, category):
        """Test filtering transactions by date - This month"""
        # Create transaction this month
        baker.make(
            models.Transaction,
            transaction_type='I',
            account=account,
            amount=Decimal('100.00'),
            transaction_date=date.today().replace(day=15),
            created_by=user
        )
        # Create transaction last month
        last_month = date.today().replace(day=1) - timedelta(days=1)
        baker.make(
            models.Transaction,
            transaction_type='I',
            account=account,
            amount=Decimal('50.00'),
            transaction_date=last_month,
            created_by=user
        )
        
        url = reverse('transaction-list')
        response = authenticated_api_client.get(url, {'date_filter': 'thisMonth'})
        
        assert response.status_code == status.HTTP_200_OK
        data = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
        assert len(data) == 1
    
    def test_list_transactions_filter_by_date_custom(self, authenticated_api_client, account, user, category):
        """Test filtering transactions by date - Custom range"""
        start_date = date.today() - timedelta(days=10)
        end_date = date.today() - timedelta(days=5)
        
        # Create transaction in range
        baker.make(
            models.Transaction,
            transaction_type='I',
            account=account,
            amount=Decimal('100.00'),
            transaction_date=date.today() - timedelta(days=7),
            created_by=user
        )
        # Create transaction outside range
        baker.make(
            models.Transaction,
            transaction_type='I',
            account=account,
            amount=Decimal('50.00'),
            transaction_date=date.today() - timedelta(days=15),
            created_by=user
        )
        
        url = reverse('transaction-list')
        response = authenticated_api_client.get(url, {
            'date_filter': 'custom',
            'start_date': str(start_date),
            'end_date': str(end_date)
        })
        
        assert response.status_code == status.HTTP_200_OK
        data = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
        assert len(data) == 1
    
    def test_list_transactions_filter_by_date_custom_missing_params(self, authenticated_api_client):
        """Test custom date filter without required parameters"""
        url = reverse('transaction-list')
        response = authenticated_api_client.get(url, {'date_filter': 'custom'})
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data
    
    def test_list_transactions_combined_filters(self, authenticated_api_client, account, user, category):
        """Test combining transaction_type and date filters"""
        # Create income today
        baker.make(
            models.Transaction,
            transaction_type='I',
            account=account,
            amount=Decimal('100.00'),
            transaction_date=date.today(),
            created_by=user
        )
        # Create expense today
        baker.make(
            models.Transaction,
            transaction_type='E',
            account=account,
            amount=Decimal('50.00'),
            transaction_date=date.today(),
            created_by=user
        )
        # Create income yesterday
        baker.make(
            models.Transaction,
            transaction_type='I',
            account=account,
            amount=Decimal('75.00'),
            transaction_date=date.today() - timedelta(days=1),
            created_by=user
        )
        
        url = reverse('transaction-list')
        response = authenticated_api_client.get(url, {
            'transaction_type': 'I',
            'date_filter': 'today'
        })
        
        assert response.status_code == status.HTTP_200_OK
        data = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
        assert len(data) == 1
        assert data[0]['transaction_type'] == 'I'
        assert data[0]['transaction_date'] == str(date.today())


@pytest.mark.django_db
class TestTransactionCreateView:
    """Tests for POST /api/transactions/ - Create transaction"""
    
    def test_create_transaction_unauthenticated(self, api_client, account, category):
        """Test that unauthenticated requests are rejected"""
        url = reverse('transaction-list')
        data = {
            'transaction_type': 'I',
            'account': account.id,
            'amount': '100.00',
            'category': category.id
        }
        response = api_client.post(url, data)
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_create_transaction_income_success(self, authenticated_api_client, account, user, category):
        """Test creating an income transaction successfully"""
        initial_balance = account.balance
        
        url = reverse('transaction-list')
        data = {
            'transaction_type': 'I',
            'account': account.id,
            'amount': '100.00',
            'category': category.id,
            'description': 'Test income',
            'transaction_date': str(date.today())
        }
        response = authenticated_api_client.post(url, data)
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['transaction_type'] == 'I'
        assert response.data['amount'] == '100.00'
        
        # Verify account balance was updated
        account.refresh_from_db()
        assert account.balance == initial_balance + Decimal('100.00')
    
    def test_create_transaction_expense_success(self, authenticated_api_client, account, user, category):
        """Test creating an expense transaction successfully"""
        initial_balance = account.balance
        
        url = reverse('transaction-list')
        data = {
            'transaction_type': 'E',
            'account': account.id,
            'amount': '50.00',
            'category': category.id,
            'description': 'Test expense',
            'transaction_date': str(date.today())
        }
        response = authenticated_api_client.post(url, data)
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['transaction_type'] == 'E'
        assert response.data['amount'] == '50.00'
        
        # Verify account balance was updated
        account.refresh_from_db()
        assert account.balance == initial_balance - Decimal('50.00')
    
    def test_create_transaction_missing_required_fields(self, authenticated_api_client, account):
        """Test creating transaction without required fields"""
        url = reverse('transaction-list')
        data = {
            'account': account.id,
            'amount': '100.00'
        }
        response = authenticated_api_client.post(url, data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_create_transaction_invalid_account(self, authenticated_api_client, category):
        """Test creating transaction with non-existent account"""
        url = reverse('transaction-list')
        data = {
            'transaction_type': 'I',
            'account': 99999,
            'amount': '100.00',
            'category': category.id
        }
        response = authenticated_api_client.post(url, data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_create_transaction_invalid_type(self, authenticated_api_client, account, category):
        """Test creating transaction with invalid transaction type"""
        url = reverse('transaction-list')
        data = {
            'transaction_type': 'INVALID',
            'account': account.id,
            'amount': '100.00',
            'category': category.id
        }
        response = authenticated_api_client.post(url, data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestTransactionDetailView:
    """Tests for GET /api/transactions/{id}/ - Retrieve transaction"""
    
    def test_retrieve_transaction_unauthenticated(self, api_client, transaction):
        """Test that unauthenticated requests are rejected"""
        url = reverse('transaction-detail', kwargs={'pk': transaction.id})
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_retrieve_transaction_success(self, authenticated_api_client, transaction):
        """Test retrieving a transaction successfully"""
        url = reverse('transaction-detail', kwargs={'pk': transaction.id})
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == transaction.id
        assert response.data['transaction_type'] == 'I'
        assert response.data['amount'] == '100.00'
    
    def test_retrieve_transaction_not_found(self, authenticated_api_client):
        """Test retrieving non-existent transaction"""
        url = reverse('transaction-detail', kwargs={'pk': 99999})
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestTransactionUpdateView:
    """Tests for PUT/PATCH /api/transactions/{id}/ - Update transaction"""
    
    def test_update_transaction_unauthenticated(self, api_client, transaction):
        """Test that unauthenticated requests are rejected"""
        url = reverse('transaction-detail', kwargs={'pk': transaction.id})
        data = {'amount': '200.00'}
        response = api_client.patch(url, data)
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_update_transaction_amount(self, authenticated_api_client, transaction, account):
        """Test updating transaction amount and verify balance correction"""
        initial_balance = account.balance
        old_amount = transaction.amount
        
        url = reverse('transaction-detail', kwargs={'pk': transaction.id})
        data = {'amount': '150.00'}
        response = authenticated_api_client.patch(url, data)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['amount'] == '150.00'
        
        # Verify balance was corrected (old amount reversed, new amount applied)
        account.refresh_from_db()
        expected_balance = initial_balance - old_amount + Decimal('150.00')
        assert account.balance == expected_balance
    
    def test_update_transaction_type(self, authenticated_api_client, transaction, account):
        """Test updating transaction type and verify balance correction"""
        initial_balance = account.balance
        old_amount = transaction.amount
        
        url = reverse('transaction-detail', kwargs={'pk': transaction.id})
        data = {'transaction_type': 'E'}  # Change from Income to Expense
        response = authenticated_api_client.patch(url, data)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['transaction_type'] == 'E'
        
        # Verify balance was corrected
        # Old: +100 (income), New: -100 (expense) = -200 total change
        account.refresh_from_db()
        expected_balance = initial_balance - (old_amount * 2)  # Reversed income, applied expense
        assert account.balance == expected_balance
    
    def test_update_transaction_full_put(self, authenticated_api_client, transaction, account, category):
        """Test full update (PUT) of transaction"""
        initial_balance = account.balance
        
        url = reverse('transaction-detail', kwargs={'pk': transaction.id})
        data = {
            'transaction_type': 'E',
            'account': account.id,
            'amount': '75.00',
            'category': category.id,
            'description': 'Updated transaction',
            'transaction_date': str(date.today())
        }
        response = authenticated_api_client.put(url, data)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['transaction_type'] == 'E'
        assert response.data['amount'] == '75.00'
        assert response.data['description'] == 'Updated transaction'
        
        # Verify balance was updated
        account.refresh_from_db()
        # Old: +100 (income), New: -75 (expense) = -175 total change
        expected_balance = initial_balance - Decimal('100.00') - Decimal('75.00')
        assert account.balance == expected_balance
    
    def test_update_transaction_not_found(self, authenticated_api_client):
        """Test updating non-existent transaction"""
        url = reverse('transaction-detail', kwargs={'pk': 99999})
        data = {'amount': '200.00'}
        response = authenticated_api_client.patch(url, data)
        
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestTransactionDeleteView:
    """Tests for DELETE /api/transactions/{id}/ - Delete transaction"""
    
    def test_delete_transaction_unauthenticated(self, api_client, transaction):
        """Test that unauthenticated requests are rejected"""
        url = reverse('transaction-detail', kwargs={'pk': transaction.id})
        response = api_client.delete(url)
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_delete_transaction_income_reverses_balance(self, authenticated_api_client, account, user, category):
        """Test deleting income transaction reverses balance correctly"""
        initial_balance = account.balance
        
        # Create an income transaction
        transaction = baker.make(
            models.Transaction,
            transaction_type='I',
            account=account,
            amount=Decimal('200.00'),
            created_by=user
        )
        
        # Verify balance increased
        account.refresh_from_db()
        assert account.balance == initial_balance + Decimal('200.00')
        
        # Delete the transaction
        url = reverse('transaction-detail', kwargs={'pk': transaction.id})
        response = authenticated_api_client.delete(url)
        
        assert response.status_code == status.HTTP_204_NO_CONTENT
        
        # Verify balance was reversed
        account.refresh_from_db()
        assert account.balance == initial_balance
    
    def test_delete_transaction_expense_reverses_balance(self, authenticated_api_client, account, user, category):
        """Test deleting expense transaction reverses balance correctly"""
        initial_balance = account.balance
        
        # Create an expense transaction
        transaction = baker.make(
            models.Transaction,
            transaction_type='E',
            account=account,
            amount=Decimal('150.00'),
            created_by=user
        )
        
        # Verify balance decreased
        account.refresh_from_db()
        assert account.balance == initial_balance - Decimal('150.00')
        
        # Delete the transaction
        url = reverse('transaction-detail', kwargs={'pk': transaction.id})
        response = authenticated_api_client.delete(url)
        
        assert response.status_code == status.HTTP_204_NO_CONTENT
        
        # Verify balance was reversed
        account.refresh_from_db()
        assert account.balance == initial_balance
    
    def test_delete_transaction_not_found(self, authenticated_api_client):
        """Test deleting non-existent transaction"""
        url = reverse('transaction-detail', kwargs={'pk': 99999})
        response = authenticated_api_client.delete(url)
        
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestTransactionBalanceUpdates:
    """Tests for automatic balance updates"""
    
    def test_multiple_transactions_update_balance_correctly(self, authenticated_api_client, account, user, category):
        """Test that multiple transactions update balance correctly"""
        initial_balance = account.balance
        
        # Create income
        url = reverse('transaction-list')
        data1 = {
            'transaction_type': 'I',
            'account': account.id,
            'amount': '500.00',
            'category': category.id
        }
        response1 = authenticated_api_client.post(url, data1)
        assert response1.status_code == status.HTTP_201_CREATED
        
        # Create expense
        data2 = {
            'transaction_type': 'E',
            'account': account.id,
            'amount': '200.00',
            'category': category.id
        }
        response2 = authenticated_api_client.post(url, data2)
        assert response2.status_code == status.HTTP_201_CREATED
        
        # Verify final balance
        account.refresh_from_db()
        expected_balance = initial_balance + Decimal('500.00') - Decimal('200.00')
        assert account.balance == expected_balance
    
    def test_transaction_includes_all_fields(self, authenticated_api_client, transaction):
        """Test that all fields are included in response"""
        url = reverse('transaction-detail', kwargs={'pk': transaction.id})
        response = authenticated_api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert 'id' in data
        assert 'transaction_type' in data
        assert 'account' in data
        assert 'amount' in data
        assert 'category' in data
        assert 'description' in data
        assert 'transaction_date' in data
        assert 'created_at' in data
        assert 'updated_at' in data
        assert 'created_by' in data

