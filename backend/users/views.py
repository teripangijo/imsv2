# backend/users/views.py
from django.contrib.auth import get_user_model
from rest_framework import generics, viewsets, status, permissions
from rest_framework.permissions import IsAuthenticated, AllowAny # AllowAny untuk login/register
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken # View login bawaan

from .serializers import UserSerializer, ChangePasswordSerializer, ForceChangePasswordSerializer
# Impor permission kustom jika diperlukan di sini, tapi lebih banyak di inventory
from inventory.permissions import IsAdminUser

CustomUser = get_user_model()

class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoint untuk melihat daftar user (hanya Admin)."""
    queryset = CustomUser.objects.all().order_by('email')
    serializer_class = UserSerializer
    permission_classes = [IsAdminUser] # Hanya admin yang bisa lihat daftar user

class CurrentUserView(generics.RetrieveAPIView):
    """API endpoint untuk mendapatkan detail user yang sedang login."""
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated] # Cukup login

    def get_object(self):
        return self.request.user

class CustomObtainAuthToken(ObtainAuthToken):
    """View login, mengembalikan token dan info user dasar."""
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data,
                                           context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        token, created = Token.objects.get_or_create(user=user)
        # Sertakan juga data user dasar dalam response
        user_data = UserSerializer(user, context={'request': request}).data
        return Response({
            'token': token.key,
            'user': user_data
        })

class LogoutView(APIView):
    """API endpoint untuk logout (menghapus token)."""
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        try:
            # Hapus token user yang sedang login
            request.user.auth_token.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except (AttributeError, Token.DoesNotExist):
            return Response({"error": "Token tidak ditemukan atau user tidak memiliki token."},
                            status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(generics.UpdateAPIView):
    """API endpoint untuk mengubah password (butuh password lama)."""
    serializer_class = ChangePasswordSerializer
    model = CustomUser
    permission_classes = [IsAuthenticated]

    def get_object(self, queryset=None):
        return self.request.user

    def update(self, request, *args, **kwargs):
        self.object = self.get_object()
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            # Cek password lama
            if not self.object.check_password(serializer.data.get("old_password")):
                return Response({"old_password": ["Password lama salah."]}, status=status.HTTP_400_BAD_REQUEST)
            # Set password baru
            self.object.set_password(serializer.data.get("new_password"))
            # Set flag password_reset_required jadi False jika ini penggantian password
            self.object.password_reset_required = False
            self.object.save()
            return Response({"message": "Password berhasil diubah."}, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ForceChangePasswordView(generics.UpdateAPIView):
    """API endpoint untuk wajib ganti password pertama kali."""
    serializer_class = ForceChangePasswordSerializer
    model = CustomUser
    permission_classes = [IsAuthenticated] # Harus login dulu

    def get_object(self, queryset=None):
        # Hanya berlaku jika flag password_reset_required=True
        user = self.request.user
        if not user.password_reset_required:
             # Jika tidak wajib ganti, endpoint ini tidak berlaku
             # Bisa raise exception atau return response error
             from django.http import Http404
             raise Http404("Penggantian password tidak diwajibkan untuk user ini.")
        return user

    def update(self, request, *args, **kwargs):
        self.object = self.get_object()
        serializer = self.get_serializer(data=request.data, context={'request': request}) # Pass context

        if serializer.is_valid():
            # Set password baru
            self.object.set_password(serializer.validated_data.get("new_password"))
            # Set flag jadi False setelah berhasil ganti
            self.object.password_reset_required = False
            self.object.save()
            return Response({"message": "Password awal berhasil diatur."}, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)