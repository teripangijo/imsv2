# backend/inventory/views.py
from rest_framework import viewsets, status, permissions, generics, pagination
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import serializers
from rest_framework import filters
from rest_framework.views import APIView
from django.db.models import F, Prefetch, Sum, Q, Value, Subquery, OuterRef
from django.db.models.functions import Coalesce, Abs
from django.utils.dateparse import parse_date
from django.http import HttpResponse
import csv
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from django.db import transaction, IntegrityError
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend, FilterSet, DateFromToRangeFilter, ModelChoiceFilter, ChoiceFilter, CharFilter
# from django.shortcuts import get_object_or_404 # Mungkin tidak terpakai
import pandas as pd
import openpyxl
import traceback # Untuk debugging jika perlu

# Impor model dengan benar
from .models import (
    ProductVariant, InventoryItem, Stock,
    Request, RequestItem, SPMB, RequestLog, Transaction, ProductVariant,
    StockOpnameSession, StockOpnameItem,
    ItemCodeGolongan, ItemCodeBidang, ItemCodeKelompok, ItemCodeSubKelompok, ItemCodeBarang,
    Receipt # Pastikan Receipt hanya diimpor sekali
)
# Impor serializer dengan benar
from .serializers import (
    ProductVariantSerializer, InventoryItemSerializer,
    InventoryItemCreateSerializer, StockSerializer, RequestListSerializer,
    RequestDetailSerializer, RequestCreateSerializer, SPMBSerializer,
    RequestLogSerializer, TransactionSerializer, StockOpnameSessionSerializer,
    StockOpnameItemSerializer, StockOpnameFileUploadSerializer,
    StockOpnameConfirmSerializer, StockValueFIFOReportSerializer,
    ReceiptUploadSerializer, ReceiptSerializer,
    ItemCodeBarangSerializer,
    CurrentStockReportSerializer, MovingItemsReportSerializer, ConsumptionReportSerializer,
)
# Impor permission kustom
from .permissions import (
    IsAdminUser, IsOperatorOrReadOnly, IsOperator, IsPeminta,
    IsAtasanPeminta, IsAtasanOperator, CanApproveRequestSpv1,
    CanApproveRequestSpv2, CanProcessRequestOperator, IsOwnerOfRequest
)

# --- FilterSet Kustom untuk Laporan Konsumsi ---

class ConsumptionFilter(FilterSet):
    timestamp_range = DateFromToRangeFilter(field_name='timestamp')
    department_code = CharFilter(field_name='related_request__requester__department_code', lookup_expr='iexact')
    # Tambahkan filter lain jika perlu, misal variant
    # variant = ModelChoiceFilter(queryset=ProductVariant.objects.all(), field_name='variant')

    class Meta:
        model = Transaction
        fields = ['timestamp_range', 'department_code', 'variant'] # Tambahkan 'variant' jika filter di atas diaktifkan

# --- ViewSet Baru untuk Laporan Konsumsi (dengan Ekspor CSV) ---

class ConsumptionReportViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint untuk menampilkan laporan konsumsi barang per unit peminta
    dalam periode tanggal tertentu. Termasuk ekspor CSV.
    Membutuhkan query parameter 'timestamp_range_after' dan 'timestamp_range_before' (YYYY-MM-DD).
    Opsional: 'department_code', 'variant'.
    """
    serializer_class = ConsumptionReportSerializer
    permission_classes = [IsOperator | IsAtasanOperator | IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = ConsumptionFilter

    ordering_fields = [
        'department_code',
        'variant_full_code',
        'variant_type_name',
        'variant_name',
        'total_quantity_consumed',
    ]
    ordering = ['department_code', 'variant_full_code']

    def get_queryset(self):
        """
        Mengambil data transaksi keluar, mengagregasi per departemen & varian,
        dan menganotasi dengan detail yang diperlukan serializer.
        """
        queryset = Transaction.objects.filter(
            transaction_type=Transaction.Type.OUT,
            related_request__isnull=False,
            related_request__requester__isnull=False
        ).select_related(
            'variant__base_item_code',
            'related_request__requester'
        )

        # Filter diterapkan oleh DjangoFilterBackend menggunakan filterset_class

        report_data = queryset.values(
            'related_request__requester__department_code', # Grouping
            'variant__id',                                  # Grouping
        ).annotate(
            total_quantity_consumed=Coalesce(Sum(Abs('quantity')), 0),
            # Ambil data lain menggunakan F expression
            department_code=F('related_request__requester__department_code'),
            # Ambil data requester jika ingin ditampilkan per user, bukan hanya dept
            # requester_id=F('related_request__requester__id'),
            # requester_email=F('related_request__requester__email'),
            variant_id=F('variant__id'),
            variant_full_code=F('variant__full_code'),
            variant_type_name=F('variant__type_name'),
            variant_name=F('variant__name'),
            variant_unit=F('variant__unit_of_measure'),
            base_item_description=F('variant__base_item_code__base_description')
        ).filter(
            total_quantity_consumed__gt=0 # Hanya tampilkan yang ada konsumsi
        )
        # Ordering akan diterapkan oleh OrderingFilter

        return report_data

    # --- ACTION BARU UNTUK EKSPOR CSV ---
    @action(detail=False, methods=['get'], url_path='export-csv')
    def export_consumption_csv(self, request):
        """
        Ekspor data laporan konsumsi per unit/varian ke format CSV.
        Menerima query parameter filter yang sama dengan list view.
        """
        # Terapkan filter yang sama seperti list view
        queryset = self.filter_queryset(self.get_queryset())
        # Terapkan ordering yang diminta (atau default)
        # OrderingFilter biasanya menangani ini, tapi kita bisa terapkan manual jika perlu
        ordering = self.request.query_params.get('ordering', self.ordering[0] if self.ordering else None)
        if ordering and ordering in self.ordering_fields:
             # Perlu mapping nama field ordering ke field anotasi/values
             # Contoh sederhana:
             db_ordering_field = ordering
             # Ganti nama jika ordering field berbeda dari nama anotasi/values
             if ordering == 'variant_name': db_ordering_field = 'variant__name' # Sesuaikan
             # ... mapping lain ...
             queryset = queryset.order_by(db_ordering_field)
        elif self.ordering:
             # Terapkan default ordering jika ada
             queryset = queryset.order_by(*self.ordering)


        # Siapkan HttpResponse dengan header CSV
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="laporan_konsumsi_{date.today().strftime("%Y%m%d")}.csv"'

        writer = csv.writer(response, delimiter=';')

        # Tulis header kolom (sesuaikan dengan field di ConsumptionReportSerializer)
        header = [
            'Kode Departemen',
            # 'ID Peminta', # Jika dikelompokkan per peminta
            # 'Email Peminta', # Jika dikelompokkan per peminta
            'Kode Varian',
            'Jenis Barang',
            'Nama Spesifik',
            'Deskripsi Dasar',
            'Satuan',
            'Total Kuantitas Konsumsi',
        ]
        writer.writerow(header)

        # Tulis data per baris
        # Karena queryset sudah berisi dictionary hasil values().annotate(),
        # kita bisa langsung akses key-nya
        for row in queryset:
            writer.writerow([
                row.get('department_code', ''),
                # row.get('requester_id', ''), # Jika ada
                # row.get('requester_email', ''), # Jika ada
                row.get('variant_full_code', ''),
                row.get('variant_type_name', ''),
                row.get('variant_name', ''),
                row.get('base_item_description', ''),
                row.get('variant_unit', ''),
                row.get('total_quantity_consumed', 0),
            ])

        return response
    # --- AKHIR ACTION EKSPOR CSV ---

# --- FilterSet Kustom untuk Transaksi ---

class TransactionFilter(FilterSet):
    timestamp_range = DateFromToRangeFilter(field_name='timestamp')
    transaction_type = ChoiceFilter(choices=Transaction.Type.choices)
    variant = ModelChoiceFilter(queryset=ProductVariant.objects.all())
    # user = ModelChoiceFilter(queryset=get_user_model().objects.all()) # Uncomment jika filter user diaktifkan
    # receipt = ModelChoiceFilter(queryset=Receipt.objects.all()) # Uncomment jika filter receipt diaktifkan

    class Meta:
        model = Transaction
        fields = ['timestamp_range', 'transaction_type', 'variant'] # Tambahkan 'user', 'receipt' jika perlu

# --- ViewSet untuk Laporan Histori Transaksi (dengan Ekspor CSV) ---

class TransactionReportViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint untuk menampilkan laporan histori transaksi (keluar/masuk/penyesuaian).
    Read-only, dengan filter tanggal, tipe, varian, search, ordering, dan ekspor CSV.
    """
    serializer_class = TransactionSerializer
    permission_classes = [IsOperator | IsAtasanOperator | IsAdminUser] # Sesuaikan permission jika perlu
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = TransactionFilter # Gunakan FilterSet kustom

    search_fields = [
        'variant__full_code',
        'variant__type_name',
        'variant__name',
        'user__email',
        'user__first_name',
        'user__last_name',
        'receipt__receipt_number',
        'related_request__request_number',
        'related_spmb__spmb_number',
        'notes',
    ]
    ordering_fields = [
        'timestamp',
        'variant__full_code',
        'transaction_type',
        'quantity',
        'user__email',
    ]
    ordering = ['-timestamp'] # Default: transaksi terbaru dulu

    def get_queryset(self):
        """
        Mengambil queryset dasar untuk laporan transaksi.
        """
        queryset = Transaction.objects.select_related(
            'variant__base_item_code',
            'user',
            'inventory_item',
            'related_request',
            'related_spmb',
            'receipt'
        ).all()
        return queryset

    # --- ACTION UNTUK EKSPOR CSV ---
    @action(detail=False, methods=['get'], url_path='export-csv')
    def export_transactions_csv(self, request):
        """
        Ekspor data laporan transaksi ke format CSV.
        Menerima query parameter filter yang sama dengan list view.
        """
        # Terapkan filter yang sama seperti list view
        queryset = self.filter_queryset(self.get_queryset())
        # Terapkan ordering jika ada
        ordering = self.request.query_params.get('ordering')
        if ordering and ordering.lstrip('-') in self.ordering_fields:
             queryset = queryset.order_by(ordering)
        elif self.ordering:
             queryset = queryset.order_by(*self.ordering)


        # Siapkan HttpResponse dengan header CSV
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="laporan_transaksi_{date.today().strftime("%Y%m%d")}.csv"'

        writer = csv.writer(response, delimiter=';')

        # Tulis header kolom (sesuaikan dengan field di TransactionSerializer)
        header = [
            'ID Transaksi',
            'Waktu Transaksi',
            'Kode Varian',
            'Jenis Barang',
            'Nama Spesifik',
            'Satuan',
            'Jumlah',
            'Tipe Transaksi',
            'User Email',
            'User Nama',
            'ID Batch Terkait',
            'ID Request Terkait',
            'No Request',
            'ID SPMB Terkait',
            'No SPMB',
            'ID Kuitansi Terkait',
            'No Kuitansi',
            'Catatan',
        ]
        writer.writerow(header)

        # Tulis data per baris
        for tx in queryset:
            variant = tx.variant
            user = tx.user
            req = tx.related_request
            spmb = tx.related_spmb
            receipt = tx.receipt

            writer.writerow([
                tx.id,
                tx.timestamp.strftime('%Y-%m-%d %H:%M:%S') if tx.timestamp else '',
                getattr(variant, 'full_code', ''),
                getattr(variant, 'type_name', ''),
                getattr(variant, 'name', ''),
                getattr(variant, 'unit_of_measure', ''),
                tx.quantity,
                tx.get_transaction_type_display(), # Tampilkan display name
                getattr(user, 'email', ''),
                getattr(user, 'get_full_name', lambda: '')(), # Panggil get_full_name jika ada
                getattr(tx.inventory_item, 'id', ''),
                getattr(req, 'id', ''),
                getattr(req, 'request_number', ''),
                getattr(spmb, 'id', ''),
                getattr(spmb, 'spmb_number', ''),
                getattr(receipt, 'id', ''),
                getattr(receipt, 'receipt_number', ''),
                tx.notes,
            ])

        return response
    # --- AKHIR ACTION EKSPOR CSV ---

