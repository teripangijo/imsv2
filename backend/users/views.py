# backend/users/views.py
from django.contrib.auth import get_user_model
from django.http import Http404 # Import Http404 untuk ForceChangePasswordView

from rest_framework import generics, viewsets, status, permissions
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import generics, viewsets, status, permissions, serializers
from rest_framework.response import Response
from rest_framework.views import APIView # Pastikan APIView diimpor
from rest_framework.authtoken.models import Token

from .serializers import (
    UserSerializer,
    ChangePasswordSerializer,
    ForceChangePasswordSerializer,
    CustomAuthTokenSerializer
)
from inventory.permissions import IsAdminUser

CustomUser = get_user_model()

class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint untuk melihat daftar user.
    Hanya Admin yang bisa mengakses ini.
    """
    queryset = CustomUser.objects.all().order_by('email')
    serializer_class = UserSerializer
    permission_classes = [IsAdminUser] # Hanya admin yang bisa lihat daftar user

class CurrentUserView(generics.RetrieveAPIView):
    """
    API endpoint untuk mendapatkan detail user yang sedang login.
    """
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated] # Cukup user sudah login

    def check_permissions(self, request):
        """Override untuk inspeksi request.user sebelum permission check standar."""
        print(f"\n--- CurrentUserView: check_permissions called ---")
        # Cek apakah request.user ada dan siapa dia
        user_repr = getattr(request, 'user', 'Not Set')
        print(f"--- request.user: {user_repr} (Type: {type(user_repr).__name__}) ---")

        # Cek status is_authenticated
        is_auth_attr = getattr(request.user, 'is_authenticated', 'N/A (user not set or no attribute)')
        is_auth_val = 'N/A'
        if callable(is_auth_attr): # is_authenticated biasanya property, tapi cek jika callable
             try: is_auth_val = is_auth_attr()
             except Exception as e: is_auth_val = f'Error calling: {e}'
        else:
            is_auth_val = is_auth_attr
        print(f"--- request.user.is_authenticated: {is_auth_val} ---")

        # Cek hasil autentikasi (token apa yg ditemukan)
        auth_token = getattr(request, 'auth', 'Not Set')
        print(f"--- request.auth (Token found by Auth class): {auth_token} ---")
        print(f"--- Running standard permission checks defined in permission_classes... ---")

        try:
            super().check_permissions(request)
            print(f"--- CurrentUserView: super().check_permissions() PASSED ---")
        except Exception as e:
             print(f"--- CurrentUserView: super().check_permissions() FAILED with {type(e).__name__} ---")
             raise e

    def get_object(self):
        return self.request.user

# --- View Login Kustom (Menggantikan CustomObtainAuthToken) ---
class LoginView(APIView):
    """
    API View untuk user login menggunakan email dan password.
    Mengembalikan auth token dan data user.
    """
    permission_classes = [AllowAny] # Siapa saja boleh mencoba login
    serializer_class = CustomAuthTokenSerializer

    def post(self, request, *args, **kwargs):
        # Inisialisasi serializer dengan data dari request
        serializer = self.serializer_class(data=request.data,
                                           context={'request': request})
        try:
            # Validasi data input (email, password, dan cek kredensial via authenticate)
            serializer.is_valid(raise_exception=True)
        except serializers.ValidationError as e:
             # Jika validasi gagal, kirim response error
             error_detail = e.detail
             if isinstance(error_detail, list) and len(error_detail) > 0:
                  error_detail = {'detail': error_detail[0]}
             elif isinstance(error_detail, dict):
                  if 'non_field_errors' in error_detail:
                       error_detail = {'detail': error_detail['non_field_errors'][0]}

             return Response({"error": error_detail}, status=status.HTTP_400_BAD_REQUEST)
        
        user = serializer.validated_data['user']
        token, created = Token.objects.get_or_create(user=user)
        user_data = UserSerializer(user, context={'request': request}).data
        return Response({
            'token': token.key,
            'user': user_data
        }, status=status.HTTP_200_OK)

class LogoutView(APIView):
    """
    API endpoint untuk logout (menghapus token autentikasi).
    """
    permission_classes = [IsAuthenticated] # Hanya user yang login bisa logout

    def post(self, request, *args, **kwargs):
        try:
            # Hapus token milik user yang sedang login
            request.user.auth_token.delete()
            # Kirim response sukses tanpa konten
            return Response(status=status.HTTP_204_NO_CONTENT)
        except (AttributeError, Token.DoesNotExist):
            return Response({"error": "Token tidak ditemukan atau user tidak memiliki token."},
                            status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(generics.UpdateAPIView):
    """
    API endpoint untuk mengubah password (membutuhkan password lama).
    """
    serializer_class = ChangePasswordSerializer
    model = CustomUser
    permission_classes = [IsAuthenticated] # Hanya user login yang bisa ganti passwordnya

    def get_object(self, queryset=None):
        # Objek yang diupdate adalah user itu sendiri
        return self.request.user

    def update(self, request, *args, **kwargs):
        self.object = self.get_object()
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            # Cek apakah password lama benar
            if not self.object.check_password(serializer.data.get("old_password")):
                return Response({"old_password": ["Password lama salah."]}, status=status.HTTP_400_BAD_REQUEST)

            # Set password baru (sudah divalidasi oleh serializer)
            self.object.set_password(serializer.data.get("new_password"))
            # Setelah berhasil ganti password, flag wajib ganti password jadi False
            self.object.password_reset_required = False
            self.object.save()
            return Response({"message": "Password berhasil diubah."}, status=status.HTTP_200_OK)

        # Jika serializer tidak valid
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ForceChangePasswordView(generics.UpdateAPIView):
    """
    API endpoint untuk wajib ganti password saat pertama kali login
    (jika flag password_reset_required = True).
    """
    serializer_class = ForceChangePasswordSerializer
    model = CustomUser
    permission_classes = [IsAuthenticated] # Harus login dulu

    def get_object(self, queryset=None):
        user = self.request.user
        # Hanya user yang WAJIB ganti password yang bisa akses endpoint ini
        if not user.password_reset_required:
             raise Http404("Penggantian password tidak diwajibkan untuk user ini.")
        return user

    def update(self, request, *args, **kwargs):
        self.object = self.get_object()
        serializer = self.get_serializer(data=request.data, context={'request': request})

        if serializer.is_valid():
            self.object.set_password(serializer.validated_data.get("new_password"))
            self.object.password_reset_required = False
            self.object.save()
            return Response({"message": "Password awal berhasil diatur."}, status=status.HTTP_200_OK)

        # Jika serializer tidak valid
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)