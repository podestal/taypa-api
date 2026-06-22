from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction as db_transaction
from django.db.models import Sum
from django.utils import timezone

from . import models


def apply_quantity_change(product, movement_type, quantity):
    product = models.Product.objects.get(pk=product.pk)
    quantity = Decimal(quantity)
    if movement_type == 'IN':
        product.quantity += quantity
    elif movement_type == 'OUT':
        product.quantity -= quantity
    product.save(update_fields=['quantity', 'updated_at'])


def create_inventory_movement(
    *,
    product,
    movement_type,
    quantity,
    source,
    movement_date=None,
    notes='',
    purchase=None,
    created_by=None,
):
    movement_date = movement_date or timezone.localdate()
    with db_transaction.atomic():
        apply_quantity_change(product, movement_type, quantity)
        return models.InventoryMovement.objects.create(
            product=product,
            movement_type=movement_type,
            quantity=quantity,
            source=source,
            movement_date=movement_date,
            notes=notes,
            purchase=purchase,
            created_by=created_by,
        )


def delete_inventory_movement(movement):
    with db_transaction.atomic():
        opposite = 'OUT' if movement.movement_type == 'IN' else 'IN'
        apply_quantity_change(movement.product, opposite, movement.quantity)
        movement.delete()


def sync_purchase_movement(purchase, created_by):
    movement_date = purchase.transaction.transaction_date
    notes = purchase.notes or f'Purchase: {purchase.product.name}'

    if hasattr(purchase, 'inventory_movement'):
        movement = purchase.inventory_movement
        apply_quantity_change(movement.product, 'OUT', movement.quantity)
        movement.product = purchase.product
        movement.quantity = purchase.quantity_bought
        movement.movement_date = movement_date
        movement.notes = notes
        movement.save()
        apply_quantity_change(purchase.product, 'IN', purchase.quantity_bought)
        return movement

    return create_inventory_movement(
        product=purchase.product,
        movement_type='IN',
        quantity=purchase.quantity_bought,
        source='PURCHASE',
        movement_date=movement_date,
        notes=notes,
        purchase=purchase,
        created_by=created_by,
    )


def _balance_from_movements(movements):
    balance = Decimal('0')
    for movement in movements:
        if movement.movement_type == 'IN':
            balance += movement.quantity
        else:
            balance -= movement.quantity
    return balance


def get_inventory_report(start_date, end_date, product_id=None):
    products = models.Product.objects.all().order_by('name')
    if product_id:
        products = products.filter(pk=product_id)

    report = []
    for product in products:
        movements = models.InventoryMovement.objects.filter(
            product=product,
            movement_date__lte=end_date,
        )
        prior_movements = movements.filter(movement_date__lt=start_date)
        current_balance = _balance_from_movements(prior_movements)

        day = start_date
        while day <= end_date:
            day_movements = movements.filter(movement_date=day)
            day_in = day_movements.filter(movement_type='IN').aggregate(
                total=Sum('quantity'),
            )['total'] or Decimal('0')
            day_out = day_movements.filter(movement_type='OUT').aggregate(
                total=Sum('quantity'),
            )['total'] or Decimal('0')
            closing_balance = current_balance + day_in - day_out
            report.append({
                'date': day,
                'product_id': product.id,
                'product_name': product.name,
                'opening_balance': current_balance,
                'in': day_in,
                'out': day_out,
                'closing_balance': closing_balance,
            })
            current_balance = closing_balance
            day += timedelta(days=1)

    return report


def get_balance_as_of(product, as_of_date):
    movements = models.InventoryMovement.objects.filter(
        product=product,
        movement_date__lte=as_of_date,
    )
    return _balance_from_movements(movements)
