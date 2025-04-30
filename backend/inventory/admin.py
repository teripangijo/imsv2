# backend/inventory/admin.py
from django.contrib import admin
from .models import (
    # Model hierarki kode baru
    ItemCodeGolongan, ItemCodeBidang, ItemCodeKelompok, ItemCodeSubKelompok, ItemCodeBarang,
    # Model utama yg dimodifikasi/digunakan
    ProductVariant, InventoryItem, Stock, Receipt,
    # Model lain (request, spmb, log, transaksi, opname)
    Request, RequestItem, SPMB, RequestLog, Transaction,
    StockOpnameSession, StockOpnameItem
)

# --- Kustomisasi Admin untuk Model yang Dimodifikasi ---

@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ('full_code', 'type_name', 'name', 'base_item_code', 'specific_code', 'unit_of_measure')
    search_fields = ('name', 'type_name', 'full_code', 'base_item_code__base_description', 'base_item_code__code')
    list_filter = ('base_item_code__sub_kelompok__kelompok__bidang__golongan', 'base_item_code__sub_kelompok__kelompok__bidang', 'base_item_code__sub_kelompok', 'type_name') # Filter berdasarkan hierarki
    # Fields yang ditampilkan di form tambah/ubah
    fields = ('base_item_code', 'type_name', 'name', 'description', 'unit_of_measure', 'full_code', 'specific_code')
    # Fields yang hanya bisa dibaca (di-generate otomatis)
    readonly_fields = ('full_code', 'specific_code')
    # Gunakan raw_id_fields jika daftar ItemCodeBarang sangat banyak
    raw_id_fields = ('base_item_code',)
    # Tambahkan ordering jika perlu
    ordering = ('base_item_code', 'specific_code')

@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'variant', 'quantity', 'purchase_price', 'entry_date', 'receipt', 'added_by')
    search_fields = ('variant__name', 'variant__full_code', 'receipt__receipt_number')
    list_filter = ('entry_date', 'variant__base_item_code__sub_kelompok', 'receipt')
    # Fields yang ditampilkan di form tambah/ubah
    fields = ('variant', 'receipt', 'quantity', 'purchase_price', 'entry_date', 'expiry_date', 'added_by')
    # Tentukan field read-only jika ada (misal added_by saat update)
    # readonly_fields = ('added_by',) # Contoh saat edit
    # Gunakan raw_id_fields untuk ForeignKey yg listnya bisa panjang
    raw_id_fields = ('variant', 'receipt', 'added_by')
    date_hierarchy = 'entry_date' # Memudahkan navigasi berdasarkan tanggal masuk
    ordering = ('-entry_date',)

@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
     list_display = ('variant', 'total_quantity', 'low_stock_threshold', 'last_updated', 'is_low_stock', 'is_out_of_stock')
     search_fields = ('variant__name', 'variant__full_code')
     readonly_fields = ('last_updated', 'total_quantity') # total_quantity dihitung otomatis, sebaiknya read-only di admin
     # Jika ingin mengedit threshold
     fields = ('variant', 'total_quantity', 'low_stock_threshold', 'last_updated')
     raw_id_fields = ('variant',)


# --- Pendaftaran Model Baru (Awalnya Default) ---
# Anda bisa menambahkan kustomisasi (list_display, dll.) nanti jika diperlukan

@admin.register(ItemCodeGolongan)
class ItemCodeGolonganAdmin(admin.ModelAdmin):
    list_display = ('code', 'description')
    search_fields = ('code', 'description')

@admin.register(ItemCodeBidang)
class ItemCodeBidangAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'description', 'golongan')
    search_fields = ('code', 'description', 'golongan__code')
    list_filter = ('golongan',)

@admin.register(ItemCodeKelompok)
class ItemCodeKelompokAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'description', 'bidang')
    search_fields = ('code', 'description', 'bidang__code', 'bidang__golongan__code')
    list_filter = ('bidang__golongan', 'bidang')
    raw_id_fields = ('bidang',) # Bidang bisa banyak

@admin.register(ItemCodeSubKelompok)
class ItemCodeSubKelompokAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'base_description', 'kelompok')
    search_fields = ('code', 'base_description', 'kelompok__code', 'kelompok__bidang__code', 'kelompok__bidang__golongan__code')
    list_filter = ('kelompok__bidang__golongan', 'kelompok__bidang', 'kelompok')
    raw_id_fields = ('kelompok',) # Kelompok bisa banyak

@admin.register(ItemCodeBarang)
class ItemCodeBarangAdmin(admin.ModelAdmin):
    list_display = ('get_full_base_code', 'base_description', 'sub_kelompok', 'account_code', 'account_description')
    search_fields = ('code', 'base_description', 'account_code', 'account_description', 'sub_kelompok__code', 'sub_kelompok__kelompok__code')
    list_filter = ('sub_kelompok__kelompok__bidang__golongan', 'sub_kelompok__kelompok__bidang', 'sub_kelompok__kelompok', 'sub_kelompok')
    readonly_fields = ('get_full_base_code',) # Method tidak bisa diedit
    raw_id_fields = ('sub_kelompok',) # SubKelompok bisa banyak
    # fieldsets/fields bisa ditambahkan untuk mengatur tampilan form
    fieldsets = (
         (None, {'fields': ('sub_kelompok', 'code', 'base_description')}),
         ('Info Akuntansi', {'fields': ('account_code', 'account_description')}),
    )

@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ('receipt_number', 'receipt_date', 'supplier_name', 'uploaded_by', 'uploaded_at')
    search_fields = ('receipt_number', 'supplier_name')
    list_filter = ('receipt_date', 'uploaded_by')
    readonly_fields = ('uploaded_at', 'uploaded_by') # Diisi otomatis

    def save_model(self, request, obj, form, change):
        # Set uploaded_by otomatis saat simpan dari admin jika belum ada
        if not obj.pk: # Hanya saat objek baru dibuat
            obj.uploaded_by = request.user
        super().save_model(request, obj, form, change)


# --- Pendaftaran Model Lain (Asumsi tidak berubah signifikan) ---
# Pastikan ini masih relevan atau sesuaikan jika perlu
admin.site.register(Request) # Mungkin perlu kustomisasi admin juga
admin.site.register(RequestItem)
admin.site.register(SPMB)
admin.site.register(RequestLog)
admin.site.register(Transaction)
admin.site.register(StockOpnameSession)
admin.site.register(StockOpnameItem)