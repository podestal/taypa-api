from django.db import migrations, models


def normalize_product_types(apps, schema_editor):
    Product = apps.get_model('kitchen', 'Product')
    Product.objects.filter(product_type='INGREDIENT').update(product_type='I')
    Product.objects.filter(product_type__in=('OTHER', 'PACKAGING')).update(product_type='O')


class Migration(migrations.Migration):

    dependencies = [
        ('kitchen', '0006_product_type_other_no_inventory'),
    ]

    operations = [
        migrations.RunPython(normalize_product_types, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='product',
            name='product_type',
            field=models.CharField(
                choices=[('I', 'Ingredient'), ('O', 'Other')],
                default='I',
                max_length=10,
            ),
        ),
    ]
