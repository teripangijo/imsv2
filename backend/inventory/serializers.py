# backend/inventory/serializers.py
from rest_framework import serializers
from django.utils import timezone
from .models import (
    ProductCategory, ProductVariant, InventoryItem, Stock,
    Request, RequestItem, SPMB, RequestLog, Transaction,
    StockOpnameSession, StockOpnameItem
)
# Impor serializer user yang ringkas
from users.serializers import BasicUserSerializer, UserSerializer
from users.models import CustomUser
from django.utils.translation import gettext_lazy as _

# --- Serializer Produk & Stok ---

class ProductCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCategory
        fields = ('id', 'name', 'description')

class ProductVariantSerializer(serializers.ModelSerializer):
    # Tampilkan nama kategori, bukan hanya ID
    category_name = serializers.CharField(source='category.name', read_only=True)
    # Tampilkan URL ke kategori jika menggunakan HyperlinkedModelSerializer nanti
    # category = serializers.HyperlinkedRelatedField(view_name='productcategory-detail', read_only=True)

    class Meta:
        model = ProductVariant
        fields = ('id', 'category', 'category_name', 'name', 'description', 'unit_of_measure')
        # 'category' di sini adalah ID untuk write operations (membuat/update varian)

class StockSerializer(serializers.ModelSerializer):
    """Serializer untuk menampilkan level stok."""
    # Tampilkan detail varian, bukan hanya ID
    variant = ProductVariantSerializer(read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)
    is_out_of_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Stock
        fields = ('variant', 'total_quantity', 'low_stock_threshold', 'last_updated', 'is_low_stock', 'is_out_of_stock')


class InventoryItemSerializer(serializers.ModelSerializer):
    """Serializer untuk menampilkan detail batch inventaris (FIFO)."""
    variant = ProductVariantSerializer(read_only=True) # Tampilkan detail varian
    added_by = BasicUserSerializer(read_only=True) # Tampilkan info dasar user penambah

    class Meta:
        # ... (Meta sebelumnya) ...
        fields = ('id', 'variant', 'quantity', 'purchase_price', 'entry_date', 'expiry_date', 'added_by')
        read_only_fields = ('entry_date', 'added_by')

    def to_representation(self, instance):
        """Sesuaikan representasi data berdasarkan peran user."""
        ret = super().to_representation(instance)
        user = self.context['request'].user

        # Sembunyikan harga beli jika user bukan Operator, Atasan Operator, atau Admin
        if not (user.is_authenticated and (
                user.role == CustomUser.Role.OPERATOR or
                user.role == CustomUser.Role.ATASAN_OPERATOR or
                user.is_admin)):
            ret.pop('purchase_price', None) # Hapus field harga dari output

        return ret

class InventoryItemCreateSerializer(serializers.ModelSerializer):
    """Serializer khusus untuk Operator merekam barang masuk."""
    # Saat membuat, kita hanya perlu ID varian
    variant = serializers.PrimaryKeyRelatedField(queryset=ProductVariant.objects.all())
    # added_by akan diisi otomatis dari user yang login di view

    class Meta:
        model = InventoryItem
        # Hanya field yang relevan untuk input barang masuk
        fields = ('variant', 'quantity', 'purchase_price', 'expiry_date')


# --- Serializer Permintaan Barang ---

class RequestItemSerializer(serializers.ModelSerializer):
    """Serializer untuk item barang dalam sebuah permintaan."""
    variant = ProductVariantSerializer(read_only=True) # Tampilkan detail saat membaca
    variant_id = serializers.PrimaryKeyRelatedField( # Terima ID saat menulis (membuat request)
        queryset=ProductVariant.objects.all(), source='variant', write_only=True
    )

    class Meta:
        model = RequestItem
        fields = (
            'id', 'variant', 'variant_id', 'quantity_requested',
            'quantity_approved_spv2', 'quantity_issued'
        )
        read_only_fields = ('quantity_approved_spv2', 'quantity_issued') # Ini diisi oleh atasan/operator


class RequestListSerializer(serializers.ModelSerializer):
    """Serializer ringkas untuk daftar permintaan."""
    requester = BasicUserSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    spmb_number = serializers.CharField(source='spmb_document.spmb_number', read_only=True, allow_null=True)

    class Meta:
        model = Request
        fields = (
            'id', 'request_number', 'requester', 'status', 'status_display',
            'created_at', 'submitted_at', 'supervisor1_decision_at',
            'supervisor2_decision_at', 'operator_processed_at', 'received_at',
            'spmb_number' # Tampilkan nomor SPMB jika ada
        )
        read_only_fields = fields # List view biasanya read-only


