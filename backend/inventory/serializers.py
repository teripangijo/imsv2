# backend/inventory/serializers.py
from rest_framework import serializers
from django.utils import timezone
from decimal import Decimal
from .models import (
    # Model hierarki kode baru
    ItemCodeGolongan, ItemCodeBidang, ItemCodeKelompok, ItemCodeSubKelompok, ItemCodeBarang,
    # Model utama yg dimodifikasi/digunakan
    ProductVariant, InventoryItem, Stock, Receipt,
    # Model lain (request, spmb, log, transaksi, opname)
    Request, RequestItem, SPMB, RequestLog, Transaction,
    StockOpnameSession, StockOpnameItem
)
# Impor serializer user & model user
from users.serializers import BasicUserSerializer, UserSerializer
from users.models import CustomUser
from django.utils.translation import gettext_lazy as _ 

# --- Serializer Baru untuk Laporan Konsumsi ---

class ConsumptionReportSerializer(serializers.Serializer):
    """
    Serializer untuk menampilkan data laporan konsumsi barang per unit/peminta.
    Data ini biasanya hasil dari anotasi/agregasi di ViewSet, bukan ModelSerializer langsung.
    """
    # Field dari agregasi/anotasi (nama field ini akan kita tentukan di ViewSet)

    # Info Unit/Peminta (tergantung grouping di ViewSet)
    department_code = serializers.CharField(read_only=True, required=False, allow_null=True)
    requester_id = serializers.IntegerField(read_only=True, required=False, allow_null=True)
    requester_email = serializers.EmailField(read_only=True, required=False, allow_null=True)
    requester_full_name = serializers.CharField(read_only=True, required=False, allow_null=True)

    # Info Barang yang dikonsumsi
    variant_id = serializers.IntegerField(read_only=True)
    variant_full_code = serializers.CharField(read_only=True)
    variant_type_name = serializers.CharField(read_only=True)
    variant_name = serializers.CharField(read_only=True) # Nama spesifik
    variant_unit = serializers.CharField(read_only=True)

    # Hasil Agregasi
    total_quantity_consumed = serializers.IntegerField(read_only=True)

    # Kita tidak pakai Meta class karena bukan ModelSerializer

# --- Serializer untuk Hierarki Kode ---
class ItemCodeGolonganSerializer(serializers.ModelSerializer):
    class Meta: model = ItemCodeGolongan; fields = '__all__'
class ItemCodeBidangSerializer(serializers.ModelSerializer):
    golongan_code = serializers.CharField(source='golongan.code', read_only=True)
    class Meta: model = ItemCodeBidang; fields = '__all__'
class ItemCodeKelompokSerializer(serializers.ModelSerializer):
    bidang_full_code = serializers.SerializerMethodField()
    class Meta: model = ItemCodeKelompok; fields = '__all__'
    def get_bidang_full_code(self, obj): return f"{obj.bidang.golongan.code}.{obj.bidang.code}"
class ItemCodeSubKelompokSerializer(serializers.ModelSerializer):
    kelompok_full_code = serializers.SerializerMethodField()
    class Meta: model = ItemCodeSubKelompok; fields = '__all__'
    def get_kelompok_full_code(self, obj): bidang = obj.kelompok.bidang; return f"{bidang.golongan.code}.{bidang.code}.{obj.kelompok.code}"
class ItemCodeBarangSerializer(serializers.ModelSerializer):
    sub_kelompok_full_code = serializers.CharField(source='sub_kelompok.get_base_code_prefix', read_only=True)
    full_base_code = serializers.CharField(source='full_base_code', read_only=True) # Gunakan field yg tersimpan
    class Meta: model = ItemCodeBarang; fields = ('id', 'sub_kelompok', 'sub_kelompok_full_code', 'code', 'base_description', 'full_base_code', 'account_code', 'account_description')

# --- Serializer untuk Varian Produk Spesifik (DEFINISIKAN SEBELUM DIGUNAKAN) ---
class ProductVariantSerializer(serializers.ModelSerializer):
    """Serializer untuk Varian Produk Spesifik (misal: Aspal Pertamina)."""
    base_item_code = ItemCodeBarangSerializer(read_only=True)
    base_item_code_id = serializers.PrimaryKeyRelatedField(
        queryset=ItemCodeBarang.objects.all(), source='base_item_code', write_only=True
    )
    # Kode specific & full adalah read-only (di-generate model)
    specific_code = serializers.CharField(read_only=True)
    full_code = serializers.CharField(read_only=True)
    # Tambahkan barcode sebagai read-only field
    barcode = serializers.CharField(read_only=True) # <-- TAMBAHKAN INI

    class Meta:
        model = ProductVariant
        fields = (
            'id',
            'base_item_code',         # Nested object saat GET
            'base_item_code_id',      # ID untuk POST/PUT
            'specific_code',          # Kode 3 digit (read-only)
            'full_code',              # Kode lengkap (read-only)
            'barcode',                # Barcode (read-only) <-- TAMBAHKAN INI
            'type_name',              # Jenis Barang
            'name',                   # Nama spesifik (merk/tipe)
            'description',            # Deskripsi tambahan (opsional)
            'unit_of_measure'         # Satuan (pcs, rim, dll.)
        )
        # Barcode juga read-only karena di-generate otomatis
        read_only_fields = ('specific_code', 'full_code', 'barcode')

