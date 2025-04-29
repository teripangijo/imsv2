# backend/inventory/models.py
from django.db import models
from django.conf import settings # Untuk mengakses AUTH_USER_MODEL
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
import uuid # Untuk nomor unik sementara jika diperlukan

# --- Model Dasar Barang ---

class ProductCategory(models.Model):
    """Merepresentasikan Jenis Barang (e.g., ATK, Komputer)"""
    name = models.CharField(_('nama kategori'), max_length=100, unique=True)
    description = models.TextField(_('deskripsi'), blank=True, null=True)

    class Meta:
        verbose_name = _('Kategori Produk')
        verbose_name_plural = _('Kategori Produk')
        ordering = ['name']

    def __str__(self):
        return self.name

class ProductVariant(models.Model):
    """Merepresentasikan Varian Barang spesifik (e.g., Pulpen Snowman 0.5)"""
    category = models.ForeignKey(ProductCategory, related_name='variants', on_delete=models.PROTECT, verbose_name=_('kategori'))
    name = models.CharField(_('nama varian'), max_length=150)
    description = models.TextField(_('deskripsi'), blank=True, null=True)
    unit_of_measure = models.CharField(_('satuan'), max_length=20, default='pcs', help_text="Contoh: pcs, box, rim, unit")
    # Tambahkan field lain jika perlu, misal: gambar, kode barang internal

    class Meta:
        verbose_name = _('Varian Produk')
        verbose_name_plural = _('Varian Produk')
        unique_together = ('category', 'name') # Varian harus unik dalam satu kategori
        ordering = ['category', 'name']

    def __str__(self):
        return f"{self.category.name} - {self.name}"

# --- Model Stok ---

class InventoryItem(models.Model):
    """Item spesifik dalam stok, mencatat batch masuk untuk FIFO"""
    variant = models.ForeignKey(ProductVariant, related_name='inventory_items', on_delete=models.PROTECT, verbose_name=_('varian produk'))
    quantity = models.PositiveIntegerField(_('jumlah'))
    purchase_price = models.DecimalField(_('harga beli'), max_digits=15, decimal_places=2, blank=True, null=True, help_text="Harga per satuan")
    entry_date = models.DateTimeField(_('tanggal masuk'), default=timezone.now)
    expiry_date = models.DateField(_('tanggal kadaluarsa'), blank=True, null=True)
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='added_inventory_items', null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_('ditambahkan oleh'))
    # Bisa ditambah: nomor batch, supplier, etc.

    class Meta:
        verbose_name = _('Item Inventaris (Batch)')
        verbose_name_plural = _('Item Inventaris (Batch)')
        ordering = ['entry_date', 'id'] # Urutan FIFO berdasarkan tanggal masuk

    def __str__(self):
        return f"{self.variant} ({self.quantity} {self.variant.unit_of_measure}) - Masuk: {self.entry_date.strftime('%Y-%m-%d')}"

class Stock(models.Model):
    """Mencatat jumlah total stok terkini per varian"""
    variant = models.OneToOneField(ProductVariant, related_name='stock_level', on_delete=models.CASCADE, primary_key=True, verbose_name=_('varian produk'))
    total_quantity = models.PositiveIntegerField(_('total kuantitas'), default=0)
    low_stock_threshold = models.PositiveIntegerField(_('ambang batas stok rendah'), default=10, blank=True, null=True)
    last_updated = models.DateTimeField(_('terakhir diperbarui'), auto_now=True)

    class Meta:
        verbose_name = _('Level Stok')
        verbose_name_plural = _('Level Stok')
        ordering = ['variant__name']

    def __str__(self):
        return f"Stok {self.variant}: {self.total_quantity}"

    @property
    def is_low_stock(self):
        if self.low_stock_threshold is None:
            return False
        return self.total_quantity <= self.low_stock_threshold

    @property
    def is_out_of_stock(self):
        return self.total_quantity <= 0

# --- Model Permintaan Barang ---
# PERHATIKAN: Definisi Request SEKARANG di atas RequestItem