# --- ViewSet Baru untuk Laporan Slow/Fast Moving ---

class MovingItemsReportViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint untuk menampilkan laporan barang slow/fast moving
    berdasarkan jumlah keluar dalam periode tanggal tertentu.
    Membutuhkan query parameter 'start_date' dan 'end_date' (YYYY-MM-DD).
    """
    serializer_class = MovingItemsReportSerializer
    permission_classes = [IsOperator | IsAtasanOperator | IsAdminUser]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['total_quantity_issued', 'variant_name', 'full_code']
    ordering = ['-total_quantity_issued'] # Default: fast-moving

    def get_queryset(self):
        """
        Menganotasi ProductVariant dengan total kuantitas keluar
        berdasarkan filter tanggal dari query parameters.
        """
        # Ambil dan Validasi Parameter Tanggal
        start_date_str = self.request.query_params.get('start_date', None)
        end_date_str = self.request.query_params.get('end_date', None)

        if not end_date_str: end_date = date.today()
        else: end_date = parse_date(end_date_str) or date.today()

        if not start_date_str: start_date = end_date - timedelta(days=30)
        else: start_date = parse_date(start_date_str) or (end_date - timedelta(days=30))

        if start_date > end_date: start_date = end_date - timedelta(days=30)

        print(f"DEBUG: MovingItemsReport - Periode: {start_date} s/d {end_date}")

        # Query Utama
        # 1. Dapatkan ID varian yang relevan (sama seperti sebelumnya)
        transactions_in_period = Transaction.objects.filter(
            transaction_type=Transaction.Type.OUT,
            timestamp__date__gte=start_date,
            timestamp__date__lte=end_date
        )
        variant_issued_quantities = transactions_in_period.values('variant').annotate(
            total_issued=Coalesce(Sum(Abs('quantity')), 0)
        ).filter(total_issued__gt=0)
        variant_ids = [item['variant'] for item in variant_issued_quantities]

        # 2. Ambil objek ProductVariant
        queryset = ProductVariant.objects.filter(
            pk__in=variant_ids
        ).select_related('base_item_code')

        # 3. Tambahkan anotasi total_quantity_issued
        # --- PERBAIKAN: Gunakan Q object untuk filter ---
        annotated_queryset = queryset.annotate(
             total_quantity_issued=Coalesce(Sum(
                 Abs('transaction__quantity'),
                 filter=Q(transaction__transaction_type=Transaction.Type.OUT) &
                        Q(transaction__timestamp__date__gte=start_date) &
                        Q(transaction__timestamp__date__lte=end_date)
             ), 0)
        )
        # --- AKHIR PERBAIKAN ---

        return annotated_queryset

    # Override list lagi jika perlu memasukkan nilai dari issued_map secara manual
    # (Mirip dengan StockValueFIFOReportViewSet, tapi mungkin tidak perlu jika anotasi cukup akurat)
    # def list(self, request, *args, **kwargs):
    #     queryset = self.filter_queryset(self.get_queryset())
    #     page = self.paginate_queryset(queryset)
    #     data_to_serialize = page if page is not None else queryset
    #
    #     # Dapatkan mapping ID varian ke jumlah keluar (seperti di get_queryset)
    #     start_date, end_date = self._get_date_range(request) # Buat helper method jika perlu
    #     transactions_in_period = Transaction.objects.filter(...)
    #     variant_issued_quantities = transactions_in_period.values(...).annotate(...)
    #     issued_map = {item['variant']: item['total_issued'] for item in variant_issued_quantities}
    #
    #     serializer = self.get_serializer(data_to_serialize, many=True)
    #     final_data = serializer.data
    #
    #     # Masukkan nilai dari issued_map
    #     for item_data in final_data:
    #         variant_id = item_data.get('id') # Asumsi serializer punya 'id'
    #         item_data['total_quantity_issued'] = issued_map.get(variant_id, 0)
    #
    #     if page is not None:
    #          return self.get_paginated_response(final_data)
    #     return Response(final_data)
    #
    # def _get_date_range(self, request):
    #      # Helper untuk mengambil dan memvalidasi tanggal
    #      # ... (logika ambil start_date, end_date dari query_params) ...
    #      return start_date, end_date

# ---View Set Laporan Stok Minimum ---
class LowStockAlertViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint untuk menampilkan daftar barang yang stoknya
    sama dengan atau di bawah batas minimum (low stock alert).
    Read-only.
    """
    serializer_class = CurrentStockReportSerializer # Gunakan serializer laporan stok yang ada
    permission_classes = [IsOperator | IsAtasanOperator | IsAdminUser]
    # Filter backend bisa ditambahkan jika ingin filter/search/order lebih lanjut di hasil alert
    # filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    # filterset_fields = { ... }
    # search_fields = [ ... ]
    # ordering_fields = [ ... ]
    ordering = ['variant__full_code'] # Default ordering

    def get_queryset(self):
        """
        Mengambil queryset Stock dan memfilternya untuk stok minimum.
        """
        # Ambil data Stock dan relasinya
        queryset = Stock.objects.select_related(
            'variant__base_item_code'
        ).filter(
            # Filter utama: total kuantitas <= ambang batas DAN ambang batas tidak null
            low_stock_threshold__isnull=False, # Pastikan threshold ada
            total_quantity__lte=F('low_stock_threshold') # Bandingkan field dengan field
        ).order_by('variant__full_code') # Urutkan

        # Anda bisa tambahkan filter lain di sini jika perlu
        # Misalnya, hanya tampilkan yang stoknya > 0 tapi di bawah threshold
        # queryset = queryset.filter(total_quantity__gt=0)

        return queryset

