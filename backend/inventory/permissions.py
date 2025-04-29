# backend/inventory/permissions.py
from rest_framework import permissions
from users.models import CustomUser # Impor model user kustom

class IsAdminUser(permissions.BasePermission):
    """Hanya mengizinkan akses untuk user dengan role ADMIN atau superuser."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (request.user.role == CustomUser.Role.ADMIN or request.user.is_superuser))

class IsAtasanOperator(permissions.BasePermission):
    """Hanya mengizinkan akses untuk Atasan Operator atau Admin."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (request.user.role == CustomUser.Role.ATASAN_OPERATOR or request.user.is_admin)) # Admin bisa melakukan segalanya

class IsOperatorOrReadOnly(permissions.BasePermission):
    """Mengizinkan read-only untuk semua, tapi write hanya untuk Operator atau Admin."""
    def has_permission(self, request, view):
        # Izinkan GET, HEAD, OPTIONS requests (read) untuk semua user terautentikasi
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        # Izinkan write methods (POST, PUT, PATCH, DELETE) hanya untuk Operator atau Admin
        return bool(request.user and request.user.is_authenticated and (request.user.role == CustomUser.Role.OPERATOR or request.user.is_admin))

class IsOperator(permissions.BasePermission):
    """Hanya mengizinkan akses untuk Operator atau Admin."""
    def has_permission(self, request, view):
         return bool(request.user and request.user.is_authenticated and (request.user.role == CustomUser.Role.OPERATOR or request.user.is_admin))

class IsAtasanPeminta(permissions.BasePermission):
    """Hanya mengizinkan akses untuk Atasan Peminta atau Admin."""
    def has_permission(self, request, view):
         return bool(request.user and request.user.is_authenticated and (request.user.role == CustomUser.Role.ATASAN_PEMINTA or request.user.is_admin))

class IsPeminta(permissions.BasePermission):
    """Hanya mengizinkan akses untuk Peminta atau Admin."""
    def has_permission(self, request, view):
         return bool(request.user and request.user.is_authenticated and (request.user.role == CustomUser.Role.PEMINTA or request.user.is_admin))

class CanApproveRequestSpv1(permissions.BasePermission):
    """Hanya Atasan Peminta yang relevan atau Admin yang bisa approve/reject tahap 1."""
    def has_object_permission(self, request, view, obj):
        # Asumsi obj adalah instance Request
        # Admin bisa melakukan apa saja
        if request.user.is_admin:
            return True
        # Hanya Atasan Peminta yang bisa bertindak
        if request.user.role != CustomUser.Role.ATASAN_PEMINTA:
            return False
        # Idealnya, cek apakah atasan ini memang atasan dari si peminta (jika ada relasi atasan-bawahan di model User)
        # Untuk sekarang, kita asumsikan Atasan Peminta bisa melihat semua request yang butuh approval-nya
        # Atau cek berdasarkan departemen? Misalnya, Atasan Peminta hanya bisa approve request dari departemennya.
        # return request.user.department_code == obj.requester.department_code
        return True # Sementara kita izinkan semua Atasan Peminta

class CanApproveRequestSpv2(permissions.BasePermission):
    """Hanya Atasan Operator atau Admin yang bisa approve/reject tahap 2."""
    def has_object_permission(self, request, view, obj):
        # Asumsi obj adalah instance Request
        if request.user.is_admin:
            return True
        return request.user.role == CustomUser.Role.ATASAN_OPERATOR

class CanProcessRequestOperator(permissions.BasePermission):
     """Hanya Operator atau Admin yang bisa process/reject tahap operator."""
     def has_object_permission(self, request, view, obj):
        if request.user.is_admin:
            return True
        return request.user.role == CustomUser.Role.OPERATOR

class IsOwnerOfRequest(permissions.BasePermission):
    """Hanya Peminta yang membuat request yang bisa melihat detail/mengubah draft/menerima."""
    def has_object_permission(self, request, view, obj):
        # Asumsi obj adalah instance Request
        if request.user.is_admin: # Admin bisa lihat semua
             return True
        return obj.requester == request.user

# Tambahkan permission lain sesuai kebutuhan alur (misal: IsOwnerOrAdminOrApprover)