class Request(models.Model):
    """Merepresentasikan satu pengajuan permintaan barang"""
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', _('Draft')
        SUBMITTED = 'SUBMITTED', _('Diajukan (Menunggu Atasan Peminta)')
        REJECTED_SPV1 = 'REJECTED_SPV1', _('Ditolak Atasan Peminta')
        APPROVED_SPV1 = 'APPROVED_SPV1', _('Disetujui Atasan Peminta (Menunggu Atasan Operator)')
        REJECTED_SPV2 = 'REJECTED_SPV2', _('Ditolak Atasan Operator')
        APPROVED_SPV2 = 'APPROVED_SPV2', _('Disetujui Atasan Operator (Menunggu Operator)')
        PROCESSING = 'PROCESSING', _('Diproses Operator')
        REJECTED_OPR = 'REJECTED_OPR', _('Ditolak Operator') # Mungkin terjadi jika stok tiba2 habis?
        COMPLETED = 'COMPLETED', _('Selesai (Menunggu Konfirmasi Terima)')
        RECEIVED = 'RECEIVED', _('Barang Diterima Peminta')
        CANCELLED = 'CANCELLED', _('Dibatalkan') # Jika diperlukan

    requester = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='requests_made', on_delete=models.PROTECT, verbose_name=_('peminta'))
    request_number = models.CharField(_('nomor permintaan'), max_length=50, unique=True, blank=True, null=True, editable=False) # Diubah sedikit: blank=True, null=True agar bisa draft tanpa nomor
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
        return self.request_number or f"Draft Request by {self.requester.email or self.requester.id}" # Lebih aman jika email belum tentu ada

    def save(self, *args, **kwargs):
        # Generate nomor hanya jika belum ada DAN status bukan lagi DRAFT
        if not self.request_number and self.status != self.Status.DRAFT:
            self.request_number = self._generate_request_number()
        super().save(*args, **kwargs)

    def _generate_request_number(self):
        # Format: “ND-xx/WBC.xxx/PS/2025”
        # Pastikan requester sudah tersimpan dan memiliki department_code
        if not self.requester_id or not self.requester.department_code:
             # Handle case where requester or department code is missing before generating number
             # Mungkin return error atau nomor sementara? Untuk sekarang, anggap selalu ada saat submit.
             # Atau bisa dibuat unik sementara menggunakan UUID jika diperlukan
             # return f"TEMP-{uuid.uuid4().hex[:8]}" # Contoh fallback nomor sementara
             # Pilihan lain: validasi di level serializer/view agar request tidak bisa disubmit tanpa dept code
             return None # Atau raise error

        year = timezone.now().year
        department_code = self.requester.department_code
        prefix = f"ND-"
        suffix = f"/{department_code}/PS/{year}"

        # Cari nomor urut terakhir yang cocok dengan prefix dan suffix
        last_request = Request.objects.filter(
            request_number__startswith=prefix,
            request_number__endswith=suffix
        ).exclude(pk=self.pk).order_by('request_number').last() # Exclude self jika sedang update

        sequence = 1
        if last_request and last_request.request_number:
            try:
                last_seq_str = last_request.request_number.replace(prefix, "").split('/')[0]
                sequence = int(last_seq_str) + 1
            except (IndexError, ValueError, TypeError):
                # Fallback: Hitung jumlah request yang cocok di tahun/dept tersebut + 1
                # Ini kurang ideal jika ada nomor yang dihapus atau formatnya rusak
                 count = Request.objects.filter(
                     request_number__startswith=prefix,
                     request_number__endswith=suffix
                 ).exclude(pk=self.pk).count()
                 sequence = count + 1


        return f"{prefix}{sequence:02d}{suffix}"