# --- ViewSet Laporan Nilai Stok FIFO ---

class StockValueFIFOReportViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint untuk menampilkan laporan nilai stok menggunakan metode FIFO.
    Read-only. Nilai FIFO dihitung saat request. Termasuk ekspor CSV.
    """
    serializer_class = StockValueFIFOReportSerializer
    permission_classes = [IsOperator | IsAtasanOperator | IsAdminUser]
    # filter_backends = [...] 
    # filterset_fields = { ... }
    # search_fields = [ ... ]
    # ordering_fields = [ ... ]
    ordering = ['variant__full_code'] # Default ordering

    def get_queryset(self):
        """
        Mengambil queryset Stock dan prefetch batch InventoryItem yang relevan.
        """
        inventory_items_prefetch = Prefetch(
            'variant__inventory_items',
            queryset=InventoryItem.objects.filter(quantity__gt=0).order_by('entry_date', 'id'),
            to_attr='fifo_batches'
        )
        queryset = Stock.objects.filter(total_quantity__gt=0).select_related(
            'variant__base_item_code'
        ).prefetch_related(
            inventory_items_prefetch
        ).order_by('variant__full_code')
        return queryset

    def _calculate_fifo_value(self, stock_item):
        """Helper method untuk menghitung nilai FIFO."""
        total_quantity_on_hand = stock_item.total_quantity
        fifo_total_value = Decimal('0.00')
        quantity_to_value = total_quantity_on_hand
        batches = getattr(stock_item.variant, 'fifo_batches', [])

        for batch in batches:
            if quantity_to_value <= 0: break
            try:
                purchase_price = batch.purchase_price or Decimal('0.00')
                if not isinstance(purchase_price, Decimal): purchase_price = Decimal(purchase_price)
            except (TypeError, ValueError, InvalidOperation) as e_price:
                 purchase_price = Decimal('0.00')
                 print(f"Warning (FIFO Calc): Invalid purchase price '{batch.purchase_price}' for batch ID {batch.id}. Using 0.")

            qty_from_this_batch = min(Decimal(quantity_to_value), Decimal(batch.quantity))
            fifo_total_value += (qty_from_this_batch * purchase_price)
            quantity_to_value -= qty_from_this_batch

        if quantity_to_value > 0:
             print(f"Warning (FIFO Calc): Could not value remaining {quantity_to_value} units for variant {getattr(stock_item.variant, 'name', 'N/A')}.")

        return fifo_total_value

    def list(self, request, *args, **kwargs):
        """
        Override method list untuk menghitung nilai FIFO per item.
        """
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        data_to_serialize = page if page is not None else queryset

        results_with_fifo_value = []
        for stock_item in data_to_serialize:
            # Hitung nilai FIFO menggunakan helper method
            stock_item.calculated_fifo_value = self._calculate_fifo_value(stock_item)
            results_with_fifo_value.append(stock_item)

        serializer = self.get_serializer(results_with_fifo_value, many=True)
        final_data = serializer.data

        # Masukkan nilai FIFO ke hasil serialisasi
        for i, item_data in enumerate(final_data):
             if i < len(results_with_fifo_value):
                 item_data['fifo_total_value'] = results_with_fifo_value[i].calculated_fifo_value

        if page is not None:
             return self.get_paginated_response(final_data)
        return Response(final_data)

    # --- ACTION BARU UNTUK EKSPOR CSV ---
    @action(detail=False, methods=['get'], url_path='export-csv')
    def export_fifo_value_csv(self, request):
        """
        Ekspor data laporan nilai stok FIFO ke format CSV.
        Menerima query parameter filter yang sama dengan list view.
        """
        # Terapkan filter yang sama seperti list view
        queryset = self.filter_queryset(self.get_queryset())

        # Siapkan HttpResponse dengan header CSV
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="laporan_nilai_stok_fifo_{date.today().strftime("%Y%m%d")}.csv"'

        # Buat CSV writer
        writer = csv.writer(response, delimiter=';')

        # Tulis header kolom (sesuaikan dengan field di StockValueFIFOReportSerializer)
        header = [
            'Kode Lengkap Varian',
            'Jenis Barang',
            'Nama Spesifik (Merk/Tipe)',
            'Deskripsi Dasar',
            'Satuan',
            'Jumlah Stok Saat Ini',
            'Total Nilai (FIFO)',
        ]
        writer.writerow(header)

        # Tulis data per baris, hitung FIFO untuk setiap item
        for stock_item in queryset:
            # Hitung nilai FIFO untuk item ini
            fifo_value = self._calculate_fifo_value(stock_item)

            # Ambil data terkait dengan aman
            variant = stock_item.variant
            base_item = getattr(variant, 'base_item_code', None)

            writer.writerow([
                getattr(variant, 'full_code', ''),
                getattr(variant, 'type_name', ''),
                getattr(variant, 'name', ''),
                getattr(base_item, 'base_description', '') if base_item else '',
                getattr(variant, 'unit_of_measure', ''),
                stock_item.total_quantity,
                fifo_value, # Masukkan nilai FIFO yang sudah dihitung
            ])

        return response
    # --- AKHIR ACTION EKSPOR CSV ---

# --- ViewSet Laporan Stok Terkini ---

class CurrentStockReportViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint untuk menampilkan laporan stok terkini.
    Read-only, dengan kemampuan filter, pencarian, dan ekspor CSV.
    """
    serializer_class = CurrentStockReportSerializer
    permission_classes = [IsOperator | IsAtasanOperator | IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = {
        'variant__type_name': ['exact', 'icontains'],
        'variant__base_item_code__sub_kelompok__kelompok__bidang__golongan__code': ['exact'],
        'variant__base_item_code__sub_kelompok__kelompok__bidang__code': ['exact'],
        'variant__base_item_code__sub_kelompok__kelompok__code': ['exact'],
        'variant__base_item_code__sub_kelompok__code': ['exact'],
        'variant__base_item_code__account_code': ['exact'],
        # 'total_quantity': ['lte', 'gte'], # Bisa ditambahkan jika perlu
    }
    search_fields = [
        'variant__full_code',
        'variant__type_name',
        'variant__name',
        'variant__base_item_code__base_description',
        'variant__base_item_code__account_code',
    ]
    ordering_fields = [
        'variant__full_code',
        'variant__type_name',
        'variant__name',
        'total_quantity',
        'last_updated',
    ]
    ordering = ['variant__full_code']

    def get_queryset(self):
        """
        Mengambil queryset dasar untuk laporan stok.
        """
        queryset = Stock.objects.select_related(
            'variant__base_item_code' # Ambil data dasar varian
        ).all() # Ambil semua stok, filter low/out of stock bisa di query param

        # Implementasi filter tambahan jika diperlukan
        query_params = self.request.query_params
        if query_params.get('low_stock_only') == 'true':
             queryset = queryset.filter(
                 low_stock_threshold__isnull=False,
                 total_quantity__lte=F('low_stock_threshold')
             )
        elif query_params.get('out_of_stock_only') == 'true':
             queryset = queryset.filter(total_quantity__lte=0)

        return queryset

    # --- ACTION BARU UNTUK EKSPOR CSV ---
    @action(detail=False, methods=['get'], url_path='export-csv')
    def export_stock_csv(self, request):
        """
        Ekspor data laporan stok terkini ke format CSV.
        Menerima query parameter filter yang sama dengan list view.
        """
        # Terapkan filter yang sama seperti list view
        queryset = self.filter_queryset(self.get_queryset())

        # Siapkan HttpResponse dengan header CSV
        response = HttpResponse(content_type='text/csv')
        # Beri nama file download
        response['Content-Disposition'] = f'attachment; filename="laporan_stok_terkini_{date.today().strftime("%Y%m%d")}.csv"'

        # Buat CSV writer
        writer = csv.writer(response, delimiter=';') # Gunakan titik koma jika preferensi lokal

        # Tulis header kolom (sesuaikan dengan field di CurrentStockReportSerializer)
        header = [
            'Kode Lengkap Varian',
            'Jenis Barang',
            'Nama Spesifik (Merk/Tipe)',
            'Deskripsi Dasar',
            'Satuan',
            'Jumlah Stok Saat Ini',
            # 'Batas Stok Rendah',
            'Terakhir Update',
            # 'Status Stok Rendah',
            # 'Status Stok Habis',
            # 'Kode Akun',
        ]
        writer.writerow(header)

        # Tulis data per baris
        for stock_item in queryset:
            # Ambil data terkait dengan aman
            variant = stock_item.variant
            base_item = getattr(variant, 'base_item_code', None)

            writer.writerow([
                getattr(variant, 'full_code', ''),
                getattr(variant, 'type_name', ''),
                getattr(variant, 'name', ''),
                getattr(base_item, 'base_description', '') if base_item else '',
                getattr(variant, 'unit_of_measure', ''),
                stock_item.total_quantity,
                # stock_item.low_stock_threshold,
                stock_item.last_updated.strftime('%Y-%m-%d %H:%M:%S') if stock_item.last_updated else '',
                # stock_item.is_low_stock,
                # stock_item.is_out_of_stock,
                # getattr(base_item , 'account_code', '') if base_item else '',
            ])

        return response
    # --- AKHIR ACTION EKSPOR CSV ---

# --- Views Produk & Stok ---

class ProductVariantViewSet(viewsets.ModelViewSet):
    """API endpoint untuk mengelola Varian Produk Spesifik."""
    # Gunakan select_related untuk mengambil data terkait
    queryset = ProductVariant.objects.select_related(
        'base_item_code__sub_kelompok__kelompok__bidang__golongan'
    ).all()
    serializer_class = ProductVariantSerializer
    permission_classes = [IsAdminUser | IsOperatorOrReadOnly]

class StockViewSet(viewsets.ReadOnlyModelViewSet):
    """Menampilkan daftar stok barang."""
    # Sesuaikan select_related dan ordering
    queryset = Stock.objects.select_related(
        'variant__base_item_code' # Ambil kode barang dasar terkait varian
        ).order_by('variant__full_code') # Urutkan berdasarkan kode lengkap varian
    serializer_class = StockSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        return queryset

class InventoryItemViewSet(viewsets.ModelViewSet):
    """Endpoint untuk mengelola batch inventaris (FIFO)."""
    # Sesuaikan select_related
    queryset = InventoryItem.objects.select_related(
        'variant__base_item_code', # Ambil data varian dan kode dasarnya
        'added_by',                # Ambil data user penambah
        'receipt'                  # Ambil data kuitansi terkait
        ).all()
    permission_classes = [IsOperator] # Hanya Operator/Admin

    def get_serializer_class(self):
        # Gunakan InventoryItemCreateSerializer saat membuat item baru
        if self.action == 'create':
            return InventoryItemCreateSerializer
        # Untuk upload_receipt, serializer input didefinisikan di @action
        # Untuk list, retrieve, update, destroy, gunakan serializer standar
        return InventoryItemSerializer

    def perform_create(self, serializer):
        # Set added_by otomatis saat input manual via API
        inventory_item = serializer.save(added_by=self.request.user)
        # Update Stock Level dan buat Transaction log
        try:
            with transaction.atomic():
                stock, created = Stock.objects.select_for_update().get_or_create(variant=inventory_item.variant)
                stock.total_quantity += inventory_item.quantity
                stock.save()
                Transaction.objects.create(
                    variant=inventory_item.variant,
                    inventory_item=inventory_item,
                    quantity=inventory_item.quantity,
                    transaction_type=Transaction.Type.IN,
                    user=self.request.user,
                    receipt=inventory_item.receipt, # Catat receipt jika ada
                    notes=f"Penerimaan barang baru batch #{inventory_item.id} (Manual/API Create)"
                )
        except Exception as e:
             print(f"Error updating stock for InventoryItem {inventory_item.id}: {e}")
             # Pertimbangkan mekanisme notifikasi atau logging error yang lebih baik

    def perform_update(self, serializer):
        # Logika update batch inventaris (penyesuaian)
        original_item = self.get_object()
        original_quantity = original_item.quantity
        updated_item = serializer.save()
        quantity_diff = updated_item.quantity - original_quantity
        if quantity_diff != 0:
            try:
                with transaction.atomic():
                    stock = Stock.objects.select_for_update().get(variant=updated_item.variant)
                    stock.total_quantity += quantity_diff
                    stock.save()
                    Transaction.objects.create(
                        variant=updated_item.variant,
                        inventory_item=updated_item,
                        quantity=quantity_diff,
                        transaction_type=Transaction.Type.ADJUSTMENT,
                        user=self.request.user,
                        receipt=updated_item.receipt,
                        notes=f"Penyesuaian manual batch #{updated_item.id}"
                    )
            except Stock.DoesNotExist:
                 print(f"Error: Stock level not found for variant {updated_item.variant.id} during InventoryItem update.")
            except Exception as e:
                 print(f"Error updating stock during InventoryItem update {updated_item.id}: {e}")

    def perform_destroy(self, instance):
        # Logika saat menghapus batch inventaris
        variant = instance.variant
        receipt_ref = instance.receipt
        instance_id = instance.id
        quantity_to_deduct = instance.quantity
        try:
            with transaction.atomic():
                instance.delete()
                stock = Stock.objects.select_for_update().get(variant=variant)
                stock.total_quantity -= quantity_to_deduct
                if stock.total_quantity < 0:
                    print(f"Warning: Stock became negative for {variant} after deleting InventoryItem {instance_id}. Setting to 0.")
                    stock.total_quantity = 0
                stock.save()
                Transaction.objects.create(
                   variant=variant,
                   quantity=-quantity_to_deduct,
                   transaction_type=Transaction.Type.ADJUSTMENT,
                   user=self.request.user,
                   receipt=receipt_ref,
                   notes=f"Penghapusan manual batch #{instance_id}"
                )
        except Stock.DoesNotExist:
             print(f"Error: Stock level not found for variant {variant.id} during InventoryItem delete.")
        except Exception as e:
             print(f"Error updating stock during InventoryItem delete {instance_id}: {e}")


    # --- ACTION UPLOAD RESI (LOGIKA DISESUAIKAN DENGAN PENDEKATAN C) ---
    @action(detail=False, methods=['post'], permission_classes=[IsOperator], serializer_class=ReceiptUploadSerializer)
    @transaction.atomic
    def upload_receipt(self, request):
        """
        Operator mengunggah file Excel/CSV berisi detail pembelian barang masuk.
        Mencari/Membuat ProductVariant, Membuat Receipt, InventoryItem, update Stock, Transaction log.
        Format file: Kode_Barang_Dasar, Jenis_Barang, Nama_Spesifik, Satuan, Jumlah, Harga_Beli_Satuan, Nomor_Kuitansi, Tanggal_Kuitansi, Nama_Supplier?, Tanggal_Kadaluarsa?
        """
        upload_serializer = ReceiptUploadSerializer(data=request.data)
        if not upload_serializer.is_valid():
            return Response(upload_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        file = upload_serializer.validated_data['file']
        processed_count = 0
        created_variants = 0
        error_rows = []
        receipt_cache = {}

        try:
            # Baca file Excel/CSV
            try: df = pd.read_excel(file, engine='openpyxl')
            except Exception:
                try:
                    file.seek(0)
                    df = pd.read_csv(file, sep=';') # Sesuaikan separator jika perlu
                except Exception as e_csv: raise serializers.ValidationError(f"Gagal membaca file. Pastikan format Excel (.xlsx) atau CSV (separator ';') valid. Detail: {e_csv}")

            # Validasi Nama Kolom BARU
            required_columns = ['Kode_Barang_Dasar', 'Jenis_Barang', 'Nama_Spesifik', 'Satuan', 'Jumlah', 'Harga_Beli_Satuan', 'Nomor_Kuitansi', 'Tanggal_Kuitansi']
            missing_cols = [col for col in required_columns if col not in df.columns]
            if missing_cols: raise serializers.ValidationError(f"Kolom berikut tidak ditemukan di file: {', '.join(missing_cols)}")

            # Loop per baris
            for index, row in df.iterrows():
                row_num = index + 2
                item_code_barang_obj = None # Reset per baris
                variant_obj = None
                receipt = None
                inventory_item = None
                stock = None
                base_code = 'N/A' # Default jika parsing gagal

                try:
                    # Ambil data dasar (sesuaikan nama kolom dgn format baru)
                    base_code = str(row['Kode_Barang_Dasar']).strip()
                    item_type_name = str(row['Jenis_Barang']).strip()
                    variant_spec_name = str(row['Nama_Spesifik']).strip()
                    unit = str(row['Satuan']).strip()
                    quantity = int(row['Jumlah'])
                    price_str = str(row['Harga_Beli_Satuan']).strip()
                    receipt_num = str(row['Nomor_Kuitansi']).strip()
                    receipt_date = pd.to_datetime(row['Tanggal_Kuitansi']).date()
                    supplier = str(row.get('Nama_Supplier', '') or '').strip()
                    expiry_str = str(row.get('Tanggal_Kadaluarsa', '') or '').strip()

                    # Validasi dasar
                    if not all([base_code, item_type_name, variant_spec_name, unit, quantity, price_str, receipt_num, receipt_date]):
                         raise ValueError("Kolom wajib (Kode Dasar, Jenis, Nama Spesifik, Satuan, Jumlah, Harga, No Kuitansi, Tgl Kuitansi) tidak boleh kosong.")
                    if quantity <= 0: raise ValueError("Jumlah harus positif.")
                    try: purchase_price = float(price_str.replace(',', '.'))
                    except ValueError: raise ValueError(f"Format Harga_Beli_Satuan tidak valid: '{price_str}'")
                    if purchase_price < 0: raise ValueError("Harga beli tidak boleh negatif.")

                    expiry_date = None
                    if expiry_str and expiry_str.lower() != 'nan': # Handle 'nan' dari pandas
                        try: expiry_date = pd.to_datetime(expiry_str).date()
                        except ValueError: print(f"Warning baris {row_num}: Format Tanggal_Kadaluarsa '{expiry_str}' tidak valid, akan diabaikan.")

                    # 1. Cari ItemCodeBarang berdasarkan Kode Barang Dasar
                    try:
                        # Cari langsung menggunakan field full_base_code
                        item_code_barang_obj = ItemCodeBarang.objects.get(full_base_code=base_code)
                    except ItemCodeBarang.DoesNotExist:
                         # Pesan error ini yang akan ditangkap oleh except Exception as e_row
                         raise ValueError(f"Kode Barang Dasar '{base_code}' tidak ditemukan di database.")


                    # 2. Cari atau Buat ProductVariant Spesifik (LOGIKA BARU)
                    variant_obj, variant_created = ProductVariant.objects.get_or_create(
                        base_item_code=item_code_barang_obj,
                        type_name__iexact=item_type_name,    # Cari berdasarkan jenis (case-insensitive)
                        name__iexact=variant_spec_name, # Cari berdasarkan nama spesifik (case-insensitive)
                        defaults={ # Hanya diisi saat create varian baru
                            'type_name': item_type_name,     # Simpan jenis
                            'name': variant_spec_name,       # Simpan nama spesifik
                            'unit_of_measure': unit
                            # specific_code dan full_code akan di-generate oleh model save()
                        }
                    )
                    if variant_created:
                         created_variants += 1
                         print(f"Info baris {row_num}: Membuat ProductVariant baru: {variant_obj.type_name} - {variant_obj.name} dengan kode {variant_obj.full_code}")
                    elif variant_obj.unit_of_measure.lower() != unit.lower():
                         print(f"Warning baris {row_num}: Satuan '{unit}' berbeda dgn Varian '{variant_obj.name}' ({variant_obj.unit_of_measure}). Menggunakan satuan yg sudah ada.")


                    # 3. Cari atau Buat Receipt (sama seperti sebelumnya)
                    receipt_key = (receipt_num, receipt_date)
                    receipt = receipt_cache.get(receipt_key)
                    if not receipt:
                        try:
                            receipt, receipt_created = Receipt.objects.get_or_create(
                                receipt_number=receipt_num,
                                receipt_date=receipt_date,
                                defaults={'supplier_name': supplier, 'uploaded_by': request.user}
                            )
                            receipt_cache[receipt_key] = receipt
                        except IntegrityError:
                             raise ValueError(f"Nomor Kuitansi '{receipt_num}' sudah ada dengan tanggal atau data lain yang berbeda.")


                    # 4. Buat InventoryItem (sama seperti sebelumnya)
                    inventory_item = InventoryItem(
                         variant=variant_obj, # Gunakan variant yg ditemukan/dibuat
                         receipt=receipt,
                         quantity=quantity,
                         purchase_price=purchase_price,
                         expiry_date=expiry_date,
                         added_by=request.user,
                         entry_date=timezone.now()
                    )
                    inventory_item.save() # Simpan item dulu

                    # 5. Update Stock Level (sama seperti sebelumnya)
                    stock, stock_created = Stock.objects.select_for_update().get_or_create(variant=variant_obj)
                    stock.total_quantity += quantity
                    stock.save()

                    # 6. Buat Transaction Log (sama seperti sebelumnya)
                    Transaction.objects.create(
                        variant=variant_obj,
                        inventory_item=inventory_item,
                        quantity=quantity,
                        transaction_type=Transaction.Type.IN,
                        user=request.user,
                        receipt=receipt, # Tambahkan referensi receipt
                        notes=f"Penerimaan barang via upload kuitansi #{receipt_num}. Item Batch #{inventory_item.id}"
                    )

                    processed_count += 1

                except Exception as e_row:
                    # Catat error per baris
                    error_rows.append({
                        "row": row_num,
                        "error": f"{type(e_row).__name__}: {str(e_row)}", # Sertakan tipe error
                        "data": row.to_dict()
                    })
                    # Print traceback untuk debug di server jika diperlukan
                    # print(f"Error processing row {row_num}:")
                    # traceback.print_exc()


            # Setelah loop selesai
            if error_rows:
                 # Jika ada error, batalkan transaksi (otomatis karena @transaction.atomic)
                 # dan kembalikan pesan error
                 raise serializers.ValidationError({
                     "message": f"Gagal memproses {len(error_rows)} baris dari file.",
                     "errors": error_rows
                 })

        except serializers.ValidationError as e_val:
             # Tangkap validation error yg di-raise manual (misal kolom hilang)
             return Response({"error": "Validasi file gagal.", "details": e_val.detail}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e_file:
             # Tangkap error pembacaan file atau error tak terduga lainnya
             print(f"Unexpected error during file processing:") # Log error ke server
             traceback.print_exc()
             return Response({"error": f"Terjadi kesalahan internal saat memproses file. Hubungi administrator."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Respons sukses
        return Response({
            "message": f"Berhasil memproses {processed_count} item barang dari file.",
            "processed_items": processed_count,
            "new_variants_created": created_variants,
            "failed_rows": len(error_rows)
        }, status=status.HTTP_201_CREATED)
    # --- AKHIR ACTION UPLOAD RESI ---

# --- Views Permintaan Barang (Workflow) ---

# class RequestViewSet(viewsets.ModelViewSet):
#     """Endpoint untuk mengelola permintaan barang dan alur kerjanya."""
#     # Sesuaikan prefetch_related
#     queryset = Request.objects.select_related(
#         'requester', 'supervisor1_approver', 'supervisor2_approver',
#         'operator_processor', 'spmb_document'
#     ).prefetch_related(
#         'items__variant__base_item_code' # Prefetch item, varian, dan kode dasarnya
#     ).all()

#     # get_serializer_class, get_permissions, get_queryset, perform_create, _add_log tetap sama
#     def get_serializer_class(self):
#         if self.action == 'list': return RequestListSerializer
#         if self.action == 'create': return RequestCreateSerializer
#         return RequestDetailSerializer
#     def get_permissions(self):
#         if self.action == 'create': self.permission_classes = [IsPeminta]
#         elif self.action in ['list', 'retrieve']: self.permission_classes = [permissions.IsAuthenticated]
#         elif self.action in ['update', 'partial_update']: self.permission_classes = [permissions.IsAuthenticated]
#         elif self.action == 'destroy': self.permission_classes = [IsOwnerOfRequest & permissions.SAFE_METHODS | IsAdminUser]
#         else: self.permission_classes = [permissions.IsAuthenticated]
#         return super().get_permissions()
#     def get_queryset(self):
#         user = self.request.user
#         queryset = super().get_queryset()
#         if user.is_admin: return queryset
#         elif user.is_peminta: return queryset.filter(requester=user)
#         elif user.is_atasan_peminta: return queryset.filter(status=Request.Status.SUBMITTED)
#         elif user.is_atasan_operator: return queryset.filter(status=Request.Status.APPROVED_SPV1)
#         elif user.is_operator: return queryset.filter(status__in=[Request.Status.APPROVED_SPV2, Request.Status.PROCESSING, Request.Status.COMPLETED])
#         else: return queryset.none()
#     def perform_create(self, serializer):
#         serializer.save(requester=self.request.user)
#     def _add_log(self, request_obj, user, action, comment=None, status_from=None, status_to=None):
#          RequestLog.objects.create(
#              request=request_obj, user=user, action=action,
#              status_from=status_from or request_obj.status,
#              status_to=status_to or request_obj.status,
#              comment=comment
#          )

#     # --- Custom Actions for Workflow (Tetap Sama) ---
#     @action(detail=True, methods=['post'], permission_classes=[IsOwnerOfRequest])
#     def submit(self, request, pk=None):
#         # ... (Kode sama seperti sebelumnya) ...
#         req = self.get_object();
#         if req.status != Request.Status.DRAFT: return Response(...)
#         if not req.items.exists(): return Response(...)
#         if not req.request_number: req.status=Request.Status.SUBMITTED; req.submitted_at=timezone.now(); req.save()
#         else: req.status=Request.Status.SUBMITTED; req.submitted_at=timezone.now(); req.save(...)
#         self._add_log(...)
#         serializer = self.get_serializer(req); return Response(serializer.data)

#     @action(detail=True, methods=['post'], permission_classes=[CanApproveRequestSpv1])
#     def approve_spv1(self, request, pk=None):
#         # ... (Kode sama seperti sebelumnya) ...
#         req = self.get_object();
#         if req.status != Request.Status.SUBMITTED: return Response(...)
#         req.status=Request.Status.APPROVED_SPV1; req.supervisor1_approver=request.user; req.supervisor1_decision_at=timezone.now(); req.save(...)
#         self._add_log(...)
#         serializer = self.get_serializer(req); return Response(serializer.data)

class RequestViewSet(viewsets.ModelViewSet):
    """Endpoint untuk mengelola permintaan barang dan alur kerjanya."""
    # --- QuerySet dan konfigurasi lain seperti sebelumnya ---
    queryset = Request.objects.select_related(
        'requester', 'supervisor1_approver', 'supervisor2_approver',
        'operator_processor', 'spmb_document'
    ).prefetch_related(
        'items__variant__base_item_code' # Sesuaikan prefetch jika perlu
    ).all()

    def get_serializer_class(self):
        if self.action == 'list': return RequestListSerializer
        if self.action == 'create': return RequestCreateSerializer
        return RequestDetailSerializer

    def get_permissions(self):
        # --- PERBAIKAN: Gunakan IsPeminta dari permissions.py ---
        if self.action == 'create': self.permission_classes = [IsPeminta]
        # --- AKHIR PERBAIKAN ---
        elif self.action in ['list', 'retrieve']: self.permission_classes = [permissions.IsAuthenticated]
        elif self.action in ['update', 'partial_update']: self.permission_classes = [permissions.IsAuthenticated]
        elif self.action == 'destroy': self.permission_classes = [IsOwnerOfRequest & permissions.SAFE_METHODS | IsAdminUser]
        # Permissions untuk custom actions diatur di decorator @action
        # Jika tidak diatur di decorator, permission default viewset akan berlaku
        # atau Anda bisa tambahkan kondisi elif untuk action spesifik di sini
        else: self.permission_classes = [permissions.IsAuthenticated] # Default
        return super().get_permissions()


    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        if user.is_admin: return queryset
        elif user.is_peminta: return queryset.filter(requester=user)
        elif user.is_atasan_peminta: return queryset.filter(status=Request.Status.SUBMITTED)
        elif user.is_atasan_operator: return queryset.filter(status=Request.Status.APPROVED_SPV1)
        elif user.is_operator: return queryset.filter(status__in=[Request.Status.APPROVED_SPV2, Request.Status.PROCESSING, Request.Status.COMPLETED])
        else: return queryset.none()

    def perform_create(self, serializer):
        serializer.save(requester=self.request.user)

    # --- Definisi _add_log (Tetap sama) ---
    def _add_log(self, request_obj, user, action, comment=None, status_from=None, status_to=None):
         """Helper untuk mencatat log."""
         print(f"--- _add_log DIPANGGIL: action={action}, user={user} ---") # DEBUG PEMANGGILAN
         try:
             RequestLog.objects.create(
                 request=request_obj,
                 user=user,
                 action=action,
                 status_from=status_from or request_obj.status,
                 status_to=status_to or request_obj.status,
                 comment=comment
             )
             print(f"--- _add_log SUKSES: action={action} ---") # DEBUG SUKSES
         except Exception as e:
             print(f"--- _add_log ERROR: Gagal membuat log untuk action={action} ---") # DEBUG ERROR
             traceback.print_exc()
    # --- AKHIR DEFINISI _add_log ---


    # --- Custom Actions for Workflow ---

    @action(detail=True, methods=['post'], permission_classes=[IsOwnerOfRequest])
    def submit(self, request, pk=None):
        """Aksi Peminta untuk mengajukan request dari DRAFT."""
        print("--- Action 'submit' dimulai ---")
        req = self.get_object()
        if req.status != Request.Status.DRAFT:
            return Response({"error": "Hanya request DRAFT yang bisa diajukan."}, status=status.HTTP_400_BAD_REQUEST)
        if not req.items.exists():
             return Response({"error": "Request harus memiliki minimal 1 item barang."}, status=status.HTTP_400_BAD_REQUEST)

        status_sebelum = req.status

        if not req.request_number:
             req.status = Request.Status.SUBMITTED
             req.submitted_at = timezone.now()
             print(f"--- Action 'submit': Memanggil req.save() ---")
             req.save()
        else:
             req.status = Request.Status.SUBMITTED
             req.submitted_at = timezone.now()
             print(f"--- Action 'submit': Memanggil req.save(update_fields) ---")
             req.save(update_fields=['status', 'submitted_at'])

        print(f"--- Action 'submit': Persiapan memanggil _add_log ---")
        print(f"--- Argumen req: {req} (ID: {req.id}) ---")
        print(f"--- Argumen request.user: {request.user} (ID: {request.user.id}) ---")
        print(f"--- Argumen action: 'SUBMIT' ---")
        print(f"--- Argumen status_from: {status_sebelum} ---")
        print(f"--- Argumen status_to: {Request.Status.SUBMITTED} ---")

        try:
            # --- PERUBAHAN: Panggil dengan argumen posisi ---
            self._add_log(
                req,                    # request_obj (posisi 1 setelah self)
                request.user,           # user (posisi 2 setelah self)
                "SUBMIT",               # action (posisi 3 setelah self)
                status_from=status_sebelum,
                status_to=Request.Status.SUBMITTED
                # comment=None (opsional, biarkan default)
            )
            # --- AKHIR PERUBAHAN ---
        except TypeError as te:
             print(f"--- Action 'submit': TypeError saat memanggil _add_log! ---")
             traceback.print_exc()
             return Response({"error": "Internal error saat logging (TypeError)."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e_log:
             print(f"--- Action 'submit': Exception lain saat memanggil _add_log: {type(e_log).__name__} ---")
             traceback.print_exc()

        print("--- Action 'submit' selesai, menyiapkan response ---")
        serializer = self.get_serializer(req)
        return Response(serializer.data)

    # --- Pastikan pemanggilan _add_log di action lain juga benar ---
    @action(detail=True, methods=['post'], permission_classes=[CanApproveRequestSpv1])
    def approve_spv1(self, request, pk=None):
        req = self.get_object()
        if req.status != Request.Status.SUBMITTED: return Response({"error": "Hanya request SUBMITTED yang bisa disetujui SPV1."}, status=status.HTTP_400_BAD_REQUEST)
        status_sebelum = req.status
        req.status = Request.Status.APPROVED_SPV1
        req.supervisor1_approver = request.user
        req.supervisor1_decision_at = timezone.now()
        req.save(update_fields=['status', 'supervisor1_approver', 'supervisor1_decision_at'])
        # Panggil dengan argumen posisi
        self._add_log(req, request.user, "APPROVE_SPV1", status_from=status_sebelum, status_to=req.status)
        serializer = self.get_serializer(req)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[CanApproveRequestSpv1])
    def reject_spv1(self, request, pk=None):
        # ... (Kode sama seperti sebelumnya) ...
        req = self.get_object(); comment = request.data.get('comment');
        if not comment: return Response(...)
        if req.status != Request.Status.SUBMITTED: return Response(...)
        req.status=Request.Status.REJECTED_SPV1; req.supervisor1_approver=request.user; req.supervisor1_decision_at=timezone.now(); req.supervisor1_rejection_reason=comment; req.save(...)
        self._add_log(...)
        serializer = self.get_serializer(req); return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[CanApproveRequestSpv2])
    def approve_spv2(self, request, pk=None):
        # ... (Kode sama seperti sebelumnya) ...
        req = self.get_object();
        if req.status != Request.Status.APPROVED_SPV1: return Response(...)
        approved_items_data = request.data.get('items', []); item_updates = {item['id']: item['quantity_approved'] for item in approved_items_data if 'id' in item and 'quantity_approved' in item};
        try:
             with transaction.atomic():
                 req.status=Request.Status.APPROVED_SPV2; req.supervisor2_approver=request.user; req.supervisor2_decision_at=timezone.now(); req.save(...)
                 for item in req.items.all():
                      approved_qty = item_updates.get(item.id)
                      if approved_qty is not None:
                           if approved_qty < 0: raise serializers.ValidationError(...)
                           if approved_qty > item.quantity_requested: raise serializers.ValidationError(...)
                           item.quantity_approved_spv2 = approved_qty
                           item.save(update_fields=['quantity_approved_spv2'])
                      else:
                           item.quantity_approved_spv2 = 0
                           item.save(update_fields=['quantity_approved_spv2'])
                 self._add_log(...)
        except serializers.ValidationError as e: return Response({"error": e.detail}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e: return Response({"error": f"Terjadi kesalahan internal: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        serializer = self.get_serializer(req); return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[CanApproveRequestSpv2])
    def reject_spv2(self, request, pk=None):
        # ... (Kode sama seperti sebelumnya) ...
        req = self.get_object(); comment = request.data.get('comment');
        if not comment: return Response(...)
        if req.status != Request.Status.APPROVED_SPV1: return Response(...)
        req.status=Request.Status.REJECTED_SPV2; req.supervisor2_approver=request.user; req.supervisor2_decision_at=timezone.now(); req.supervisor2_rejection_reason=comment; req.save(...)
        self._add_log(...)
        serializer = self.get_serializer(req); return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[CanProcessRequestOperator])
    @transaction.atomic
    def process(self, request, pk=None):
        # ... (Kode FIFO sama seperti sebelumnya) ...
        req = self.get_object();
        if req.status != Request.Status.APPROVED_SPV2: return Response(...)
        items_to_issue = req.items.filter(quantity_approved_spv2__gt=0);
        if not items_to_issue.exists():
             req.status = Request.Status.COMPLETED; req.operator_processor = request.user; req.operator_processed_at = timezone.now(); req.save(...); self._add_log(...); return Response(...)
        transactions_to_create = []; spmb = None;
        for item in items_to_issue:
            variant=item.variant; qty_to_issue=item.quantity_approved_spv2; qty_issued_so_far=0;
            inventory_batches = InventoryItem.objects.select_for_update().filter(variant=variant, quantity__gt=0).order_by('entry_date', 'id');
            if not inventory_batches.exists(): raise serializers.ValidationError(f"Stok habis untuk barang '{variant.name}'. Proses dibatalkan.")
            for batch in inventory_batches:
                take_from_batch = min(qty_to_issue - qty_issued_so_far, batch.quantity);
                if take_from_batch > 0:
                    batch.quantity-=take_from_batch; batch.save(...);
                    stock=Stock.objects.select_for_update().get(variant=variant); stock.total_quantity-=take_from_batch; stock.save(...);
                    transactions_to_create.append(Transaction(variant=variant, inventory_item=batch, quantity=-take_from_batch, transaction_type=Transaction.Type.OUT, user=request.user, related_request=req, notes=f"Pengeluaran untuk Request #{req.id}"));
                    qty_issued_so_far+=take_from_batch;
                if qty_issued_so_far >= qty_to_issue: break
            if qty_issued_so_far < qty_to_issue: raise serializers.ValidationError(f"Stok tidak mencukupi untuk '{variant.name}'. Diminta {qty_to_issue}, tersedia {qty_issued_so_far}. Proses dibatalkan.")
            item.quantity_issued=qty_issued_so_far; item.save(...)
        spmb = SPMB.objects.create(request=req, issued_by=request.user);
        req.status=Request.Status.COMPLETED; req.operator_processor=request.user; req.operator_processed_at=timezone.now(); req.save(...)
        for t in transactions_to_create: t.related_spmb = spmb
        Transaction.objects.bulk_create(transactions_to_create)
        self._add_log(...)
        serializer = self.get_serializer(req); response_data = serializer.data; response_data['spmb_info'] = SPMBSerializer(spmb).data; return Response(response_data)

    @action(detail=True, methods=['post'], permission_classes=[CanProcessRequestOperator])
    def reject_opr(self, request, pk=None):
        # ... (Kode sama seperti sebelumnya) ...
        req = self.get_object(); comment = request.data.get('comment');
        if not comment: return Response(...)
        if req.status != Request.Status.APPROVED_SPV2: return Response(...)
        req.status=Request.Status.REJECTED_OPR; req.operator_processor=request.user; req.operator_processed_at=timezone.now(); req.operator_rejection_reason=comment; req.save(...)
        self._add_log(...)
        serializer = self.get_serializer(req); return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsOwnerOfRequest])
    def receive(self, request, pk=None):
        # ... (Kode sama seperti sebelumnya) ...
        req = self.get_object();
        if req.status != Request.Status.COMPLETED: return Response(...)
        req.status=Request.Status.RECEIVED; req.received_at=timezone.now(); req.save(...)
        self._add_log(...)
        serializer = self.get_serializer(req); return Response(serializer.data)


# --- Views Lain (SPMB, Log, Transaksi) ---
class SPMBViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SPMB.objects.select_related('request__requester', 'issued_by').all()
    serializer_class = SPMBSerializer
    permission_classes = [permissions.IsAuthenticated]
    # get_queryset tetap sama

class RequestLogViewSet(viewsets.ReadOnlyModelViewSet):
     queryset = RequestLog.objects.select_related('request', 'user').all()
     serializer_class = RequestLogSerializer
     permission_classes = [IsAdminUser]

class TransactionViewSet(viewsets.ReadOnlyModelViewSet):
    # Sesuaikan select_related untuk variant
    queryset = Transaction.objects.select_related(
        'variant__base_item_code', 'user', 'inventory_item',
        'related_request', 'related_spmb', 'receipt' # Tambahkan receipt
        ).all()
    serializer_class = TransactionSerializer
    permission_classes = [IsAdminUser | IsOperator]

# --- Views Stock Opname ---
class StockOpnameSessionViewSet(viewsets.ModelViewSet):
     queryset = StockOpnameSession.objects.select_related('created_by').all()
     serializer_class = StockOpnameSessionSerializer
     permission_classes = [IsAdminUser]
     # Pastikan action upload_opname TIDAK ada di sini

class StockOpnameItemViewSet(viewsets.ModelViewSet):
    # Sesuaikan select_related
    queryset = StockOpnameItem.objects.select_related(
        'opname_session', 'variant__base_item_code', 'confirmed_by').all()
    serializer_class = StockOpnameItemSerializer
    # get_permissions, confirm action tetap sama
    def get_permissions(self):
         if self.action == 'confirm': self.permission_classes = [IsOperator]
         else: self.permission_classes = [IsOperator | IsAdminUser]
         return super().get_permissions()
    @action(detail=True, methods=['post'], serializer_class=StockOpnameConfirmSerializer)
    @transaction.atomic
    def confirm(self, request, pk=None):
         # ... (Kode sama seperti sebelumnya) ...
         item = self.get_object(); #...
         if item.confirmation_status != StockOpnameItem.ConfirmationStatus.PENDING: return Response(...)
         confirm_serializer = StockOpnameConfirmSerializer(data=request.data); #...
         if not confirm_serializer.is_valid(): return Response(...)
         validated_data = confirm_serializer.validated_data; new_status=validated_data[...]; notes=validated_data[...]; #...
         item.confirmation_status = new_status; item.confirmation_notes = notes; item.confirmed_by = request.user; item.confirmed_at = timezone.now(); item.save(); #...
         if new_status == StockOpnameItem.ConfirmationStatus.CONFIRMED_ADJUST and item.difference != 0: #...
              stock, created = Stock.objects.select_for_update().get_or_create(...); #...
              original_stock = stock.total_quantity; stock.total_quantity += item.difference; stock.save(); #...
              Transaction.objects.create(...); #...
         serializer = self.get_serializer(item); return Response(serializer.data) #...


# --- View Dashboard (Placeholder) ---
class DashboardDataView(APIView):
     permission_classes = [permissions.IsAuthenticated]
     # get method tetap sama seperti sebelumnya
     def get(self, request, *args, **kwargs):
          user=request.user; data={};
          if user.is_admin or user.is_operator or user.is_atasan_operator:
              data['total_variants'] = ProductVariant.objects.count();
              # Perlu import F di atas file: from django.db.models import F
              data['low_stock_items'] = StockSerializer(Stock.objects.filter(total_quantity__lte=F('low_stock_threshold')), many=True, context={'request': request}).data;
              data['pending_requests_spv2'] = Request.objects.filter(status=Request.Status.APPROVED_SPV1).count();
              data['pending_opname_confirmations'] = StockOpnameItem.objects.filter(confirmation_status=StockOpnameItem.ConfirmationStatus.PENDING).count();
          if user.is_peminta:
              data['my_draft_requests'] = Request.objects.filter(requester=user, status=Request.Status.DRAFT).count();
              data['my_pending_requests'] = Request.objects.filter(requester=user, status__in=[Request.Status.SUBMITTED, Request.Status.APPROVED_SPV1]).count();
          return Response(data)

# --- ReceiptViewSet (Untuk Input Manual) ---
class ReceiptViewSet(viewsets.ModelViewSet):
    """API endpoint untuk mengelola data Kuitansi Pembelian."""
    queryset = Receipt.objects.select_related('uploaded_by').all()
    serializer_class = ReceiptSerializer
    permission_classes = [IsOperator] # Hanya Operator/Admin

    def perform_create(self, serializer):
        # Set uploaded_by otomatis saat Operator membuat via API
        serializer.save(uploaded_by=self.request.user)

