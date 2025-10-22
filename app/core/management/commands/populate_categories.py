# create categories

from django.core.management.base import BaseCommand
from store.models import Category


class Command(BaseCommand):
    help = 'Populate categories'

    def handle(self, *args, **options):
        categories = [
            'Pollo',
            'Burger',
            'Salchipapa',
            'Bebidas'
        ]
        for category in categories:
            Category.objects.create(
                name=category,
                description=f'Description of {category}')
        self.stdout.write(self.style.SUCCESS(
            f'{len(categories)} Categories created successfully'))
