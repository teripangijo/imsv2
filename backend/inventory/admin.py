# backend/inventory/admin.py
from django.contrib import admin
from .models import (
    ProductVariant, InventoryItem, Stock,
    Request, RequestItem, SPMB, RequestLog, Transaction,
    StockOpnameSession, StockOpnameItem
)

# Daftarkan semua model agar muncul di admin interface
# Anda bisa membuat kelas admin kustom untuk tampilan yang lebih baik nanti
admin.site.register(ProductVariant)
admin.site.register(InventoryItem)
admin.site.register(Stock)
admin.site.register(Request)
admin.site.register(RequestItem)
admin.site.register(SPMB)
admin.site.register(RequestLog)
admin.site.register(Transaction)
admin.site.register(StockOpnameSession)
admin.site.register(StockOpnameItem)