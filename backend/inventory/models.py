# backend/inventory/models.py

from django.db import models, transaction, IntegrityError # Pastikan IntegrityError diimpor
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
import uuid
import traceback # Masih berguna jika ada error tak terduga

# --- MODEL BARU UNTUK HIERARKI KODE BARANG ---

class ItemCodeGolongan(models.Model):
    code = models.CharField(_('kode golongan'), max_length=1, unique=True)
    description = models.TextField(_('uraian golongan'), blank=True, null=True)

    class Meta:
        verbose_name = _('Kode Golongan Barang')
        verbose_name_plural = _('Kode Golongan Barang')
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.description or 'Tanpa Uraian'}"

class ItemCodeBidang(models.Model):
    golongan = models.ForeignKey(ItemCodeGolongan, on_delete=models.CASCADE, related_name='bidang_set')
    code = models.CharField(_('kode bidang'), max_length=10) # Sesuaikan max_length jika perlu
    description = models.TextField(_('uraian bidang'), blank=True, null=True)

    class Meta:
        verbose_name = _('Kode Bidang Barang')
        verbose_name_plural = _('Kode Bidang Barang')
        unique_together = ('golongan', 'code')
        ordering = ['golongan__code', 'code']

    def __str__(self):
        gol_code = getattr(self.golongan, 'code', '?')
        return f"{gol_code}.{self.code} - {self.description or 'Tanpa Uraian'}"

class ItemCodeKelompok(models.Model):
    bidang = models.ForeignKey(ItemCodeBidang, on_delete=models.CASCADE, related_name='kelompok_set')
    code = models.CharField(_('kode kelompok'), max_length=10) # Sesuaikan max_length jika perlu
    description = models.TextField(_('uraian kelompok'), blank=True, null=True)

    class Meta:
        verbose_name = _('Kode Kelompok Barang')
        verbose_name_plural = _('Kode Kelompok Barang')
        unique_together = ('bidang', 'code')
        ordering = ['bidang__golongan__code', 'bidang__code', 'code']

    def __str__(self):
        bid_code = getattr(self.bidang, 'code', '?')
        gol_code = getattr(getattr(self.bidang, 'golongan', None), 'code', '?')
        return f"{gol_code}.{bid_code}.{self.code} - {self.description or 'Tanpa Uraian'}"

class ItemCodeSubKelompok(models.Model):
    kelompok = models.ForeignKey(ItemCodeKelompok, on_delete=models.CASCADE, related_name='subkelompok_set')
    code = models.CharField(_('kode sub kelompok'), max_length=15) # Sesuaikan max_length jika perlu
    base_description = models.TextField(_('uraian sub kelompok (dasar)')) # Dari ur_sskel

    class Meta:
        verbose_name = _('Kode Sub Kelompok Barang')
        verbose_name_plural = _('Kode Sub Kelompok Barang')
        unique_together = ('kelompok', 'code')
        ordering = ['kelompok__bidang__golongan__code', 'kelompok__bidang__code', 'kelompok__code', 'code']

    def __str__(self):
        return f"{self.get_base_code_prefix()} - {self.base_description}"

    def get_base_code_prefix(self):
        """Mengembalikan prefix kode hingga level subkelompok (tanpa kd_brg). Misal: 1.01.01.01"""
        try:
            kel = self.kelompok
            bid = kel.bidang
            gol = bid.golongan
            prefix = f"{gol.code}.{bid.code}.{kel.code}.{self.code}"
            return prefix
        except Exception:
             return "?.?.?.?" # Kembalikan placeholder jika gagal

    def get_full_base_code_prefix(self):
        """Mengembalikan prefix kode hingga level subkelompok (tanpa kd_brg). Misal: 1010101"""
        try:
            kel = self.kelompok
            bid = kel.bidang
            gol = bid.golongan

            gol_code_str = str(gol.code)
            bid_code_str = str(bid.code)
            kel_code_str = str(kel.code)
            skel_code_str = str(self.code)

            gol_code = gol_code_str.zfill(1)
            bid_code = bid_code_str.zfill(2)
            kel_code = kel_code_str.zfill(2)
            skel_code = skel_code_str.zfill(2)
            prefix = f"{gol_code}{bid_code}{kel_code}{skel_code}"
            return prefix
        except Exception:
             return None # Kembalikan None jika gagal