class RequestItem(models.Model):
    """Item barang yang diminta dalam satu Request"""
    # Sekarang ForeignKey ini merujuk ke Request yang sudah didefinisikan di atas
    request = models.ForeignKey(Request, related_name='items', on_delete=models.CASCADE, verbose_name=_('permintaan'))
    variant = models.ForeignKey(ProductVariant, related_name='requested_in', on_delete=models.PROTECT, verbose_name=_('varian produk'))
    quantity_requested = models.PositiveIntegerField(_('jumlah diminta'))
    quantity_approved_spv2 = models.PositiveIntegerField(_('jumlah disetujui Atasan Operator'), null=True, blank=True)
    quantity_issued = models.PositiveIntegerField(_('jumlah dikeluarkan'), default=0)

    class Meta:
        verbose_name = _('Item Permintaan')
        verbose_name_plural = _('Item Permintaan')
        unique_together = ('request', 'variant') # Hanya boleh ada 1 baris per varian dalam 1 request

    def __str__(self):
        return f"{self.variant.name} - Diminta: {self.quantity_requested}"

    def clean(self):
        # Validasi sederhana: jumlah disetujui tidak boleh lebih dari diminta
        if self.quantity_approved_spv2 is not None and self.quantity_approved_spv2 > self.quantity_requested:
            raise ValidationError(_('Jumlah disetujui tidak boleh melebihi jumlah yang diminta.'))
        # Validasi jumlah dikeluarkan (mungkin lebih cocok di logic processing)
        # if self.quantity_issued > self.quantity_approved_spv2:
        #    raise ValidationError(_('Jumlah dikeluarkan tidak boleh melebihi jumlah yang disetujui.'))

class SPMB(models.Model):
    """Surat Perintah Mengeluarkan Barang"""
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
        # Format: “SPMB-xx/WBC.05/PS/2025” - Konfirmasi kode WBC.05
        # Jika dinamis (berdasarkan dept operator), perlu akses ke 'issued_by'
        # Namun 'issued_by' mungkin belum diset saat save() pertama kali dipanggil
        # Pendekatan: Generate saat object SPMB dibuat di view/logic, bukan di save() model?
        # Atau pastikan issued_by sudah ada saat save() dipanggil.

        year = timezone.now().year
        wbc_code = "WBC.05" # HARDCODED - Perlu dikonfirmasi!
        prefix = f"SPMB-"
        suffix = f"/{wbc_code}/PS/{year}"

        last_spmb = SPMB.objects.filter(
            spmb_number__startswith=prefix,
            spmb_number__endswith=suffix
        ).exclude(pk=self.pk).order_by('spmb_number').last()

        sequence = 1
        if last_spmb and last_spmb.spmb_number:
            try:
                last_seq_str = last_spmb.spmb_number.replace(prefix, "").split('/')[0]
                sequence = int(last_seq_str) + 1
            except (IndexError, ValueError, TypeError):
                 count = SPMB.objects.filter(
                    spmb_number__startswith=prefix,
                    spmb_number__endswith=suffix
                 ).exclude(pk=self.pk).count()
                 sequence = count + 1


        return f"{prefix}{sequence:02d}{suffix}"


# --- Model Logging dan Audit ---

class RequestLog(models.Model):
    """Mencatat histori perubahan status dan komentar pada Request"""
    request = models.ForeignKey(Request, related_name='logs', on_delete=models.CASCADE, verbose_name=_('permintaan'))
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_('pengguna'))
    timestamp = models.DateTimeField(_('waktu'), auto_now_add=True)
    action = models.CharField(_('aksi'), max_length=50) # e.g., 'SUBMIT', 'APPROVE_SPV1', 'REJECT_SPV2', 'COMMENT'
    status_from = models.CharField(_('status dari'), max_length=20, choices=Request.Status.choices, null=True, blank=True)
    status_to = models.CharField(_('status ke'), max_length=20, choices=Request.Status.choices, null=True, blank=True)
    comment = models.TextField(_('komentar/catatan'), blank=True, null=True)

    class Meta:
        verbose_name = _('Log Permintaan')
        verbose_name_plural = _('Log Permintaan')
        ordering = ['timestamp']

    def __str__(self):
        user_display = self.user.email if self.user else 'System'
        return f"{self.timestamp.strftime('%Y-%m-%d %H:%M')} - {self.request} - {self.action} by {user_display}"