class RequestDetailSerializer(serializers.ModelSerializer):
    """Serializer detail untuk satu permintaan."""
    requester = BasicUserSerializer(read_only=True)
    supervisor1_approver = BasicUserSerializer(read_only=True)
    supervisor2_approver = BasicUserSerializer(read_only=True)
    operator_processor = BasicUserSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    items = RequestItemSerializer(many=True, read_only=True) # Tampilkan item terkait
    spmb_document = serializers.HyperlinkedRelatedField( # Link ke detail SPMB jika ada
        view_name='spmb-detail', read_only=True, allow_null=True
    )
    # logs = RequestLogSerializer(many=True, read_only=True) # Tampilkan logs jika perlu

    class Meta:
        model = Request
        fields = (
            'id', 'request_number', 'requester', 'status', 'status_display', 'created_at',
            'submitted_at', 'supervisor1_approver', 'supervisor1_decision_at', 'supervisor1_rejection_reason',
            'supervisor2_approver', 'supervisor2_decision_at', 'supervisor2_rejection_reason',
            'operator_processor', 'operator_processed_at', 'operator_rejection_reason',
            'received_at', 'items', 'spmb_document', #'logs'
        )
        read_only_fields = fields # Detail view biasanya read-only


class RequestCreateSerializer(serializers.ModelSerializer):
    """Serializer untuk membuat permintaan baru oleh Peminta."""
    # Items diterima sebagai list of objects saat membuat
    items = RequestItemSerializer(many=True, write_only=True)
    # Requester akan diisi otomatis di view

    class Meta:
        model = Request
        fields = ('id', 'items') # Hanya perlu items saat membuat draft
        read_only_fields = ('id',)

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        # Ambil user dari context yang di-pass dari view
        requester = self.context['request'].user
        # Buat request (status default DRAFT)
        request = Request.objects.create(requester=requester, **validated_data)
        # Buat item-item terkait
        for item_data in items_data:
            RequestItem.objects.create(request=request, **item_data)
        return request

# --- Serializer SPMB ---
class SPMBSerializer(serializers.ModelSerializer):
    request = RequestListSerializer(read_only=True) # Tampilkan info ringkas request
    issued_by = BasicUserSerializer(read_only=True)

    class Meta:
        model = SPMB
        fields = ('id', 'spmb_number', 'request', 'issued_by', 'issued_at')
        read_only_fields = fields


# --- Serializer Log & Transaksi ---
class RequestLogSerializer(serializers.ModelSerializer):
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

class TransactionSerializer(serializers.ModelSerializer):
    variant = ProductVariantSerializer(read_only=True)
    user = BasicUserSerializer(read_only=True)
    inventory_item_info = serializers.CharField(source='inventory_item.__str__', read_only=True, allow_null=True) # Info batch jika ada
    transaction_type_display = serializers.CharField(source='get_transaction_type_display', read_only=True)

    class Meta:
        model = Transaction
        fields = (
            'id', 'variant', 'inventory_item', 'inventory_item_info', 'quantity',
            'transaction_type', 'transaction_type_display', 'timestamp', 'user',
            'related_request', 'related_spmb', 'notes'
        )


# --- Serializer Stock Opname ---
class StockOpnameItemSerializer(serializers.ModelSerializer):
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
        read_only_fields = ('difference',) # Dihitung otomatis

class StockOpnameSessionSerializer(serializers.ModelSerializer):
    created_by = BasicUserSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    # items = StockOpnameItemSerializer(many=True, read_only=True) # Tampilkan item di detail

    class Meta:
        model = StockOpnameSession
        fields = (
            'id', 'opname_date', 'uploaded_file', 'created_by', 'created_at',
            'status', 'status_display', 'notes', #'items'
        )
        read_only_fields = ('created_at', 'created_by', 'status', 'status_display')


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
        # Contoh validasi tambahan jika diperlukan
        if value == StockOpnameItem.ConfirmationStatus.PENDING:
             raise serializers.ValidationError(_("Tidak dapat mengkonfirmasi ke status PENDING."))
        return value