class ItemCodeBarang(models.Model):
     """Merepresentasikan entitas barang dasar dari CSV."""
     sub_kelompok = models.ForeignKey(ItemCodeSubKelompok, on_delete=models.CASCADE, related_name='barang_set')
     code = models.CharField(_('kode barang (akhir)'), max_length=3) # kd_brg dari CSV
     base_description = models.TextField(_('uraian barang (dasar)')) # ur_sskel
     account_code = models.CharField(_('kode akun'), max_length=20, blank=True, null=True)
     account_description = models.CharField(_('uraian akun'), max_length=100, blank=True, null=True)
     full_base_code = models.CharField(
         _('kode barang dasar lengkap'),
         max_length=20, # Sesuaikan panjang jika perlu
         unique=True,
         editable=False,
         blank=True, # Harus True agar bisa disimpan dulu sebelum di-generate
         db_index=True
     )

     class Meta:
         verbose_name = _('Kode Barang Dasar')
         verbose_name_plural = _('Kode Barang Dasar')
         unique_together = ('sub_kelompok', 'code')
         ordering = ['full_base_code']

     def __str__(self):
         # Gunakan full_base_code yang tersimpan
         return f"{self.full_base_code or '(Kode Belum Tergenerate)'} - {self.base_description}"

     def _generate_full_base_code(self):
         """Helper internal untuk men-generate kode dasar lengkap."""
         if not self.sub_kelompok_id or not self.code:
             return None
         try:
             # Coba ambil sub_kelompok terkait
             sk = ItemCodeSubKelompok.objects.select_related('kelompok__bidang__golongan').get(pk=self.sub_kelompok_id)
             prefix = sk.get_full_base_code_prefix()
             if prefix is None:
                  return None
             brg_code_str = str(self.code)
             brg_code = brg_code_str.zfill(3)
             result = f"{prefix}{brg_code}"
             return result
         except ItemCodeSubKelompok.DoesNotExist:
              return None
         except Exception: # Tangkap error lain saat generate
              traceback.print_exc() # Cetak error ke log server
              return None

     def save(self, *args, **kwargs):
         generate_code = False
         if not self.pk: generate_code = True
         elif not self.full_base_code: generate_code = True

         if generate_code:
             generated_code = self._generate_full_base_code()
             if generated_code:
                 self.full_base_code = generated_code
             else:
                 # Tetap raise error jika generate gagal agar transaksi rollback
                 raise IntegrityError(f"Tidak dapat men-generate full_base_code yang valid untuk ItemCodeBarang dengan subkel={self.sub_kelompok_id}, code={self.code}. Periksa data hierarki induknya.")
         super().save(*args, **kwargs)

