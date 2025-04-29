# backend/users/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'users', views.UserViewSet, basename='user') # Hanya untuk admin lihat list user

urlpatterns = [
    path('', include(router.urls)),
    # --- PERBARUI BARIS INI ---
    path('auth/login/', views.LoginView.as_view(), name='auth-login'), # Arahkan ke LoginView
    # --- AKHIR PERBARUAN ---
    path('auth/logout/', views.LogoutView.as_view(), name='auth-logout'),
    path('users/me/', views.CurrentUserView.as_view(), name='user-me'),
    path('users/change-password/', views.ChangePasswordView.as_view(), name='change-password'),
    path('users/force-change-password/', views.ForceChangePasswordView.as_view(), name='force-change-password'),
]