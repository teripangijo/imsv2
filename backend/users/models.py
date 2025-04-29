from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _

class CustomUser(AbstractUser):
    class Role(models.TextChoices):
        PEMINTA = 'PEMINTA', _('Peminta')
        ATASAN_PEMINTA = 'ATASAN_PEMINTA', _('Atasan Peminta')
        OPERATOR = 'OPERATOR', _('Operator')
        ATASAN_OPERATOR = 'ATASAN_OPERATOR', _('Atasan Operator')
        ADMIN = 'ADMIN', _('Admin')

    # Field username bawaan tidak digunakan, gunakan email sebagai username
    username = None
    email = models.EmailField(_('email address'), unique=True)

    role = models.EmailField(_('Role'), choices=Role.choices, default=Role.PEMINTA, max_length=20)
    departement_code = models.CharField(_('kode bagian/bidang'), max_length=10, blank=True, null=True)
    password_reset_required = models.BooleanField(_('wajib ganti password'), default=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    def __str__(self):
        return self.get_full_name() or self.email
    
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
        return self.role == self.Role.ADMIN or self.is_superuser