# --- MODEL VARIAN PRODUK SPESIFIK ---
class ProductVariant(models.Model):
    """Merepresentasikan Varian Barang SPESIFIK (e.g., Aspal Pertamina 60/70)"""
    base_item_code = models.ForeignKey(ItemCodeBarang, related_name='variants', on_delete=models.PROTECT, verbose_name=_('kode barang dasar'))
    type_name = models.CharField(_('jenis barang'), max_length=100, db_index=True, help_text="Contoh: Pulpen, Pensil, Sabun Cuci Tangan")
    specific_code = models.CharField(_('kode spesifik'), max_length=3, editable=False, blank=True, help_text="3 digit unik per kode barang dasar, di-generate otomatis.")
    full_code = models.CharField(_('kode barang lengkap'), max_length=20, unique=True, editable=False, blank=True, db_index=True)
    name = models.CharField(_('nama spesifik (merk/tipe)'), max_length=150, help_text="Contoh: Snowman 0.5 Hitam, Faber-Castell 2B, Lifebuoy Mild Care")
    description = models.TextField(_('deskripsi tambahan'), blank=True, null=True)
    unit_of_measure = models.CharField(_('satuan'), max_length=20, default='pcs', help_text="Contoh: pcs, box, rim, unit, kg, liter")

    class Meta:
        verbose_name = _('Varian Produk Spesifik')
        verbose_name_plural = _('Varian Produk Spesifik')
        unique_together = ('base_item_code', 'type_name', 'name')
        ordering = ['base_item_code', 'type_name', 'specific_code']

    def __str__(self):
        return f"{self.full_code or '(Kode?)'} - {self.type_name} - {self.name}"

    def _generate_specific_code(self):
         """Generate 3 digit kode spesifik berikutnya untuk base_item_code ini."""
         if not self.base_item_code_id: return None
         # Cari varian terakhir untuk base_item_code yang sama
         last_variant = ProductVariant.objects.filter(base_item_code=self.base_item_code).exclude(pk=self.pk).order_by('-specific_code').first()
         if last_variant and last_variant.specific_code:
             try: next_num = int(last_variant.specific_code) + 1
             except ValueError:
                 # Fallback jika kode lama tidak valid, hitung jumlah yg ada
                 next_num = ProductVariant.objects.filter(base_item_code=self.base_item_code).count() + (0 if self.pk else 1)
         else:
             next_num = 1 # Kode pertama
         return f"{next_num:03d}" # Format jadi 3 digit

    def save(self, *args, **kwargs):
         # Generate specific_code jika belum ada
         if not self.pk or not self.specific_code:
             self.specific_code = self._generate_specific_code()

         # Generate full_code jika komponennya sudah ada dan full_code belum terisi
         if self.base_item_code_id and self.specific_code and (not self.pk or not self.full_code):
             try:
                 # Ambil base_code dari field yang tersimpan di base_item_code
                 base_code_part = self.base_item_code.full_base_code
                 if not base_code_part: # Jika base_code belum tergenerate
                     # Coba generate ulang base_code
                     base_code_part = self.base_item_code._generate_full_base_code()
                     if not base_code_part:
                          raise IntegrityError(f"Tidak bisa mendapatkan full_base_code dari ItemCodeBarang ID {self.base_item_code_id}")

                 self.full_code = f"{base_code_part}{self.specific_code}"
             except ItemCodeBarang.DoesNotExist:
                 raise IntegrityError(f"ItemCodeBarang dengan ID {self.base_item_code_id} tidak ditemukan saat generate full_code ProductVariant.")
             except Exception as e:
                 # Tangkap error lain saat generate
                 print(f"Error generating full_code for ProductVariant: {e}")
                 traceback.print_exc()
                 raise IntegrityError(f"Gagal men-generate full_code untuk ProductVariant: {e}")

         super().save(*args, **kwargs)

# --- MODEL KUITANSI ---
class Receipt(models.Model):
    receipt_number = models.CharField(_('nomor kuitansi/PO'), max_length=100, unique=True)
    supplier_name = models.CharField(_('nama pemasok'), max_length=255, blank=True, null=True)
    receipt_date = models.DateField(_('tanggal kuitansi/pembelian'))
    uploaded_file = models.FileField(_('file unggahan'), upload_to='receipts/%Y/%m/', blank=True, null=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='uploaded_receipts', on_delete=models.PROTECT, verbose_name=_('diunggah oleh'))
    uploaded_at = models.DateTimeField(_('diunggah tanggal'), auto_now_add=True)

    class Meta:
         verbose_name = _('Kuitansi Pembelian')
         verbose_name_plural = _('Kuitansi Pembelian')
         ordering = ['-receipt_date', '-uploaded_at']

    def __str__(self):
         return f"Kuitansi {self.receipt_number} ({self.receipt_date})"