# --- Serializer Stok ---
class StockSerializer(serializers.ModelSerializer):
    variant = ProductVariantSerializer(read_only=True) # Sekarang ProductVariantSerializer sudah ada
    is_low_stock = serializers.BooleanField(read_only=True)
    is_out_of_stock = serializers.BooleanField(read_only=True)
    class Meta: model = Stock; fields = ('variant', 'total_quantity', 'low_stock_threshold', 'last_updated', 'is_low_stock', 'is_out_of_stock')

# --- Serializer Item Inventaris ---
class InventoryItemSerializer(serializers.ModelSerializer):
    variant = ProductVariantSerializer(read_only=True) # Sekarang ProductVariantSerializer sudah ada
    added_by = BasicUserSerializer(read_only=True)
    receipt_id = serializers.PrimaryKeyRelatedField(source='receipt', read_only=True, allow_null=True) # Allow null jika receipt opsional
    class Meta: model = InventoryItem; fields = ('id', 'variant', 'quantity', 'purchase_price', 'entry_date', 'expiry_date', 'added_by', 'receipt', 'receipt_id'); read_only_fields = ('entry_date', 'added_by', 'receipt_id')
    def to_representation(self, instance):
        ret = super().to_representation(instance)
        if 'request' not in self.context: ret.pop('purchase_price', None); return ret
        user = self.context['request'].user
        if not (user.is_authenticated and (user.role == CustomUser.Role.OPERATOR or user.role == CustomUser.Role.ATASAN_OPERATOR or user.is_admin)): ret.pop('purchase_price', None)
        return ret

class InventoryItemCreateSerializer(serializers.ModelSerializer):
    variant = serializers.PrimaryKeyRelatedField(queryset=ProductVariant.objects.all())
    receipt = serializers.PrimaryKeyRelatedField(queryset=Receipt.objects.all(), required=False, allow_null=True, help_text="ID Kuitansi Pembelian terkait (jika ada).")
    class Meta: model = InventoryItem; fields = ('variant', 'quantity', 'purchase_price', 'expiry_date', 'receipt')

# --- Serializer Kuitansi ---
class ReceiptSerializer(serializers.ModelSerializer):
    uploaded_by = BasicUserSerializer(read_only=True)
    class Meta: model = Receipt; fields = '__all__'

# --- Serializer Permintaan ---
class RequestItemSerializer(serializers.ModelSerializer):
    variant = ProductVariantSerializer(read_only=True) # Sekarang ProductVariantSerializer sudah ada
    variant_id = serializers.PrimaryKeyRelatedField(queryset=ProductVariant.objects.all(), source='variant', write_only=True)
    class Meta: model = RequestItem; fields = ('id', 'variant', 'variant_id', 'quantity_requested', 'quantity_approved_spv2', 'quantity_issued'); read_only_fields = ('quantity_approved_spv2', 'quantity_issued')

class RequestListSerializer(serializers.ModelSerializer):
    requester = BasicUserSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    spmb_number = serializers.CharField(source='spmb_document.spmb_number', read_only=True, allow_null=True, default=None)
    class Meta: model = Request; fields = ('id', 'request_number', 'requester', 'status', 'status_display', 'created_at', 'submitted_at', 'supervisor1_decision_at', 'supervisor2_decision_at', 'operator_processed_at', 'received_at', 'spmb_number'); read_only_fields = fields

class RequestDetailSerializer(serializers.ModelSerializer):
    requester = BasicUserSerializer(read_only=True); supervisor1_approver = BasicUserSerializer(read_only=True); supervisor2_approver = BasicUserSerializer(read_only=True); operator_processor = BasicUserSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    items = RequestItemSerializer(many=True, read_only=True) # Menggunakan RequestItemSerializer yg sudah benar
    # Gunakan PrimaryKeyRelatedField jika Hyperlinked tidak disetup
    spmb_document = serializers.PrimaryKeyRelatedField(read_only=True, allow_null=True)
    # spmb_document = serializers.HyperlinkedRelatedField(view_name='spmb-detail', read_only=True, allow_null=True) # Jika pakai Hyperlinked
    class Meta: model = Request; fields = ('id', 'request_number', 'requester', 'status', 'status_display', 'created_at','submitted_at', 'supervisor1_approver', 'supervisor1_decision_at', 'supervisor1_rejection_reason','supervisor2_approver', 'supervisor2_decision_at', 'supervisor2_rejection_reason','operator_processor', 'operator_processed_at', 'operator_rejection_reason','received_at', 'items', 'spmb_document'); read_only_fields = fields

