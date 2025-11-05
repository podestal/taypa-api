from django.contrib import admin
from . import models

admin.site.register(models.Category)
admin.site.register(models.Dish)
admin.site.register(models.Customer)
admin.site.register(models.Address)
admin.site.register(models.Order)
admin.site.register(models.OrderItem)
admin.site.register(models.Account)
admin.site.register(models.Transaction)