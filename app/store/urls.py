from rest_framework_nested import routers
from . import views

router = routers.DefaultRouter()
router.register('categories', views.CategoryViewSet)
router.register('dishes', views.DishViewSet)
router.register('orders', views.OrderViewSet)
router.register('order-items', views.OrderItemViewSet)
router.register('customers', views.CustomerViewSet)
router.register('addresses', views.AddressViewSet)
router.register('accounts', views.AccountViewSet)
router.register('transactions', views.TransactionViewSet)

urlpatterns = router.urls