class RequestCreateSerializer(serializers.ModelSerializer):
    items = RequestItemSerializer(many=True) # Menggunakan RequestItemSerializer yg sudah benar
    class Meta: model = Request; fields = ('id', 'items'); read_only_fields = ('id',)
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        # Pastikan requester ada di validated_data (dari view)
        request_obj = Request.objects.create(**validated_data)
        for item_data in items_data: RequestItem.objects.create(request=request_obj, **item_data)
        return request_obj

# --- Serializer SPMB ---
class SPMBSerializer(serializers.ModelSerializer):
    request = RequestListSerializer(read_only=True) # Menggunakan RequestListSerializer yg sudah ada
    issued_by = BasicUserSerializer(read_only=True)
    class Meta: model = SPMB; fields = ('id', 'spmb_number', 'request', 'issued_by', 'issued_at'); read_only_fields = fields

# --- Serializer Log & Transaksi ---
class RequestLogSerializer(serializers.ModelSerializer):
    user = BasicUserSerializer(read_only=True)
    status_from_display = serializers.CharField(source='get_status_from_display', read_only=True, allow_null=True)
    status_to_display = serializers.CharField(source='get_status_to_display', read_only=True, allow_null=True)
    class Meta: model = RequestLog; fields = ('id', 'request', 'user', 'timestamp', 'action', 'status_from', 'status_from_display', 'status_to', 'status_to_display', 'comment'); read_only_fields = fields

class TransactionSerializer(serializers.ModelSerializer):
    variant = ProductVariantSerializer(read_only=True) # Sekarang ProductVariantSerializer sudah ada
    user = BasicUserSerializer(read_only=True)
    inventory_item_info = serializers.CharField(source='inventory_item.__str__', read_only=True, allow_null=True)
    transaction_type_display = serializers.CharField(source='get_transaction_type_display', read_only=True)
    related_request_number = serializers.CharField(source='related_request.request_number', read_only=True, allow_null=True)
    related_spmb_number = serializers.CharField(source='related_spmb.spmb_number', read_only=True, allow_null=True)
    receipt_number = serializers.CharField(source='receipt.receipt_number', read_only=True, allow_null=True)
    class Meta: model = Transaction; fields = ('id','timestamp','variant','quantity','transaction_type','transaction_type_display','user','inventory_item','inventory_item_info','related_request','related_request_number','related_spmb','related_spmb_number','receipt','receipt_number','notes'); read_only_fields = fields

# --- Serializer Stock Opname ---
class StockOpnameItemSerializer(serializers.ModelSerializer):
    variant = ProductVariantSerializer(read_only=True) # Sekarang ProductVariantSerializer sudah ada
    confirmed_by = BasicUserSerializer(read_only=True)
    confirmation_status_display = serializers.CharField(source='get_confirmation_status_display', read_only=True)
    class Meta: model = StockOpnameItem; fields = ('id', 'opname_session', 'variant', 'system_quantity', 'counted_quantity', 'difference', 'notes', 'confirmation_status','confirmation_status_display', 'confirmed_by', 'confirmation_notes', 'confirmed_at'); read_only_fields = ('difference',)

class StockOpnameSessionSerializer(serializers.ModelSerializer):
    created_by = BasicUserSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    class Meta: model = StockOpnameSession; fields = ('id', 'opname_date', 'uploaded_file', 'created_by', 'created_at', 'status', 'status_display', 'notes'); read_only_fields = ('created_at', 'created_by', 'status', 'status_display')

class StockOpnameFileUploadSerializer(serializers.Serializer):
    file = serializers.FileField(required=True)
    opname_date = serializers.DateField(required=False, default=timezone.now().date())
    notes = serializers.CharField(required=False, allow_blank=True)

class StockOpnameConfirmSerializer(serializers.Serializer):
    confirmation_status = serializers.ChoiceField(choices=StockOpnameItem.ConfirmationStatus.choices, required=True)
    confirmation_notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    def validate_confirmation_status(self, value):
        if value == StockOpnameItem.ConfirmationStatus.PENDING: raise serializers.ValidationError(_("Tidak dapat mengkonfirmasi ke status PENDING."))
        return value