# --- MODEL ITEM INVENTARIS (BATCH) ---
class InventoryItem(models.Model):
    variant = models.ForeignKey(ProductVariant, related_name='inventory_items', on_delete=models.PROTECT, verbose_name=_('varian produk spesifik'))
    quantity = models.PositiveIntegerField(_('jumlah'))
    purchase_price = models.DecimalField(_('harga beli'), max_digits=15, decimal_places=2, blank=True, null=True, help_text="Harga per satuan")
    entry_date = models.DateTimeField(_('tanggal masuk'), default=timezone.now)
    expiry_date = models.DateField(_('tanggal kadaluarsa'), blank=True, null=True)
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='added_inventory_items', null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_('ditambahkan oleh'))
    receipt = models.ForeignKey(Receipt, related_name='inventory_items', null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_('kuitansi terkait'))

    class Meta:
        verbose_name = _('Item Inventaris (Batch)')
        verbose_name_plural = _('Item Inventaris (Batch)')
        ordering = ['entry_date', 'id']

    def __str__(self):
        variant_str = str(self.variant) if self.variant else 'N/A'
        unit = getattr(getattr(self, 'variant', None), 'unit_of_measure', 'unit')
        return f"{variant_str} ({self.quantity} {unit}) - Masuk: {self.entry_date.strftime('%Y-%m-%d')}"

# --- MODEL STOK TOTAL ---
class Stock(models.Model):
    variant = models.OneToOneField(ProductVariant, related_name='stock_level', on_delete=models.CASCADE, primary_key=True, verbose_name=_('varian produk spesifik'))
    total_quantity = models.PositiveIntegerField(_('total kuantitas'), default=0)
    low_stock_threshold = models.PositiveIntegerField(_('ambang batas stok rendah'), default=10, blank=True, null=True)
    last_updated = models.DateTimeField(_('terakhir diperbarui'), auto_now=True)

    class Meta:
        verbose_name = _('Level Stok')
        verbose_name_plural = _('Level Stok')
        ordering = ['variant__full_code']

    def __str__(self):
        variant_name = getattr(getattr(self, 'variant', None), 'name', 'N/A')
        variant_code = getattr(getattr(self, 'variant', None), 'full_code', 'N/A')
        return f"Stok {variant_name} ({variant_code}): {self.total_quantity}"

    @property
    def is_low_stock(self):
        if self.low_stock_threshold is None: return False
        return self.total_quantity <= self.low_stock_threshold

    @property
    def is_out_of_stock(self):
        return self.total_quantity <= 0

