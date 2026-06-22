from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register('products', views.ProductViewSet, basename='kitchen-product')
router.register('accounts', views.AccountViewSet, basename='kitchen-account')
router.register('transactions', views.TransactionViewSet, basename='kitchen-transaction')
router.register('purchases', views.PurchaseViewSet, basename='kitchen-purchase')

urlpatterns = router.urls
