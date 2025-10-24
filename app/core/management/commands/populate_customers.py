from store.models import Customer
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Populate customers'

    def handle(self, *args, **options):
        customers = [
            {
                'first_name': 'Jose',
                'last_name': 'Perez',
                'phone_number': '1234567890',
            },
            {
                'first_name': 'Maria',
                'last_name': 'Gomez',
                'phone_number': '1234567890',
            },
            {
                'first_name': 'Pedro',
                'last_name': 'Garcia',
                'phone_number': '1234567890',
            },
            {
                'first_name': 'Ana',
                'last_name': 'Lopez',
                'phone_number': '1234567890',
            },
            {
                'first_name': 'Luis',
                'last_name': 'Martinez',
                'phone_number': '1234567890',
            },
            {
                'first_name': 'Carlos',
                'last_name': 'Rodriguez',
                'phone_number': '1234567890',
            },
            {
                'first_name': 'Rosa',
                'last_name': 'Gonzalez',
                'phone_number': '1234567890',
            },
            {
                'first_name': 'Jorge',
                'last_name': 'Lopez',
                'phone_number': '1234567890',
            },
            {
                'first_name': 'Mario',
                'last_name': 'Garcia',
                'phone_number': '1234567890',
            },
        ]
        for customer in customers:
            Customer.objects.create(**customer)
            self.stdout.write(
                self.style.SUCCESS
                (f'{len(customers)} customers created successfully'))