# --- MODEL REQUEST ---
class Request(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', _('Draft')
        SUBMITTED = 'SUBMITTED', _('Diajukan (Menunggu Atasan Peminta)')
        REJECTED_SPV1 = 'REJECTED_SPV1', _('Ditolak Atasan Peminta')
        APPROVED_SPV1 = 'APPROVED_SPV1', _('Disetujui Atasan Peminta (Menunggu Atasan Operator)')
        REJECTED_SPV2 = 'REJECTED_SPV2', _('Ditolak Atasan Operator')
        APPROVED_SPV2 = 'APPROVED_SPV2', _('Disetujui Atasan Operator (Menunggu Operator)')
        PROCESSING = 'PROCESSING', _('Diproses Operator')
        REJECTED_OPR = 'REJECTED_OPR', _('Ditolak Operator')
        COMPLETED = 'COMPLETED', _('Selesai (Menunggu Konfirmasi Terima)')
        RECEIVED = 'RECEIVED', _('Barang Diterima Peminta')
        CANCELLED = 'CANCELLED', _('Dibatalkan')

    requester = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='requests_made', on_delete=models.PROTECT, verbose_name=_('peminta'))
    request_number = models.CharField(_('nomor permintaan'), max_length=50, unique=True, blank=True, null=True, editable=False)
    status = models.CharField(_('status'), max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(_('dibuat tanggal'), auto_now_add=True)
    submitted_at = models.DateTimeField(_('diajukan tanggal'), null=True, blank=True)
    supervisor1_approver = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='approved_requests_spv1', null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_('penyetuju (Atasan Peminta)'))
    supervisor1_decision_at = models.DateTimeField(_('tanggal keputusan spv1'), null=True, blank=True)
    supervisor1_rejection_reason = models.TextField(_('alasan penolakan spv1'), blank=True, null=True)
    supervisor2_approver = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='approved_requests_spv2', null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_('penyetuju (Atasan Operator)'))
    supervisor2_decision_at = models.DateTimeField(_('tanggal keputusan spv2'), null=True, blank=True)
    supervisor2_rejection_reason = models.TextField(_('alasan penolakan spv2'), blank=True, null=True)
    operator_processor = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='processed_requests_opr', null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_('pemroses (Operator)'))
    operator_processed_at = models.DateTimeField(_('tanggal diproses operator'), null=True, blank=True)
    operator_rejection_reason = models.TextField(_('alasan penolakan operator'), blank=True, null=True)
    received_at = models.DateTimeField(_('diterima peminta tanggal'), null=True, blank=True)

    class Meta:
        verbose_name = _('Permintaan Barang')
        verbose_name_plural = _('Permintaan Barang')
        ordering = ['-created_at']

    def __str__(self):
        requester_display = getattr(self.requester, 'email', self.requester_id)
        return self.request_number or f"Draft Request by {requester_display}"

    def save(self, *args, **kwargs):
        if not self.request_number and self.status != self.Status.DRAFT:
            self.request_number = self._generate_request_number()
        super().save(*args, **kwargs)

    def _generate_request_number(self):
        if not self.requester_id or not getattr(self.requester, 'department_code', None):
             return None
        year = timezone.now().year
        department_code = self.requester.department_code
        prefix = f"ND-"
        suffix = f"/{department_code}/PS/{year}"
        last_request = Request.objects.filter(request_number__startswith=prefix, request_number__endswith=suffix).exclude(pk=self.pk).order_by('request_number').last()
        sequence = 1
        if last_request and last_request.request_number:
            try:
                last_seq_str = last_request.request_number.replace(prefix, "").split('/')[0]
                sequence = int(last_seq_str) + 1
            except (IndexError, ValueError, TypeError):
                 count = Request.objects.filter(request_number__startswith=prefix, request_number__endswith=suffix).exclude(pk=self.pk).count()
                 sequence = count + 1
        return f"{prefix}{sequence:02d}{suffix}"

# --- MODEL ITEM PERMINTAAN ---
class RequestItem(models.Model):
    request = models.ForeignKey(Request, related_name='items', on_delete=models.CASCADE, verbose_name=_('permintaan'))
    variant = models.ForeignKey(ProductVariant, related_name='requested_in', on_delete=models.PROTECT, verbose_name=_('varian produk'))
    quantity_requested = models.PositiveIntegerField(_('jumlah diminta'))
    quantity_approved_spv2 = models.PositiveIntegerField(_('jumlah disetujui Atasan Operator'), null=True, blank=True)
    quantity_issued = models.PositiveIntegerField(_('jumlah dikeluarkan'), default=0)

    class Meta:
        verbose_name = _('Item Permintaan')
        verbose_name_plural = _('Item Permintaan')
        unique_together = ('request', 'variant')

    def __str__(self):
        variant_name = getattr(getattr(self.variant, 'name', None), 'N/A')
        return f"{variant_name} - Diminta: {self.quantity_requested}"

    def clean(self):
        if self.quantity_approved_spv2 is not None and self.quantity_approved_spv2 > self.quantity_requested:
            raise ValidationError(_('Jumlah disetujui tidak boleh melebihi jumlah yang diminta.'))

