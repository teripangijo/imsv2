# backend/users/models.py
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _

# --- CUSTOM USER MANAGER ---
class CustomUserManager(BaseUserManager):
    """
    Custom user model manager where email is the unique identifiers
    for authentication instead of usernames.
    """
    def create_user(self, email, password, **extra_fields):
        """
        Create and save a User with the given email and password.
        """
        print(f"--- Manager: create_user() called for: {email} ---") # DEBUG 5
        if not email: raise ValueError(_('The Email must be set'))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        try:
            print(f"--- Manager: Attempting user.save() for: {email} ---") # DEBUG 6
            user.save(using=self._db)
            print(f"--- Manager: user.save() successful for: {email} ---") # DEBUG 7
        except Exception as e:
            print(f"--- Manager: EXCEPTION during user.save(): {type(e).__name__}: {e} ---") # DEBUG 8
            import traceback
            traceback.print_exc() # Cetak traceback lengkap ke konsol runserver
            raise e # Lempar lagi errornya
        return user

    def create_superuser(self, email, password, **extra_fields):
        """
        Create and save a SuperUser with the given email and password.
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        # Set default role for superuser
        extra_fields.setdefault('role', CustomUser.Role.ADMIN)
        extra_fields.setdefault('password_reset_required', False) # Superuser tidak perlu ganti password awal

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))

        # 'createsuperuser' command akan meminta first_name, last_name
        # berdasarkan REQUIRED_FIELDS jika tidak ada di extra_fields
        return self.create_user(email, password, **extra_fields)

# --- CUSTOM USER MODEL ---
class CustomUser(AbstractUser):
    class Role(models.TextChoices):
        PEMINTA = 'PEMINTA', _('Peminta Barang')
        ATASAN_PEMINTA = 'ATASAN_PEMINTA', _('Atasan Peminta Barang')
        OPERATOR = 'OPERATOR', _('Operator Persediaan')
        ATASAN_OPERATOR = 'ATASAN_OPERATOR', _('Atasan Operator Persediaan')
        ADMIN = 'ADMIN', _('Administrator')

    # Hapus username, gunakan email
    username = None
    email = models.EmailField(_('email address'), unique=True)

    # Field kustom
    role = models.CharField(
        _('Role'),
        max_length=20,
        choices=Role.choices,
        default=Role.PEMINTA # Default role saat user dibuat (kecuali superuser)
    )
    department_code = models.CharField(
        _('kode bagian/bidang'),
        max_length=10,
        blank=True,
        null=True,
        help_text="Contoh: WBC.051"
    )
    password_reset_required = models.BooleanField(_('wajib ganti password'), default=True)

    # Konfigurasi User Model
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name'] # Diminta saat createsuperuser

    # Gunakan manager kustom
    objects = CustomUserManager()

    def __str__(self):
        full_name = super().get_full_name()
        return full_name or self.email

    # Properties untuk cek role
    @property
    def is_peminta(self):
        return self.role == self.Role.PEMINTA

    @property
    def is_atasan_peminta(self):
        return self.role == self.Role.ATASAN_PEMINTA

    @property
    def is_operator(self):
        return self.role == self.Role.OPERATOR

    @property
    def is_atasan_operator(self):
        return self.role == self.Role.ATASAN_OPERATOR

    @property
    def is_admin(self):
        # Superuser juga dianggap admin dalam konteks aplikasi ini
        return self.role == self.Role.ADMIN or self.is_superuser