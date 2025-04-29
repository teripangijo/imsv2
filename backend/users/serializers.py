# backend/users/serializers.py
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core import exceptions as django_exceptions
from django.utils.translation import gettext_lazy as _

CustomUser = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    """Serializer dasar untuk menampilkan data user."""
    full_name = serializers.SerializerMethodField()
    role_display = serializers.CharField(source='get_role_display', read_only=True) # Tampilkan nama peran

    class Meta:
        model = CustomUser
        # Pilih field yang ingin ditampilkan/diedit via API
        fields = (
            'id', 'email', 'first_name', 'last_name', 'full_name',
            'role', 'role_display', # Kirim kode peran & nama tampilannya
            'department_code', 'password_reset_required',
            'is_active', # Mungkin berguna untuk admin
            # 'date_joined', 'last_login' # Opsional
        )
        # Field yang hanya bisa dibaca (tidak bisa diubah lewat serializer ini)
        read_only_fields = ('email', 'role_display', 'password_reset_required')
        # Admin mungkin bisa mengubah role atau is_active di view/serializer terpisah

    def get_full_name(self, obj):
        return obj.get_full_name()

class BasicUserSerializer(serializers.ModelSerializer):
     """Serializer minimal untuk info user di relasi."""
     class Meta:
        model = CustomUser
        fields = ('id', 'email', 'first_name', 'last_name', 'department_code')

class ChangePasswordSerializer(serializers.Serializer):
    """Serializer untuk mengubah password user yang sedang login."""
    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True)
    new_password_confirm = serializers.CharField(required=True, write_only=True)

    def validate_new_password(self, value):# Gunakan validator bawaan Django
        try:
            validate_password(value, self.context['request'].user)
        except django_exceptions.ValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return value

    def validate(self, data):
        if data['new_password'] != data['new_password_confirm']:
            raise serializers.ValidationError({"new_password_confirm": _("Password baru tidak cocok.")})
        return data

class ForceChangePasswordSerializer(serializers.Serializer):
    """Serializer untuk penggantian password pertama kali."""
    new_password = serializers.CharField(required=True, write_only=True)
    new_password_confirm = serializers.CharField(required=True, write_only=True)

    def validate_new_password(self, value):# Gunakan validator bawaan Django
        try:
            # Kita tidak punya old_password di sini, user diambil dari context
            validate_password(value, self.context['request'].user)
        except django_exceptions.ValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return value

    def validate(self, data):
        if data['new_password'] != data['new_password_confirm']:
            raise serializers.ValidationError({"new_password_confirm": _("Password baru tidak cocok.")})
        return data