from rest_framework.routers import DefaultRouter
from .views import DocumentViewSet

router = DefaultRouter()
router.register(r'documents', DocumentViewSet)

urlpatterns = router.urls