# --- Serializer Laporan ---
class CurrentStockReportSerializer(serializers.ModelSerializer):
    full_code = serializers.CharField(source='variant.full_code', read_only=True); type_name = serializers.CharField(source='variant.type_name', read_only=True); variant_name = serializers.CharField(source='variant.name', read_only=True); unit_of_measure = serializers.CharField(source='variant.unit_of_measure', read_only=True); base_item_description = serializers.CharField(source='variant.base_item_code.base_description', read_only=True); account_code = serializers.CharField(source='variant.base_item_code.account_code', read_only=True); is_low_stock = serializers.BooleanField(read_only=True); is_out_of_stock = serializers.BooleanField(read_only=True)
    class Meta: model = Stock; fields = ['full_code','type_name','variant_name','base_item_description','unit_of_measure','total_quantity','low_stock_threshold','last_updated','is_low_stock','is_out_of_stock','account_code']

class StockValueFIFOReportSerializer(serializers.ModelSerializer):
    full_code = serializers.CharField(source='variant.full_code', read_only=True); type_name = serializers.CharField(source='variant.type_name', read_only=True); variant_name = serializers.CharField(source='variant.name', read_only=True); unit_of_measure = serializers.CharField(source='variant.unit_of_measure', read_only=True); base_item_description = serializers.CharField(source='variant.base_item_code.base_description', read_only=True); total_quantity = serializers.IntegerField(read_only=True); fifo_total_value = serializers.DecimalField(max_digits=19, decimal_places=2, read_only=True, default=Decimal('0.00'))
    class Meta: model = Stock; fields = ['full_code','type_name','variant_name','base_item_description','unit_of_measure','total_quantity','fifo_total_value']

class MovingItemsReportSerializer(serializers.ModelSerializer):
    full_code = serializers.CharField(read_only=True); type_name = serializers.CharField(read_only=True); variant_name = serializers.CharField(source='name', read_only=True); unit_of_measure = serializers.CharField(read_only=True); base_item_description = serializers.CharField(source='base_item_code.base_description', read_only=True); total_quantity_issued = serializers.IntegerField(read_only=True)
    class Meta: model = ProductVariant; fields = ['id','full_code','type_name','variant_name','base_item_description','unit_of_measure','total_quantity_issued']

# --- Serializer Upload Kuitansi ---
class ReceiptUploadSerializer(serializers.Serializer):
    file = serializers.FileField(required=True, help_text="File Excel (.xlsx) atau CSV (.csv) berisi detail pembelian.")

# --- Serializer untuk Laporan/Detail Transaksi ---

class TransactionSerializer(serializers.ModelSerializer):
    """
    Serializer untuk menampilkan detail transaksi stok.
    Digunakan untuk laporan histori keluar masuk barang.
    """
    # Tampilkan detail varian menggunakan serializer yang sudah ada
    variant = ProductVariantSerializer(read_only=True)
    # Tampilkan info user yang melakukan transaksi
    user = BasicUserSerializer(read_only=True)
    # Tampilkan info ringkas batch inventory terkait (jika ada)
    inventory_item_info = serializers.CharField(source='inventory_item.__str__', read_only=True, allow_null=True)
    # Tampilkan display name untuk tipe transaksi
    transaction_type_display = serializers.CharField(source='get_transaction_type_display', read_only=True)
    # Tampilkan nomor request terkait (jika ada)
    related_request_number = serializers.CharField(source='related_request.request_number', read_only=True, allow_null=True)
    # Tampilkan nomor SPMB terkait (jika ada)
    related_spmb_number = serializers.CharField(source='related_spmb.spmb_number', read_only=True, allow_null=True)
    # Tampilkan nomor kuitansi terkait (jika ada)
    receipt_number = serializers.CharField(source='receipt.receipt_number', read_only=True, allow_null=True)

    class Meta:
        model = Transaction
        fields = (
            'id',
            'timestamp',
            'variant', # Nested detail varian
            'quantity', # Jumlah (+/-)
            'transaction_type',
            'transaction_type_display', # Tipe (Masuk/Keluar/Penyesuaian)
            'user', # Info user pelaku
            'inventory_item', # ID batch terkait (jika ada)
            'inventory_item_info', # Info ringkas batch
            'related_request', # ID request terkait (jika ada)
            'related_request_number', # Nomor request
            'related_spmb', # ID SPMB terkait (jika ada)
            'related_spmb_number', # Nomor SPMB
            'receipt', # ID Kuitansi terkait (jika ada)
            'receipt_number', # Nomor Kuitansi
            'notes' # Catatan transaksi
        )
        # Read-only karena ini laporan histori
        read_only_fields = fields

# --- Serializer Baru untuk Laporan Slow/Fast Moving ---

