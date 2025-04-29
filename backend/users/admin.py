# backend/users/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser

class CustomUserAdmin(UserAdmin):
    model = CustomUser
    # Tampilkan field tambahan di admin list dan form
    list_display = ('email', 'first_name', 'last_name', 'role', 'department_code', 'is_staff', 'password_reset_required')
    list_filter = ('role', 'is_staff', 'is_active', 'groups', 'password_reset_required')
    search_fields = ('email', 'first_name', 'last_name', 'department_code')
    ordering = ('email',)
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
        ('Custom Fields', {'fields': ('role', 'department_code', 'password_reset_required')}), # Field kustom
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Custom Fields', {'fields': ('first_name', 'last_name', 'role', 'department_code', 'password_reset_required')}),
    )

admin.site.register(CustomUser, CustomUserAdmin)