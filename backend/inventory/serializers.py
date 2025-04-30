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


# Serializer lain seperti RequestList, RequestDetail, SPMB, RequestLog,
# StockOpnameSession, StockOpnameFileUpload, StockOpnameConfirm
# umumnya tidak perlu diubah karena relasinya ke Request atau User,
# TAPI jika mereka menampilkan detail item (seperti RequestDetailSerializer),
# pastikan mereka menggunakan RequestItemSerializer yang sudah diupdate.

# Contoh penyesuaian RequestDetailSerializer jika menampilkan item
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

class ReceiptUploadSerializer(serializers.Serializer):
    """Serializer untuk menerima file upload kuitansi."""
    file = serializers.FileField(required=True, help_text="File Excel (.xlsx) atau CSV (.csv) berisi detail pembelian.")