class MovingItemsReportSerializer(serializers.ModelSerializer):
    """
    Serializer untuk menampilkan data laporan barang slow/fast moving.
    Menampilkan detail varian dan total kuantitas keluar dalam periode tertentu.
    """
    # Ambil field dari ProductVariant
    # Kita tidak bisa langsung source='variant...' karena instance yg diserialize adalah ProductVariant
    full_code = serializers.CharField(read_only=True)
    type_name = serializers.CharField(read_only=True)
    variant_name = serializers.CharField(source='name', read_only=True) # 'name' adalah nama spesifik
    unit_of_measure = serializers.CharField(read_only=True)

    # Ambil field dari ItemCodeBarang terkait
    base_item_description = serializers.CharField(source='base_item_code.base_description', read_only=True)

    # Field yang dihitung/dianotasi oleh ViewSet
    total_quantity_issued = serializers.IntegerField(read_only=True)

    class Meta:
        model = ProductVariant # Sumber data utama adalah ProductVariant
        fields = [
            'id', # Sertakan ID Varian
            'full_code',
            'type_name',
            'variant_name',
            'base_item_description',
            'unit_of_measure',
            'total_quantity_issued', # Jumlah keluar dalam periode
            # Tambahkan field lain dari ProductVariant jika perlu
        ]

# --- Serializer untuk Laporan Nilai Stok FIFO ---

class StockValueFIFOReportSerializer(serializers.ModelSerializer):
    """
    Serializer untuk menampilkan data laporan nilai stok menggunakan metode FIFO.
    Menampilkan detail varian, kuantitas, dan total nilai FIFO yang dihitung di View.
    """
    # Ambil field dari ProductVariant terkait
    full_code = serializers.CharField(source='variant.full_code', read_only=True)
    type_name = serializers.CharField(source='variant.type_name', read_only=True)
    variant_name = serializers.CharField(source='variant.name', read_only=True)
    unit_of_measure = serializers.CharField(source='variant.unit_of_measure', read_only=True)
    base_item_description = serializers.CharField(source='variant.base_item_code.base_description', read_only=True)

    # Field dari model Stock
    total_quantity = serializers.IntegerField(read_only=True)

    # Field untuk nilai FIFO yang dihitung di ViewSet
    # Nilai default ditambahkan untuk memastikan field ada meskipun kalkulasi belum terjadi
    fifo_total_value = serializers.DecimalField(max_digits=19, decimal_places=2, read_only=True, default=Decimal('0.00'))

    class Meta:
        model = Stock # Sumber data utama tetap Stock
        fields = [
            'full_code',
            'type_name',
            'variant_name',
            'base_item_description',
            'unit_of_measure',
            'total_quantity',
            'fifo_total_value', # Nilai FIFO yang dihitung
            # Tambahkan field lain jika perlu
        ]

# --- Serializers untuk Laporan Stok Terkini ---

class CurrentStockReportSerializer(serializers.ModelSerializer):
    """
    Serializer untuk menampilkan data laporan stok terkini.
    Mengambil data dari model Stock dan relasinya ke ProductVariant & ItemCodeBarang.
    """
    # Ambil field dari ProductVariant terkait
    full_code = serializers.CharField(source='variant.full_code', read_only=True)
    type_name = serializers.CharField(source='variant.type_name', read_only=True)
    variant_name = serializers.CharField(source='variant.name', read_only=True)
    unit_of_measure = serializers.CharField(source='variant.unit_of_measure', read_only=True)

    # Ambil field dari ItemCodeBarang terkait (melalui ProductVariant)
    base_item_description = serializers.CharField(source='variant.base_item_code.base_description', read_only=True)
    account_code = serializers.CharField(source='variant.base_item_code.account_code', read_only=True)

    # Field dari model Stock itu sendiri
    # total_quantity sudah ada di model Stock
    # low_stock_threshold sudah ada
    # last_updated sudah ada
    is_low_stock = serializers.BooleanField(read_only=True)
    is_out_of_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Stock # Sumber data utama adalah model Stock
        fields = [
            'full_code',                # Kode lengkap varian
            'type_name',                # Jenis Barang
            'variant_name',             # Nama Spesifik (Merk/Tipe)
            'base_item_description',    # Deskripsi dasar dari ItemCodeBarang
            'unit_of_measure',          # Satuan
            'total_quantity',           # Jumlah stok saat ini
            'low_stock_threshold',      # Ambang batas stok rendah
            'last_updated',             # Kapan stok terakhir diupdate
            'is_low_stock',             # Status stok rendah (boolean)
            'is_out_of_stock',          # Status stok habis (boolean)
            'account_code',             # Kode Akun terkait
        ]
        # Kita tidak perlu read_only_fields di sini karena semua source adalah read_only
        # atau berasal dari property model

class ItemCodeGolonganSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemCodeGolongan
        fields = '__all__'

class ItemCodeBidangSerializer(serializers.ModelSerializer):
    # Tampilkan kode golongan induk
    golongan_code = serializers.CharField(source='golongan.code', read_only=True)
    class Meta:
        model = ItemCodeBidang
        fields = '__all__' # Termasuk golongan_id, code, description

