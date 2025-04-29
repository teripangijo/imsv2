# backend/inventory/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'product-categories', views.ProductCategoryViewSet)
router.register(r'product-variants', views.ProductVariantViewSet)
router.register(r'stock-levels', views.StockViewSet)
router.register(r'inventory-items', views.InventoryItemViewSet)
router.register(r'requests', views.RequestViewSet)
router.register(r'spmbs', views.SPMBViewSet)
router.register(r'request-logs', views.RequestLogViewSet)
router.register(r'transactions', views.TransactionViewSet)
router.register(r'stock-opname-sessions', views.StockOpnameSessionViewSet)
router.register(r'stock-opname-items', views.StockOpnameItemViewSet)

urlpatterns = [
    path('', include(router.urls)),
     # Tambahkan URL untuk view dashboard jika perlu endpoint terpisah
     # path('dashboard-data/', views.DashboardDataView.as_view(), name='dashboard-data'),
]