class Transaction(models.Model):
    """Mencatat setiap pergerakan stok (masuk/keluar)"""
    class Type(models.TextChoices):
        IN = 'IN', _('Masuk')
        OUT = 'OUT', _('Keluar')
        ADJUSTMENT = 'ADJUST', _('Penyesuaian') # Untuk stock opname

    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, verbose_name=_('varian produk'))
    inventory_item = models.ForeignKey(InventoryItem, null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_('item inventaris terkait')) # Untuk OUT/ADJUSTMENT dari batch spesifik
    quantity = models.IntegerField(_('jumlah'), help_text="Positif untuk IN/ADJUST+, Negatif untuk OUT/ADJUST-")
    transaction_type = models.CharField(_('tipe transaksi'), max_length=10, choices=Type.choices)
    timestamp = models.DateTimeField(_('waktu transaksi'), default=timezone.now)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_('pengguna'))
    related_request = models.ForeignKey(Request, null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_('permintaan terkait'))
    related_spmb = models.ForeignKey(SPMB, null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_('SPMB terkait'))
    notes = models.TextField(_('catatan'), blank=True, null=True) # Misal: "Penerimaan PO#123", "Stock Opname Adjustment"

    class Meta:
        verbose_name = _('Transaksi Stok')
        verbose_name_plural = _('Transaksi Stok')
        ordering = ['-timestamp']

    def __str__(self):
        # Kode ini sudah benar secara Python
        direction = "+" if self.quantity > 0 else ""
        return f"{self.timestamp.strftime('%Y-%m-%d %H:%M')} - {self.variant.name}: {direction}{self.quantity} ({self.transaction_type})"


# --- Model Stock Opname ---

class StockOpnameSession(models.Model):
    """Sesi pelaksanaan stock opname"""
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
    """Detail item dalam satu sesi stock opname, menyoroti perbedaan"""
    class ConfirmationStatus(models.TextChoices):
        PENDING = 'PENDING', _('Menunggu Konfirmasi')
        CONFIRMED_MATCH = 'MATCH', _('Dikonfirmasi (Sesuai)')
        CONFIRMED_ADJUST = 'ADJUST', _('Dikonfirmasi (Perlu Penyesuaian)')
        REJECTED = 'REJECTED', _('Ditolak (Perlu Investigasi)')

    opname_session = models.ForeignKey(StockOpnameSession, related_name='items', on_delete=models.CASCADE, verbose_name=_('sesi opname'))
    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, verbose_name=_('varian produk'))
    system_quantity = models.IntegerField(_('jumlah sistem'))
    counted_quantity = models.IntegerField(_('jumlah hitung fisik'))
    difference = models.IntegerField(_('selisih'), editable=False) # Akan dihitung otomatis
    confirmation_status = models.CharField(_('status konfirmasi'), max_length=10, choices=ConfirmationStatus.choices, default=ConfirmationStatus.PENDING)
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='confirmed_opname_items', null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_('dikonfirmasi oleh (Operator)'))
    confirmation_notes = models.TextField(_('catatan konfirmasi'), blank=True, null=True)
    confirmed_at = models.DateTimeField(_('dikonfirmasi tanggal'), null=True, blank=True)
    # Mungkin perlu field untuk adjustment transaction ID setelah dikonfirmasi 'ADJUST'

    class Meta:
        verbose_name = _('Item Stock Opname')
        verbose_name_plural = _('Item Stock Opname')
        ordering = ['opname_session', 'variant__name']
        unique_together = ('opname_session', 'variant') # Satu varian per sesi opname

    def save(self, *args, **kwargs):
        self.difference = self.counted_quantity - self.system_quantity
        super().save(*args, **kwargs)

    def __str__(self):
        variant_name = self.variant.name if self.variant else 'N/A'
        session_date = self.opname_session.opname_date.strftime('%Y-%m-%d') if self.opname_session else 'N/A'
        return f"{variant_name} (Opname {session_date}) - Selisih: {self.difference}"