class ItemCodeKelompokSerializer(serializers.ModelSerializer):
    # Tampilkan kode bidang induk
    bidang_full_code = serializers.SerializerMethodField()
    class Meta:
        model = ItemCodeKelompok
        fields = '__all__' # Termasuk bidang_id, code, description

    def get_bidang_full_code(self, obj):
         return f"{obj.bidang.golongan.code}.{obj.bidang.code}"

class ItemCodeSubKelompokSerializer(serializers.ModelSerializer):
    # Tampilkan kode kelompok induk
    kelompok_full_code = serializers.SerializerMethodField()
    class Meta:
        model = ItemCodeSubKelompok
        fields = '__all__' # Termasuk kelompok_id, code, base_description

    def get_kelompok_full_code(self, obj):
         bidang = obj.kelompok.bidang
         return f"{bidang.golongan.code}.{bidang.code}.{obj.kelompok.code}"

class ItemCodeBarangSerializer(serializers.ModelSerializer):
    """Serializer untuk Kode Barang Dasar."""
    # Tampilkan kode subkelompok induk
    sub_kelompok_full_code = serializers.CharField(source='sub_kelompok.get_base_code_prefix', read_only=True)
    full_base_code = serializers.CharField(source='get_full_base_code', read_only=True) # Kode 10 digit

    class Meta:
        model = ItemCodeBarang
        # Tampilkan semua field, termasuk yg di-generate readonly
        fields = ('id', 'sub_kelompok', 'sub_kelompok_full_code', 'code',
                  'base_description', 'full_base_code',
                  'account_code', 'account_description')
        # 'sub_kelompok' (ID) dan 'code' diperlukan saat membuat/update

# --- Serializer untuk Varian Produk Spesifik (Modifikasi Besar) ---
class ProductVariantSerializer(serializers.ModelSerializer):
    """Serializer untuk Varian Produk Spesifik (misal: Aspal Pertamina)."""
    # Tampilkan detail Kode Barang Dasar secara nested saat read-only
    base_item_code = ItemCodeBarangSerializer(read_only=True)
    # Terima ID ItemCodeBarang saat membuat/update
    base_item_code_id = serializers.PrimaryKeyRelatedField(
        queryset=ItemCodeBarang.objects.all(), source='base_item_code', write_only=True
    )
    # Kode specific & full adalah read-only (di-generate model)
    specific_code = serializers.CharField(read_only=True)
    full_code = serializers.CharField(read_only=True)

    class Meta:
        model = ProductVariant
        fields = (
            'id',
            'base_item_code',         # Nested object saat GET
            'base_item_code_id',      # ID untuk POST/PUT
            'specific_code',          # Kode 3 digit (read-only)
            'full_code',              # Kode lengkap (read-only)
            'type_name',              # Nama tipe produk (wajib diisi user)
            'name',                   # Nama spesifik (wajib diisi user)
            'description',            # Deskripsi tambahan (opsional)
            'unit_of_measure'         # Satuan (pcs, rim, dll.)
        )
        # Kita tidak perlu unique_together di serializer, model yg handle
        read_only_fields = ('specific_code', 'full_code')

# --- Serializer Stok (Modifikasi Relasi) ---
class StockSerializer(serializers.ModelSerializer):
    # Relasi variant sekarang ke ProductVariantSerializer yg baru
    variant = ProductVariantSerializer(read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)
    is_out_of_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Stock
        fields = ('variant', 'total_quantity', 'low_stock_threshold', 'last_updated', 'is_low_stock', 'is_out_of_stock')

# --- Serializer Item Inventaris (Modifikasi Relasi + Tambah Receipt) ---
class InventoryItemSerializer(serializers.ModelSerializer):
    # Relasi variant sekarang ke ProductVariantSerializer yg baru
    variant = ProductVariantSerializer(read_only=True)
    added_by = BasicUserSerializer(read_only=True)
    # Tampilkan ID receipt jika ada
    receipt_id = serializers.PrimaryKeyRelatedField(source='receipt', read_only=True)

    class Meta:
        model = InventoryItem
        fields = (
            'id', 'variant', 'quantity', 'purchase_price', # Harga tetap ada
            'entry_date', 'expiry_date', 'added_by', 'receipt', 'receipt_id' # Tambah receipt & receipt_id
        )
        read_only_fields = ('entry_date', 'added_by', 'receipt_id')

    # Method to_representation untuk sembunyikan harga (tetap sama)
    def to_representation(self, instance):
        ret = super().to_representation(instance)
        if 'request' not in self.context:
             ret.pop('purchase_price', None)
             return ret
        user = self.context['request'].user
        if not (user.is_authenticated and (
                user.role == CustomUser.Role.OPERATOR or
                user.role == CustomUser.Role.ATASAN_OPERATOR or
                user.is_admin)):
            ret.pop('purchase_price', None)
        return ret

