# backend/inventory/serializers.py
from rest_framework import serializers
from django.utils import timezone
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
# --- Serializer untuk Hierarki Kode (Baru) ---
# (Ini sederhana, bisa dikembangkan nanti jika perlu fitur lebih)

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
        read_only_fields = fields # SPMB biasanya hanya dibuat oleh sistem (read-only via API umum)

class RequestLogSerializer(serializers.ModelSerializer):
    """Serializer untuk menampilkan log histori request."""
    user = BasicUserSerializer(read_only=True) # Tampilkan info user yg melakukan aksi
    # Dapatkan display name untuk status (jika diperlukan)
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