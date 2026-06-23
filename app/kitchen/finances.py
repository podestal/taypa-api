from datetime import timedelta
from decimal import Decimal

from django.db.models import Q, Sum

from . import models


def _account_seed_balance(account):
    """Balance from account creation before any recorded transactions."""
    totals = models.Transaction.objects.filter(account=account).aggregate(
        income=Sum('amount', filter=Q(transaction_type='I')),
        expense=Sum('amount', filter=Q(transaction_type='E')),
    )
    income = totals['income'] or Decimal('0')
    expense = totals['expense'] or Decimal('0')
    return account.balance - income + expense


def _net_from_transactions(transactions):
    income = transactions.filter(transaction_type='I').aggregate(
        total=Sum('amount'),
    )['total'] or Decimal('0')
    expense = transactions.filter(transaction_type='E').aggregate(
        total=Sum('amount'),
    )['total'] or Decimal('0')
    return income - expense


def get_finance_report(start_date, end_date, account_id=None):
    accounts = models.Account.objects.all().order_by('name')
    if account_id:
        accounts = accounts.filter(pk=account_id)

    report = []
    for account in accounts:
        seed = _account_seed_balance(account)
        transactions = models.Transaction.objects.filter(
            account=account,
            transaction_date__lte=end_date,
        )
        prior_transactions = transactions.filter(transaction_date__lt=start_date)
        current_balance = seed + _net_from_transactions(prior_transactions)

        day = start_date
        while day <= end_date:
            day_transactions = transactions.filter(transaction_date=day)
            day_income = day_transactions.filter(transaction_type='I').aggregate(
                total=Sum('amount'),
            )['total'] or Decimal('0')
            day_expenses = day_transactions.filter(transaction_type='E').aggregate(
                total=Sum('amount'),
            )['total'] or Decimal('0')
            closing_balance = current_balance + day_income - day_expenses
            report.append({
                'date': day,
                'account_id': account.id,
                'account_name': account.name,
                'opening_balance': current_balance,
                'income': day_income,
                'expenses': day_expenses,
                'closing_balance': closing_balance,
            })
            current_balance = closing_balance
            day += timedelta(days=1)

    return report