# --- Serializer Buat Item Inventaris (Modifikasi Relasi + Tambah Receipt) ---
class InventoryItemCreateSerializer(serializers.ModelSerializer):
    # variant adalah ID ProductVariant spesifik
    variant = serializers.PrimaryKeyRelatedField(queryset=ProductVariant.objects.all())
    # receipt adalah ID Receipt opsional yang sudah ada
    receipt = serializers.PrimaryKeyRelatedField(
        queryset=Receipt.objects.all(), required=False, allow_null=True, # Opsional
        help_text="ID Kuitansi Pembelian terkait (jika ada)."
    )
    # added_by akan diisi otomatis dari user yang login di view

    class Meta:
        model = InventoryItem
        # Field yang relevan untuk input barang masuk
        fields = ('variant', 'quantity', 'purchase_price', 'expiry_date', 'receipt')


# --- Serializer Kuitansi (Baru) ---
class ReceiptSerializer(serializers.ModelSerializer):
    uploaded_by = BasicUserSerializer(read_only=True)
    # inventory_items = InventoryItemSerializer(many=True, read_only=True) # Bisa ditambahkan jika ingin lihat item terkait

    class Meta:
        model = Receipt
        fields = '__all__'


# --- Penyesuaian Serializer Lain (RequestItem, Transaksi, Opname Item) ---

class RequestItemSerializer(serializers.ModelSerializer):
    # variant merujuk ke ProductVariantSerializer yg baru
    variant = ProductVariantSerializer(read_only=True)
    # variant_id merujuk ke ID ProductVariant
    variant_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariant.objects.all(), source='variant', write_only=True
    )

    class Meta:
        model = RequestItem
        fields = (
            'id', 'variant', 'variant_id', 'quantity_requested',
            'quantity_approved_spv2', 'quantity_issued'
        )
        # quantity_approved_spv2 dan quantity_issued tetap read_only di sini
        # karena diisi oleh action di view, bukan saat membuat item awal
        read_only_fields = ('quantity_approved_spv2', 'quantity_issued')


class TransactionSerializer(serializers.ModelSerializer):
    # variant merujuk ke ProductVariantSerializer yg baru
    variant = ProductVariantSerializer(read_only=True)
    user = BasicUserSerializer(read_only=True)
    inventory_item_info = serializers.CharField(source='inventory_item.__str__', read_only=True, allow_null=True)
    transaction_type_display = serializers.CharField(source='get_transaction_type_display', read_only=True)

    class Meta:
        model = Transaction
        fields = (
            'id', 'variant', 'inventory_item', 'inventory_item_info', 'quantity',
            'transaction_type', 'transaction_type_display', 'timestamp', 'user',
            'related_request', 'related_spmb', 'notes'
        )

class StockOpnameItemSerializer(serializers.ModelSerializer):
    # variant merujuk ke ProductVariantSerializer yg baru
    variant = ProductVariantSerializer(read_only=True)
    confirmed_by = BasicUserSerializer(read_only=True)
    confirmation_status_display = serializers.CharField(source='get_confirmation_status_display', read_only=True)

    class Meta:
        model = StockOpnameItem
        fields = (
            'id', 'opname_session', 'variant', 'system_quantity', 'counted_quantity',
            'difference', 'notes', 'confirmation_status','confirmation_status_display',
            'confirmed_by', 'confirmation_notes', 'confirmed_at'
        )
        read_only_fields = ('difference',)

class RequestListSerializer(serializers.ModelSerializer):
    """Serializer ringkas untuk daftar permintaan."""
    requester = BasicUserSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    # Coba ambil nomor SPMB jika ada, tangani jika spmb_document belum ada
    spmb_number = serializers.CharField(source='spmb_document.spmb_number', read_only=True, allow_null=True, default=None)

    class Meta:
        model = Request
        fields = (
            'id', 'request_number', 'requester', 'status', 'status_display',
            'created_at', 'submitted_at', 'supervisor1_decision_at',
            'supervisor2_decision_at', 'operator_processed_at', 'received_at',
            'spmb_number' # Tampilkan nomor SPMB jika ada
        )
        read_only_fields = fields # List view biasanya read-only

