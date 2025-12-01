import pytest
from decimal import Decimal
from datetime import date
from model_bakery import baker
from rest_framework import status
from django.urls import reverse

from store import models

# Fixtures are imported from conftest.py automatically by pytest


@pytest.mark.django_db
class TestOrderTransactionCreation:
    """Tests for automatic transaction creation when order status changes to HA or DO"""
    
    def test_update_order_status_to_handed_creates_transaction(self, authenticated_api_client, user, category, dish):
        """Test that updating order status to 'HA' creates an income transaction"""
        # Create account
        account = baker.make(
            models.Account,
            name='Test Account',
            balance=Decimal('0.00'),
            is_active=True
        )
        
        # Create order with items
        order = baker.make(
            models.Order,
            status='IP',
            created_by=user
        )
        
        # Create order items
        # Note: price is the total price for the item (already includes quantity)
        baker.make(
            models.OrderItem,
            order=order,
            dish=dish,
            price=Decimal('50.00'),  # Total for 2 items
            quantity=2,
            category=category
        )
        baker.make(
            models.OrderItem,
            order=order,
            dish=dish,
            price=Decimal('15.00'),  # Total for 1 item
            quantity=1,
            category=category
        )
        # Total: 50.00 + 15.00 = 65.00
        
        initial_balance = account.balance
        initial_transaction_count = models.Transaction.objects.count()
        
        # Update order status to 'HA'
        url = reverse('order-detail', kwargs={'pk': order.id})
        response = authenticated_api_client.patch(url, {'status': 'HA'})
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'HA'
        
        # Verify transaction was created
        assert models.Transaction.objects.count() == initial_transaction_count + 1
        
        transaction = models.Transaction.objects.filter(
            description__contains=f"Order {order.order_number}"
        ).first()
        
        assert transaction is not None
        assert transaction.transaction_type == 'I'  # Income
        assert transaction.amount == Decimal('65.00')  # Total of order items
        assert transaction.account == account
        assert transaction.created_by == user
        assert transaction.transaction_date == date.today()
        assert f"Order {order.order_number}" in transaction.description
        assert "Handed" in transaction.description
        
        # Verify account balance was updated
        account.refresh_from_db()
        assert account.balance == initial_balance + Decimal('65.00')
    
    def test_update_order_status_to_delivered_creates_transaction(self, authenticated_api_client, user, category, dish):
        """Test that updating order status to 'DO' creates an income transaction"""
        # Create account
        account = baker.make(
            models.Account,
            name='Test Account',
            balance=Decimal('100.00'),
            is_active=True
        )
        
        # Create order with items
        order = baker.make(
            models.Order,
            status='IT',  # In Transit
            created_by=user
        )
        
        # Create order items
        # Note: price is the total price for the item (already includes quantity)
        baker.make(
            models.OrderItem,
            order=order,
            dish=dish,
            price=Decimal('90.00'),  # Total for 3 items
            quantity=3,
            category=category
        )
        # Total: 90.00
        
        initial_balance = account.balance
        initial_transaction_count = models.Transaction.objects.count()
        
        # Update order status to 'DO'
        url = reverse('order-detail', kwargs={'pk': order.id})
        response = authenticated_api_client.patch(url, {'status': 'DO'})
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'DO'
        
        # Verify transaction was created
        assert models.Transaction.objects.count() == initial_transaction_count + 1
        
        transaction = models.Transaction.objects.filter(
            description__contains=f"Order {order.order_number}"
        ).first()
        
        assert transaction is not None
        assert transaction.transaction_type == 'I'  # Income
        assert transaction.amount == Decimal('90.00')  # Total of order items
        assert transaction.account == account
        assert transaction.created_by == user
        assert f"Order {order.order_number}" in transaction.description
        assert "Delivered" in transaction.description
        
        # Verify account balance was updated
        account.refresh_from_db()
        assert account.balance == initial_balance + Decimal('90.00')
    
    def test_update_order_status_no_transaction_for_other_statuses(self, authenticated_api_client, user, category, dish):
        """Test that updating order status to other values does not create a transaction"""
        # Create account
        account = baker.make(
            models.Account,
            name='Test Account',
            balance=Decimal('0.00'),
            is_active=True
        )
        
        # Create order with items
        order = baker.make(
            models.Order,
            status='IP',
            created_by=user
        )
        
        baker.make(
            models.OrderItem,
            order=order,
            dish=dish,
            price=Decimal('20.00'),
            quantity=1,
            category=category
        )
        
        initial_transaction_count = models.Transaction.objects.count()
        
        # Update order status to 'IK' (In Kitchen) - should NOT create transaction
        url = reverse('order-detail', kwargs={'pk': order.id})
        response = authenticated_api_client.patch(url, {'status': 'IK'})
        
        assert response.status_code == status.HTTP_200_OK
        
        # Verify NO transaction was created
        assert models.Transaction.objects.count() == initial_transaction_count
        
        # Try other statuses
        for other_status in ['PA', 'IT', 'CA']:
            response = authenticated_api_client.patch(url, {'status': other_status})
            assert response.status_code == status.HTTP_200_OK
        
        # Still no transactions should be created
        assert models.Transaction.objects.count() == initial_transaction_count
    
    def test_update_order_status_no_duplicate_transactions(self, authenticated_api_client, user, category, dish):
        """Test that updating order status multiple times does not create duplicate transactions"""
        # Create account
        account = baker.make(
            models.Account,
            name='Test Account',
            balance=Decimal('0.00'),
            is_active=True
        )
        
        # Create order with items
        order = baker.make(
            models.Order,
            status='IP',
            created_by=user
        )
        
        baker.make(
            models.OrderItem,
            order=order,
            dish=dish,
            price=Decimal('50.00'),
            quantity=1,
            category=category
        )
        
        url = reverse('order-detail', kwargs={'pk': order.id})
        
        # First update to 'HA' - should create transaction
        response = authenticated_api_client.patch(url, {'status': 'HA'})
        assert response.status_code == status.HTTP_200_OK
        
        transaction_count_after_first = models.Transaction.objects.count()
        assert transaction_count_after_first == 1
        
        # Update to 'DO' - should NOT create another transaction
        response = authenticated_api_client.patch(url, {'status': 'DO'})
        assert response.status_code == status.HTTP_200_OK
        
        # Still only one transaction
        assert models.Transaction.objects.count() == transaction_count_after_first
        
        # Update back to 'HA' - should NOT create another transaction
        response = authenticated_api_client.patch(url, {'status': 'HA'})
        assert response.status_code == status.HTTP_200_OK
        
        # Still only one transaction
        assert models.Transaction.objects.count() == transaction_count_after_first
    
    def test_update_order_creates_default_account_if_none_exists(self, authenticated_api_client, user, category, dish):
        """Test that a default account is created if no active account exists"""
        # Ensure no accounts exist
        models.Account.objects.all().delete()
        
        # Create order with items
        order = baker.make(
            models.Order,
            status='IP',
            created_by=user
        )
        
        baker.make(
            models.OrderItem,
            order=order,
            dish=dish,
            price=Decimal('40.00'),
            quantity=1,
            category=category
        )
        
        # Update order status to 'HA'
        url = reverse('order-detail', kwargs={'pk': order.id})
        response = authenticated_api_client.patch(url, {'status': 'HA'})
        
        assert response.status_code == status.HTTP_200_OK
        
        # Verify default account was created
        default_account = models.Account.objects.filter(name='Default Account').first()
        assert default_account is not None
        assert default_account.is_active is True
        assert default_account.account_type == 'CH'
        
        # Verify transaction was created with default account
        transaction = models.Transaction.objects.filter(
            description__contains=f"Order {order.order_number}"
        ).first()
        
        assert transaction is not None
        assert transaction.account == default_account
        assert transaction.amount == Decimal('40.00')
    
    def test_update_order_transaction_uses_existing_active_account(self, authenticated_api_client, user, category, dish):
        """Test that transaction uses the first active account if multiple exist"""
        # Create multiple accounts
        account1 = baker.make(
            models.Account,
            name='Account 1',
            balance=Decimal('0.00'),
            is_active=True
        )
        account2 = baker.make(
            models.Account,
            name='Account 2',
            balance=Decimal('0.00'),
            is_active=True
        )
        
        # Create order with items
        order = baker.make(
            models.Order,
            status='IP',
            created_by=user
        )
        
        baker.make(
            models.OrderItem,
            order=order,
            dish=dish,
            price=Decimal('35.00'),
            quantity=1,
            category=category
        )
        
        # Update order status to 'HA'
        url = reverse('order-detail', kwargs={'pk': order.id})
        response = authenticated_api_client.patch(url, {'status': 'HA'})
        
        assert response.status_code == status.HTTP_200_OK
        
        # Verify transaction was created with first active account
        transaction = models.Transaction.objects.filter(
            description__contains=f"Order {order.order_number}"
        ).first()
        
        assert transaction is not None
        # Should use the first active account (account1, created first)
        assert transaction.account in [account1, account2]
        
        # Verify balance was updated on the account used
        transaction.account.refresh_from_db()
        assert transaction.account.balance == Decimal('35.00')
    
    def test_update_order_with_no_items_creates_zero_transaction(self, authenticated_api_client, user):
        """Test that updating order status creates transaction even if order has no items"""
        # Create account
        account = baker.make(
            models.Account,
            name='Test Account',
            balance=Decimal('0.00'),
            is_active=True
        )
        
        # Create order without items
        order = baker.make(
            models.Order,
            status='IP',
            created_by=user
        )
        
        initial_balance = account.balance
        
        # Update order status to 'HA'
        url = reverse('order-detail', kwargs={'pk': order.id})
        response = authenticated_api_client.patch(url, {'status': 'HA'})
        
        assert response.status_code == status.HTTP_200_OK
        
        # Verify transaction was created with zero amount
        transaction = models.Transaction.objects.filter(
            description__contains=f"Order {order.order_number}"
        ).first()
        
        assert transaction is not None
        assert transaction.amount == Decimal('0.00')
        
        # Verify account balance remains unchanged
        account.refresh_from_db()
        assert account.balance == initial_balance
    
    def test_update_order_status_from_ha_to_do_no_new_transaction(self, authenticated_api_client, user, category, dish):
        """Test that changing from HA to DO does not create a new transaction"""
        # Create account
        account = baker.make(
            models.Account,
            name='Test Account',
            balance=Decimal('0.00'),
            is_active=True
        )
        
        # Create order with items
        order = baker.make(
            models.Order,
            status='IP',
            created_by=user
        )
        
        baker.make(
            models.OrderItem,
            order=order,
            dish=dish,
            price=Decimal('25.00'),
            quantity=1,
            category=category
        )
        
        url = reverse('order-detail', kwargs={'pk': order.id})
        
        # Update to 'HA' - creates transaction
        response = authenticated_api_client.patch(url, {'status': 'HA'})
        assert response.status_code == status.HTTP_200_OK
        
        transaction_count = models.Transaction.objects.count()
        assert transaction_count == 1
        
        # Update to 'DO' - should NOT create new transaction
        response = authenticated_api_client.patch(url, {'status': 'DO'})
        assert response.status_code == status.HTTP_200_OK
        
        # Still only one transaction
        assert models.Transaction.objects.count() == transaction_count

