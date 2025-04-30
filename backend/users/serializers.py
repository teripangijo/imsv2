# backend/users/serializers.py
from rest_framework import serializers
from django.contrib.auth import get_user_model, authenticate
from django.contrib.auth.password_validation import validate_password
from django.core import exceptions as django_exceptions
from django.utils.translation import gettext_lazy as _

CustomUser = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    """Serializer dasar untuk menampilkan data user."""
    full_name = serializers.SerializerMethodField()
    role_display = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model = CustomUser
        # Pilih field yang ingin ditampilkan/diedit via API
        fields = (
            'id', 'email', 'first_name', 'last_name', 'full_name',
            'role', 'role_display', 
            'department_code', 'password_reset_required',
            'is_active', #
            # 'date_joined', 'last_login' # Opsional
        )
        # Field yang hanya bisa dibaca (tidak bisa diubah lewat serializer ini)
        read_only_fields = ('email', 'role_display', 'password_reset_required')

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

    def validate_new_password(self, value):
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

    def validate_new_password(self, value):
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
    
class CustomAuthTokenSerializer(serializers.Serializer):
    """Serializer untuk login menggunakan email dan password."""
    email = serializers.EmailField(label=_("Email"), write_only=True)
    password = serializers.CharField(
        label=_("Password"),
        style={'input_type': 'password'}, # Agar bisa dikenali sebagai password field
        trim_whitespace=False,
        write_only=True # Hanya untuk input, tidak ditampilkan di output
    )

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')

        if email and password:
            # yang mendukung login via email (defaultnya sudah jika USERNAME_FIELD='email')
            user = authenticate(request=self.context.get('request'),
                                email=email, password=password) # Gunakan email

            # Jika authenticate gagal (kredensial salah), user akan None
            if not user:
                # Cek juga apakah user tidak aktif
                UserModel = get_user_model()
                try:
                     user_obj = UserModel.objects.get(email=email)
                     if not user_obj.is_active:
                          msg = _('Akun pengguna tidak aktif.')
                          raise serializers.ValidationError(msg, code='authorization')
                except UserModel.DoesNotExist:
                     pass

                msg = _('Tidak dapat login dengan kredensial yang diberikan.')
                raise serializers.ValidationError(msg, code='authorization')
        else:
            msg = _('Harus menyertakan "email" dan "password".')
            raise serializers.ValidationError(msg, code='authorization')

        # Jika berhasil, attach user ke data tervalidasi untuk digunakan view
        attrs['user'] = user
        return attrs