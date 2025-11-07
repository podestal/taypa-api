from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from store.models import Account, Transaction, Category
from decimal import Decimal
from datetime import date, timedelta
import random

User = get_user_model()


class Command(BaseCommand):
    help = 'Populate transactions for the last 3 months (5 transactions per day)'

    def handle(self, *args, **options):
        # Get or create account
        account, created = Account.objects.get_or_create(
            name='Main Account',
            defaults={
                'balance': Decimal('5000.00'),
                'account_type': 'CH',
                'is_active': True
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'Created account: {account}'))
        else:
            self.stdout.write(f'Using existing account: {account}')
            # Reset balance for clean start
            account.balance = Decimal('5000.00')
            account.save()

        # Get or create user
        user = User.objects.filter(is_superuser=True).first()
        if not user:
            user = User.objects.first()
        if not user:
            self.stdout.write(self.style.ERROR('No user found. Please create a user first.'))
            return

        # Get or create categories
        categories = Category.objects.all()

        # Income and expense descriptions
        income_descriptions = [
            'Salary payment',
            'Freelance project',
            'Client payment',
            'Consulting fee',
            'Part-time work',
            'Online sale',
            'Service payment',
            'Bonus payment',
        ]
        
        expense_descriptions = [
            'Grocery shopping',
            'Restaurant meal',
            'Gas station',
            'Uber ride',
            'Electricity bill',
            'Water bill',
            'Internet subscription',
            'Coffee shop',
            'Pharmacy',
            'Clothing store',
            'Movie tickets',
            'Concert tickets',
            'Gym membership',
            'Phone bill',
            'Supermarket',
        ]

        # Transaction amounts (small and medium)
        small_amounts = [Decimal(str(round(random.uniform(5.00, 50.00), 2))) for _ in range(20)]
        medium_amounts = [Decimal(str(round(random.uniform(50.00, 300.00), 2))) for _ in range(20)]
        
        # Income amounts (tend to be larger)
        income_small = [Decimal(str(round(random.uniform(50.00, 200.00), 2))) for _ in range(20)]
        income_medium = [Decimal(str(round(random.uniform(200.00, 800.00), 2))) for _ in range(20)]

        # Generate transactions for the last 3 months
        end_date = date.today()
        start_date = end_date - timedelta(days=90)
        
        total_income = Decimal('0.00')
        total_expenses = Decimal('0.00')
        transactions_created = 0
        
        current_date = start_date
        while current_date <= end_date:
            # 5 transactions per day
            for _ in range(5):
                # 60% income, 40% expenses to ensure positive balance
                is_income = random.random() < 0.60
                
                if is_income:
                    transaction_type = 'I'
                    amount = random.choice(income_small + income_medium)
                    description = random.choice(income_descriptions)
                    total_income += amount
                else:
                    transaction_type = 'E'
                    amount = random.choice(small_amounts + medium_amounts)
                    description = random.choice(expense_descriptions)
                    total_expenses += amount
                
                # Random category
                category = random.choice(categories) if random.random() < 0.8 else None
                
                # Create transaction (balance will be updated automatically by save method)
                Transaction.objects.create(
                    transaction_type=transaction_type,
                    account=account,
                    amount=amount,
                    category=category,
                    description=description,
                    transaction_date=current_date,
                    created_by=user
                )
                transactions_created += 1
            
            current_date += timedelta(days=1)

        # Refresh account to get updated balance
        account.refresh_from_db()
        
        self.stdout.write(self.style.SUCCESS(
            f'\nSuccessfully created {transactions_created} transactions!'
        ))
        self.stdout.write(f'Date range: {start_date} to {end_date}')
        self.stdout.write(f'Total income: ${total_income:,.2f}')
        self.stdout.write(f'Total expenses: ${total_expenses:,.2f}')
        self.stdout.write(f'Net: ${total_income - total_expenses:,.2f}')
        self.stdout.write(f'Final account balance: ${account.balance:,.2f}')
        
        if account.balance > 0:
            self.stdout.write(self.style.SUCCESS('✓ Account balance is positive!'))
        else:
            self.stdout.write(self.style.WARNING('⚠ Account balance is negative!'))

