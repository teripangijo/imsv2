# backend/users/admin.py
from django.contrib import admin
from django.contrib.auth import get_user_model
from django import forms
from django.utils.translation import gettext_lazy as _

CustomUser = get_user_model()

# --- Form Kustom (disederhanakan, bisa pakai ModelForm biasa) ---

class CustomUserAdminForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, required=False, help_text=_("Kosongkan jika tidak ingin mengubah password saat edit. Wajib diisi saat menambah user baru."))
    password2 = forms.CharField(label=_("Password confirmation"), widget=forms.PasswordInput, required=False, help_text=_("Masukkan password yang sama untuk verifikasi (hanya saat menambah user baru atau mengubah password)."))

    class Meta:
        model = CustomUser
        fields = ('email', 'first_name', 'last_name', 'role', 'department_code',
                  'password_reset_required', 'is_active', 'is_staff', 'is_superuser',
                  'groups', 'user_permissions')

    # Validasi password confirmation
    def clean_password2(self):
        password = self.cleaned_data.get("password")
        password2 = self.cleaned_data.get("password2")
        # Jika password diisi (menambah user baru atau mengubah password),
        # maka password2 wajib diisi dan harus cocok
        if password and not password2:
             raise forms.ValidationError(_("Anda harus mengkonfirmasi password."), code='password_confirmation_required')
        if password and password2 and password != password2:
            raise forms.ValidationError(
                _("The two password fields didn't match."),
                code='password_mismatch',
            )
        return password2

    def clean(self):
         cleaned_data = super().clean()
         password = cleaned_data.get("password")
         # Jika ini form update (instance sudah ada) DAN field password kosong
         if self.instance and self.instance.pk and not password:
             # Hapus password dari cleaned_data agar tidak di-save
             cleaned_data.pop('password', None)
             cleaned_data.pop('password2', None) # Hapus juga password2
         elif not (self.instance and self.instance.pk) and not password:
             # Jika ini form add DAN password kosong
              raise forms.ValidationError(_("Password wajib diisi untuk user baru."), code='password_required')

         return cleaned_data


# --- Admin Kustom (Mewarisi ModelAdmin) ---
class CustomUserAdmin(admin.ModelAdmin):

    form = CustomUserAdminForm
    add_form = CustomUserAdminForm

    # Tampilan list
    list_display = ('email', 'first_name', 'last_name', 'role', 'department_code', 'is_staff', 'is_active', 'password_reset_required')
    list_filter = ('role', 'is_staff', 'is_active', 'password_reset_required')
    search_fields = ('email', 'first_name', 'last_name', 'department_code')
    ordering = ('email',)

    fieldsets = (
        (None, {'fields': ('email', 'password', 'password2')}), # Password & konfirmasi tampil di add/change
        (_('Personal info'), {'fields': ('first_name', 'last_name')}),
        (_('Custom Fields'), {'fields': ('role', 'department_code', 'password_reset_required')}),
        (_('Permissions'), {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),

    )
    # add_fieldsets tidak diperlukan jika pakai fieldsets biasa atau form saja

    # --- PENTING: Override save_model untuk Hashing Password ---
    def save_model(self, request, obj, form, change):
        """
        Override save_model untuk menangani hashing password.
        'obj' adalah instance CustomUser (bisa baru atau lama).
        'form' adalah CustomUserAdminForm yang sudah valid.
        'change' boolean (True jika edit, False jika add).
        """
        # Ambil password dari cleaned_data form JIKA ADA
        # Form clean() kita sudah menghapus 'password' jika tidak diisi saat update
        password = form.cleaned_data.get('password')

        if password:
            # Jika password diisi (user baru atau ganti password)
            obj.set_password(password) # Hash password menggunakan set_password()
            print(f"--- Admin save_model: Password set for {obj.email} ---")
        elif not change:
             # Jika ini user baru tapi password tidak ada di cleaned_data (seharusnya tidak terjadi karena validasi form clean())
             print(f"--- Admin save_model: ERROR - Password missing for new user {obj.email} ---")
             raise ValueError("Password tidak boleh kosong untuk user baru.")

        # Simpan objek user ke database
        print(f"--- Admin save_model: Saving object for {obj.email} ---")
        super().save_model(request, obj, form, change) # Panggil save_model asli dari ModelAdmin
        print(f"--- Admin save_model: Object saved for {obj.email} ---")


# Daftarkan model dan admin kustom
admin.site.register(CustomUser, CustomUserAdmin)