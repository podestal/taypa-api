from django.urls import path
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
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
