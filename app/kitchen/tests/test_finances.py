import pytest
from datetime import date, timedelta
from decimal import Decimal

from django.urls import reverse
from rest_framework import status


@pytest.mark.django_db
class TestFinanceReportAPI:
    def test_report_requires_date_range(self, authenticated_api_client):
        response = authenticated_api_client.get(reverse('kitchen-finance-report'))

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_report_shows_daily_opening_income_expenses_and_closing(
        self, authenticated_api_client, account
    ):
        today = date.today()
        yesterday = today - timedelta(days=1)

        authenticated_api_client.post(
            reverse('kitchen-transaction-list'),
            {
                'transaction_type': 'I',
                'account': account.id,
                'amount': '100.00',
                'transaction_date': str(yesterday),
                'description': 'Daily sales',
            },
            format='json',
        )
        authenticated_api_client.post(
            reverse('kitchen-transaction-list'),
            {
                'transaction_type': 'E',
                'account': account.id,
                'amount': '50.00',
                'transaction_date': str(today),
                'description': 'Supplies',
            },
            format='json',
        )

        response = authenticated_api_client.get(
            reverse('kitchen-finance-report'),
            {
                'start_date': str(yesterday),
                'end_date': str(today),
                'account_id': account.id,
            },
        )

        assert response.status_code == status.HTTP_200_OK
        results = {row['date']: row for row in response.data['results']}

        assert results[str(yesterday)]['opening_balance'] == '500.00'
        assert results[str(yesterday)]['income'] == '100.00'
        assert results[str(yesterday)]['expenses'] == '0.00'
        assert results[str(yesterday)]['closing_balance'] == '600.00'

        assert results[str(today)]['opening_balance'] == '600.00'
        assert results[str(today)]['income'] == '0.00'
        assert results[str(today)]['expenses'] == '50.00'
        assert results[str(today)]['closing_balance'] == '550.00'

    def test_report_without_account_returns_all_accounts(
        self, authenticated_api_client, account, second_account
    ):
        today = date.today()

        response = authenticated_api_client.get(
            reverse('kitchen-finance-report'),
            {
                'start_date': str(today),
                'end_date': str(today),
            },
        )

        assert response.status_code == status.HTTP_200_OK
        account_ids = {row['account_id'] for row in response.data['results']}
        assert account.id in account_ids
        assert second_account.id in account_ids

    def test_report_unknown_account_returns_404(self, authenticated_api_client):
        today = date.today()

        response = authenticated_api_client.get(
            reverse('kitchen-finance-report'),
            {
                'start_date': str(today),
                'end_date': str(today),
                'account_id': 99999,
            },
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
