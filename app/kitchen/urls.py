from django.urls import path
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register('toppings', views.ToppingViewSet, basename='kitchen-topping')
router.register('categories', views.CategoryViewSet, basename='kitchen-category')
router.register('dishes', views.DishViewSet, basename='kitchen-dish')
router.register('dish-ingredients', views.DishIngredientViewSet, basename='kitchen-dish-ingredient')
router.register('sales', views.SaleViewSet, basename='kitchen-sale')
router.register('products', views.ProductViewSet, basename='kitchen-product')
router.register('accounts', views.AccountViewSet, basename='kitchen-account')
router.register('transactions', views.TransactionViewSet, basename='kitchen-transaction')
router.register('purchases', views.PurchaseViewSet, basename='kitchen-purchase')
router.register('inventory-movements', views.InventoryMovementViewSet, basename='kitchen-inventory-movement')

urlpatterns = [
    path('inventory/report/', views.InventoryReportView.as_view(), name='kitchen-inventory-report'),
    path('inventory/current/', views.InventoryCurrentView.as_view(), name='kitchen-inventory-current'),
    *router.urls,
]