class RequestCreateSerializer(serializers.ModelSerializer):
    """Serializer untuk membuat permintaan baru oleh Peminta."""
    # Items diterima sebagai list of objects saat membuat
    # Kita perlu mendefinisikan ulang RequestItemSerializer ringkas untuk write di sini
    # atau pastikan RequestItemSerializer di atas menangani write_only=True untuk variant_id
    items = RequestItemSerializer(many=True) # Gunakan RequestItemSerializer yg sudah ada
    # Requester akan diisi otomatis di view

    class Meta:
        model = Request
        # Hanya field 'items' yang diterima dari input saat membuat request baru
        # ID akan dibuat otomatis, requester diambil dari view
        fields = ('id', 'items')
        read_only_fields = ('id',)

    def create(self, validated_data):
        # 'requester' sudah ada di dalam validated_data karena di-pass dari view.perform_create
        items_data = validated_data.pop('items')

        # Langsung create Request menggunakan validated_data (sudah termasuk requester)
        request_obj = Request.objects.create(**validated_data)

        # Buat item-item terkait
        for item_data in items_data:
            # Pastikan 'variant' ada di item_data (dari variant_id di RequestItemSerializer)
            RequestItem.objects.create(request=request_obj, **item_data)

        return request_obj

class RequestDetailSerializer(serializers.ModelSerializer):
    requester = BasicUserSerializer(read_only=True)
    supervisor1_approver = BasicUserSerializer(read_only=True)
    supervisor2_approver = BasicUserSerializer(read_only=True)
    operator_processor = BasicUserSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    items = RequestItemSerializer(many=True, read_only=True) # Ini sudah menggunakan RequestItemSerializer terbaru
    spmb_document = serializers.HyperlinkedRelatedField(
        view_name='spmb-detail', read_only=True, allow_null=True
    )
    # logs = RequestLogSerializer(many=True, read_only=True)

    class Meta:
        model = Request
        fields = (
            'id', 'request_number', 'requester', 'status', 'status_display', 'created_at',
            'submitted_at', 'supervisor1_approver', 'supervisor1_decision_at', 'supervisor1_rejection_reason',
            'supervisor2_approver', 'supervisor2_decision_at', 'supervisor2_rejection_reason',
            'operator_processor', 'operator_processed_at', 'operator_rejection_reason',
            'received_at', 'items', 'spmb_document', #'logs'
        )
        read_only_fields = fields

class SPMBSerializer(serializers.ModelSerializer):
    """Serializer untuk menampilkan detail SPMB."""
    # Tampilkan info ringkas request terkait menggunakan serializer yg sesuai
    request = RequestListSerializer(read_only=True)
    issued_by = BasicUserSerializer(read_only=True)

    class Meta:
        model = SPMB
        fields = ('id', 'spmb_number', 'request', 'issued_by', 'issued_at')
        read_only_fields = fields

class RequestLogSerializer(serializers.ModelSerializer):
    """Serializer untuk menampilkan log histori request."""
    user = BasicUserSerializer(read_only=True)
    status_from_display = serializers.CharField(source='get_status_from_display', read_only=True, allow_null=True)
    status_to_display = serializers.CharField(source='get_status_to_display', read_only=True, allow_null=True)

    class Meta:
        model = RequestLog
        fields = (
            'id', 'request', 'user', 'timestamp', 'action',
            'status_from', 'status_from_display', 'status_to', 'status_to_display',
            'comment'
        )
        # Log biasanya read-only via API
        read_only_fields = fields

class StockOpnameSessionSerializer(serializers.ModelSerializer):
    created_by = BasicUserSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    # Jika Anda ingin menampilkan item dalam detail sesi:
    # items = StockOpnameItemSerializer(many=True, read_only=True)

    class Meta:
        model = StockOpnameSession
        fields = (
            'id', 'opname_date', 'uploaded_file', 'created_by', 'created_at',
            'status', 'status_display', 'notes', #'items' # uncomment 'items' jika field di atas di-uncomment
        )
        # Tentukan read_only fields
        read_only_fields = ('created_at', 'created_by', 'status', 'status_display') # 'items' juga read_only jika ditambahkan

class StockOpnameFileUploadSerializer(serializers.Serializer):
    """Serializer untuk menerima file upload Excel stock opname."""
    file = serializers.FileField(required=True)
    opname_date = serializers.DateField(required=False, default=timezone.now().date())
    notes = serializers.CharField(required=False, allow_blank=True)

class StockOpnameConfirmSerializer(serializers.Serializer):
    """Serializer untuk Operator mengkonfirmasi item stock opname."""
    confirmation_status = serializers.ChoiceField(choices=StockOpnameItem.ConfirmationStatus.choices, required=True)
    confirmation_notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate_confirmation_status(self, value):
        if value == StockOpnameItem.ConfirmationStatus.PENDING:
             raise serializers.ValidationError(_("Tidak dapat mengkonfirmasi ke status PENDING."))
        return value

class ReceiptUploadSerializer(serializers.Serializer):
    """Serializer untuk menerima file upload kuitansi."""
    file = serializers.FileField(required=True, help_text="File Excel (.xlsx) atau CSV (.csv) berisi detail pembelian.")