# --- MODEL SPMB ---
class SPMB(models.Model):
    request = models.OneToOneField(Request, related_name='spmb_document', on_delete=models.CASCADE, verbose_name=_('permintaan terkait'))
    spmb_number = models.CharField(_('nomor SPMB'), max_length=50, unique=True, editable=False)
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='spmb_issued', on_delete=models.PROTECT, verbose_name=_('diterbitkan oleh (Operator)'))
    issued_at = models.DateTimeField(_('diterbitkan tanggal'), default=timezone.now)

    class Meta:
        verbose_name = _('SPMB')
        verbose_name_plural = _('SPMB')
        ordering = ['-issued_at']

    def __str__(self):
        return self.spmb_number

    def save(self, *args, **kwargs):
        if not self.spmb_number:
            self.spmb_number = self._generate_spmb_number()
        super().save(*args, **kwargs)

    def _generate_spmb_number(self):
        year = timezone.now().year
        wbc_code = "WBC.05" # HARDCODED - Perlu dikonfirmasi!
        prefix = f"SPMB-"
        suffix = f"/{wbc_code}/PS/{year}"
        last_spmb = SPMB.objects.filter(spmb_number__startswith=prefix, spmb_number__endswith=suffix).exclude(pk=self.pk).order_by('spmb_number').last()
        sequence = 1
        if last_spmb and last_spmb.spmb_number:
            try:
                last_seq_str = last_spmb.spmb_number.replace(prefix, "").split('/')[0]
                sequence = int(last_seq_str) + 1
            except (IndexError, ValueError, TypeError):
                 count = SPMB.objects.filter(spmb_number__startswith=prefix, spmb_number__endswith=suffix).exclude(pk=self.pk).count()
                 sequence = count + 1
        return f"{prefix}{sequence:02d}{suffix}"

# --- MODEL LOG PERMINTAAN ---
class RequestLog(models.Model):
    request = models.ForeignKey(Request, related_name='logs', on_delete=models.CASCADE, verbose_name=_('permintaan'))
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_('pengguna'))
    timestamp = models.DateTimeField(_('waktu'), auto_now_add=True)
    action = models.CharField(_('aksi'), max_length=50)
    status_from = models.CharField(_('status dari'), max_length=20, choices=Request.Status.choices, null=True, blank=True)
    status_to = models.CharField(_('status ke'), max_length=20, choices=Request.Status.choices, null=True, blank=True)
    comment = models.TextField(_('komentar/catatan'), blank=True, null=True)

    class Meta:
        verbose_name = _('Log Permintaan')
        verbose_name_plural = _('Log Permintaan')
        ordering = ['timestamp']

    def __str__(self):
        user_display = getattr(self.user, 'email', 'System')
        return f"{self.timestamp.strftime('%Y-%m-%d %H:%M')} - {self.request} - {self.action} by {user_display}"

# --- MODEL TRANSAKSI STOK ---
class Transaction(models.Model):
    class Type(models.TextChoices):
        IN = 'IN', _('Masuk')
        OUT = 'OUT', _('Keluar')
        ADJUSTMENT = 'ADJUST', _('Penyesuaian')

    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, verbose_name=_('varian produk'))
    inventory_item = models.ForeignKey(InventoryItem, null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_('item inventaris terkait'))
    quantity = models.IntegerField(_('jumlah'), help_text="Positif untuk IN/ADJUST+, Negatif untuk OUT/ADJUST-")
    transaction_type = models.CharField(_('tipe transaksi'), max_length=10, choices=Type.choices)
    timestamp = models.DateTimeField(_('waktu transaksi'), default=timezone.now)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_('pengguna'))
    related_request = models.ForeignKey(Request, null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_('permintaan terkait'))
    related_spmb = models.ForeignKey(SPMB, null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_('SPMB terkait'))
    receipt = models.ForeignKey(Receipt, null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_('kuitansi terkait'))
    notes = models.TextField(_('catatan'), blank=True, null=True)

    class Meta:
        verbose_name = _('Transaksi Stok')
        verbose_name_plural = _('Transaksi Stok')
        ordering = ['-timestamp']

    def __str__(self):
        direction = "+" if self.quantity > 0 else ""
        variant_name = getattr(getattr(self, 'variant', None), 'name', 'N/A')
        return f"{self.timestamp.strftime('%Y-%m-%d %H:%M')} - {variant_name}: {direction}{self.quantity} ({self.transaction_type})"

