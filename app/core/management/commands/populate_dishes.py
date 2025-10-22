# populate dishes

from django.core.management.base import BaseCommand
from store.models import Dish, Category


class Command(BaseCommand):
    help = 'Populate dishes'

    def handle(self, *args, **options):
        categories = Category.objects.all()
        dishes = [
        { 
            'name': 'Personal', 
            'price': 9.99, 
            'description': 'La hamburguesa tradicional con carne jugosa, lechuga, tomate, cebolla y nuestra salsa especial.', 
            'category': 1
        },
        { 
            'name': 'Mediano', 
            'price': 11.99, 
            'description': 'Nuestra clásica hamburguesa, con tocino, queso y huevo frito perfecta para los amantes del breakfast.', 
            'category': 1
        },
        { 
            'name': 'Grande', 
            'price': 13.99, 
            'description': 'Deliciosa hamburguesa con carne de res, chorizo parrillero y nuestro chimichurri especial.', 
            'category': 1
        },
        { 
            'name': 'Familiar', 
            'price': 15.99, 
            'description': 'Para los más hambrientos. Doble porción de carne, doble queso y todos los ingredientes.', 
            'category': 1
        },
        { 
            'name': 'La Clásica', 
            'price': 9.99, 
            'description': 'La hamburguesa tradicional con carne jugosa, lechuga, tomate, cebolla y nuestra salsa especial.', 
            'category': 2
        },
        {
            'name': 'La Royal', 
            'price': 11.99, 
            'description': 'Nuestra clásica hamburguesa, con tocino, queso y huevo frito perfecta para los amantes del breakfast.', 
            'category': 2
        },
        { 
            'name': 'La Parrillera', 
            'price': 13.99, 
            'description': 'Deliciosa hamburguesa con carne de res, chorizo parrillero y nuestro chimichurri especial.', 
            'category': 2
        },
        {
            'name': 'La Doble',
            'price': 15.99,
            'description': 'Para los más hambrientos. Doble porción de carne, doble queso y todos los ingredientes.', 
            'category': 2
        }
        ]
        for dish in dishes:
            Dish.objects.create(
                name=dish['name'],
                price=dish['price'],
                description=dish['description'],
                category=categories.get(id=dish['category'])
            )
        self.stdout.write(self.style.SUCCESS(
            f'{len(dishes)} Dishes created successfully'))