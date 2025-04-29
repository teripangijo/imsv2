# backend/config/urls.py
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    # Hubungkan URL dari app users dan inventory ke /api/
    path('api/', include('users.urls')),
    path('api/', include('inventory.urls')),
    # Mungkin perlu URL lain untuk frontend jika menggunakan pendekatan terintegrasi
]