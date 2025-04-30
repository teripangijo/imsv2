# backend/inventory/views.py
from rest_framework import viewsets, status, permissions, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import serializers
from rest_framework.views import APIView
from django.db.models import F # Pastikan F diimpor jika digunakan di DashboardDataView
from django.db import transaction, IntegrityError
from django.utils import timezone
# from django.shortcuts import get_object_or_404 # Mungkin tidak terpakai
import pandas as pd
import openpyxl
import traceback # Untuk debugging jika perlu

# Impor model dengan benar
from .models import (
    ProductVariant, InventoryItem, Stock,
    Request, RequestItem, SPMB, RequestLog, Transaction,
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
    StockOpnameConfirmSerializer,
    ReceiptUploadSerializer, ReceiptSerializer, # Pastikan ReceiptSerializer diimpor jika ReceiptViewSet dibuat
    # Mungkin perlu ItemCode... serializers jika ada ViewSetnya
    ItemCodeBarangSerializer # Impor jika diperlukan nanti
)
# Impor permission kustom
from .permissions import (
    IsAdminUser, IsOperatorOrReadOnly, IsOperator, IsPeminta,
    IsAtasanPeminta, IsAtasanOperator, CanApproveRequestSpv1,
    CanApproveRequestSpv2, CanProcessRequestOperator, IsOwnerOfRequest
)

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

class RequestViewSet(viewsets.ModelViewSet):
    """Endpoint untuk mengelola permintaan barang dan alur kerjanya."""
    # Sesuaikan prefetch_related
    queryset = Request.objects.select_related(
        'requester', 'supervisor1_approver', 'supervisor2_approver',
        'operator_processor', 'spmb_document'
    ).prefetch_related(
        'items__variant__base_item_code' # Prefetch item, varian, dan kode dasarnya
    ).all()

    # get_serializer_class, get_permissions, get_queryset, perform_create, _add_log tetap sama
    def get_serializer_class(self):
        if self.action == 'list': return RequestListSerializer
        if self.action == 'create': return RequestCreateSerializer
        return RequestDetailSerializer
    def get_permissions(self):
        if self.action == 'create': self.permission_classes = [IsPeminta]
        elif self.action in ['list', 'retrieve']: self.permission_classes = [permissions.IsAuthenticated]
        elif self.action in ['update', 'partial_update']: self.permission_classes = [permissions.IsAuthenticated]
        elif self.action == 'destroy': self.permission_classes = [IsOwnerOfRequest & permissions.SAFE_METHODS | IsAdminUser]
        else: self.permission_classes = [permissions.IsAuthenticated]
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
    def _add_log(self, request_obj, user, action, comment=None, status_from=None, status_to=None):
         RequestLog.objects.create(
             request=request_obj, user=user, action=action,
             status_from=status_from or request_obj.status,
             status_to=status_to or request_obj.status,
             comment=comment
         )

    # --- Custom Actions for Workflow (Tetap Sama) ---
    @action(detail=True, methods=['post'], permission_classes=[IsOwnerOfRequest])
    def submit(self, request, pk=None):
        # ... (Kode sama seperti sebelumnya) ...
        req = self.get_object();
        if req.status != Request.Status.DRAFT: return Response(...)
        if not req.items.exists(): return Response(...)
        if not req.request_number: req.status=Request.Status.SUBMITTED; req.submitted_at=timezone.now(); req.save()
        else: req.status=Request.Status.SUBMITTED; req.submitted_at=timezone.now(); req.save(...)
        self._add_log(...)
        serializer = self.get_serializer(req); return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[CanApproveRequestSpv1])
    def approve_spv1(self, request, pk=None):
        # ... (Kode sama seperti sebelumnya) ...
        req = self.get_object();
        if req.status != Request.Status.SUBMITTED: return Response(...)
        req.status=Request.Status.APPROVED_SPV1; req.supervisor1_approver=request.user; req.supervisor1_decision_at=timezone.now(); req.save(...)
        self._add_log(...)
        serializer = self.get_serializer(req); return Response(serializer.data)

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