# --- MODEL STOCK OPNAME ---
class StockOpnameSession(models.Model):
    class Status(models.TextChoices):
        PENDING_CONFIRMATION = 'PENDING', _('Menunggu Konfirmasi Perbedaan')
        COMPLETED = 'COMPLETED', _('Selesai')

    opname_date = models.DateField(_('tanggal opname'), default=timezone.now)
    uploaded_file = models.FileField(_('file unggahan'), upload_to='stock_opname/%Y/%m/', blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='opname_sessions_created', on_delete=models.PROTECT, verbose_name=_('dibuat oleh (Admin)'))
    created_at = models.DateTimeField(_('dibuat tanggal'), auto_now_add=True)
    status = models.CharField(_('status sesi'), max_length=20, choices=Status.choices, default=Status.PENDING_CONFIRMATION)
    notes = models.TextField(_('catatan sesi'), blank=True, null=True)

    class Meta:
        verbose_name = _('Sesi Stock Opname')
        verbose_name_plural = _('Sesi Stock Opname')
        ordering = ['-opname_date']

    def __str__(self):
        return f"Stock Opname {self.opname_date.strftime('%Y-%m-%d')}"

class StockOpnameItem(models.Model):
    class ConfirmationStatus(models.TextChoices):
        PENDING = 'PENDING', _('Menunggu Konfirmasi')
        CONFIRMED_MATCH = 'MATCH', _('Dikonfirmasi (Sesuai)')
        CONFIRMED_ADJUST = 'ADJUST', _('Dikonfirmasi (Perlu Penyesuaian)')
        REJECTED = 'REJECTED', _('Ditolak (Perlu Investigasi)')

    opname_session = models.ForeignKey(StockOpnameSession, related_name='items', on_delete=models.CASCADE, verbose_name=_('sesi opname'))
    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, verbose_name=_('varian produk'))
    system_quantity = models.IntegerField(_('jumlah sistem'))
    counted_quantity = models.IntegerField(_('jumlah hitung fisik'))
    difference = models.IntegerField(_('selisih'), editable=False)
    confirmation_status = models.CharField(_('status konfirmasi'), max_length=10, choices=ConfirmationStatus.choices, default=ConfirmationStatus.PENDING)
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='confirmed_opname_items', null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_('dikonfirmasi oleh (Operator)'))
    confirmation_notes = models.TextField(_('catatan konfirmasi'), blank=True, null=True)
    confirmed_at = models.DateTimeField(_('dikonfirmasi tanggal'), null=True, blank=True)

    class Meta:
        verbose_name = _('Item Stock Opname')
        verbose_name_plural = _('Item Stock Opname')
        ordering = ['opname_session', 'variant__full_code']
        unique_together = ('opname_session', 'variant')

    def save(self, *args, **kwargs):
        self.difference = self.counted_quantity - self.system_quantity
        super().save(*args, **kwargs)

    def __str__(self):
        variant_display = getattr(getattr(self, 'variant', None), 'name', 'N/A')
        session_date = getattr(self.opname_session, 'opname_date', None)
        date_str = session_date.strftime('%Y-%m-%d') if session_date else 'N/A'
        return f"{variant_display} (Opname {date_str}) - Selisih: {self.difference}"

