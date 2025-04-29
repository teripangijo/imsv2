# backend/inventory/views.py
from rest_framework import viewsets, status, permissions, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import serializers
from rest_framework.views import APIView
from django.db.models import F
from django.db import transaction # Untuk atomicity
from django.utils import timezone
from django.shortcuts import get_object_or_404
import pandas as pd # Untuk import Excel, tambahkan ke requirements.txt nanti
import openpyxl # Juga untuk Excel

from .models import (
    ProductCategory, ProductVariant, InventoryItem, Stock,
    Request, RequestItem, SPMB, RequestLog, Transaction,
    StockOpnameSession, StockOpnameItem
)
from .serializers import (
    ProductCategorySerializer, ProductVariantSerializer, InventoryItemSerializer,
    InventoryItemCreateSerializer, StockSerializer, RequestListSerializer,
    RequestDetailSerializer, RequestCreateSerializer, SPMBSerializer,
    RequestLogSerializer, TransactionSerializer, StockOpnameSessionSerializer,
    StockOpnameItemSerializer, StockOpnameFileUploadSerializer,
    StockOpnameConfirmSerializer
)
# Impor permission kustom
from .permissions import (
    IsAdminUser, IsOperatorOrReadOnly, IsOperator, IsPeminta,
    IsAtasanPeminta, IsAtasanOperator, CanApproveRequestSpv1,
    CanApproveRequestSpv2, CanProcessRequestOperator, IsOwnerOfRequest
)

# --- Views Produk & Stok ---

class ProductCategoryViewSet(viewsets.ModelViewSet):
    queryset = ProductCategory.objects.all()
    serializer_class = ProductCategorySerializer
    permission_classes = [IsAdminUser | IsOperatorOrReadOnly] # Admin/Operator bisa R/W, lain hanya R

class ProductVariantViewSet(viewsets.ModelViewSet):
    queryset = ProductVariant.objects.select_related('category').all() # Optimasi query
    serializer_class = ProductVariantSerializer
    permission_classes = [IsAdminUser | IsOperatorOrReadOnly]

class StockViewSet(viewsets.ReadOnlyModelViewSet):
    """Menampilkan daftar stok barang."""
    queryset = Stock.objects.select_related('variant__category').order_by('variant__name') # Optimasi
    serializer_class = StockSerializer
    permission_classes = [permissions.IsAuthenticated] # Semua user login bisa lihat stok

    def get_queryset(self):
        """Filter stok berdasarkan ketersediaan untuk Peminta."""
        user = self.request.user
        queryset = super().get_queryset()
        # Peminta hanya lihat nama & jumlah. Info harga dll disembunyikan serializer/view
        # Tidak perlu filter di sini karena serializer StockSerializer tidak ekspos harga
        # Filtering tampilan (warna abu2) dilakukan di frontend berdasarkan total_quantity <= 0
        return queryset

class InventoryItemViewSet(viewsets.ModelViewSet):
    """Endpoint untuk mengelola batch inventaris (FIFO)."""
    queryset = InventoryItem.objects.select_related('variant__category', 'added_by').all()
    permission_classes = [IsOperator] # Hanya Operator/Admin

    def get_serializer_class(self):
        if self.action == 'create':
            return InventoryItemCreateSerializer
        return InventoryItemSerializer

    def perform_create(self, serializer):
        # Set added_by otomatis
        inventory_item = serializer.save(added_by=self.request.user)
        # --- Update Stock Level (PENTING) ---
        try:
            with transaction.atomic(): # Pastikan update stok & item inventory konsisten
                stock, created = Stock.objects.select_for_update().get_or_create(
                    variant=inventory_item.variant
                )
                stock.total_quantity += inventory_item.quantity
                stock.save()
                # Buat juga record Transaction
                Transaction.objects.create(
                    variant=inventory_item.variant,
                    inventory_item=inventory_item,
                    quantity=inventory_item.quantity, # Positif untuk IN
                    transaction_type=Transaction.Type.IN,
                    user=self.request.user,
                    notes=f"Penerimaan barang baru batch #{inventory_item.id}"
                )
        except Exception as e:
             # Jika gagal update stok, hapus inventory item yg baru dibuat? Atau log error?
             # Untuk sekarang log saja, idealnya ada mekanisme recovery
             print(f"Error updating stock for InventoryItem {inventory_item.id}: {e}")
             # Hapus item jika gagal update stok? Tergantung requirement
             # inventory_item.delete()
             # raise serializers.ValidationError("Gagal memperbarui level stok.")

    def perform_update(self, serializer):
         # TODO: Logika update batch inventaris jika diperlukan.
         # Perlu hati-hati karena bisa mempengaruhi stok total.
         # Mungkin perlu re-kalkulasi Stock? Atau hanya boleh edit field tertentu?
         # Untuk sekarang, anggap update terbatas atau perlu penanganan khusus.
         # Jika quantity diubah, Stock HARUS diupdate juga.
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
                    # Update/Create Transaction? Mungkin perlu tipe ADJUSTMENT
                    Transaction.objects.create(
                        variant=updated_item.variant,
                        inventory_item=updated_item,
                        quantity=quantity_diff,
                        transaction_type=Transaction.Type.ADJUSTMENT,
                        user=self.request.user,
                        notes=f"Penyesuaian manual batch #{updated_item.id}"
                    )
            except Stock.DoesNotExist:
                 print(f"Error: Stock level not found for variant {updated_item.variant.id} during InventoryItem update.")
                 # Handle error, maybe raise validation error
            except Exception as e:
                 print(f"Error updating stock during InventoryItem update {updated_item.id}: {e}")
                 # Roll back changes? Raise validation error?

    def perform_destroy(self, instance):
         # TODO: Logika saat menghapus batch inventaris.
         # Stock HARUS dikurangi sejumlah quantity item yang dihapus.
         variant = instance.variant
         quantity_to_deduct = instance.quantity
         try:
              with transaction.atomic():
                 instance.delete() # Hapus item dulu
                 stock = Stock.objects.select_for_update().get(variant=variant)
                 stock.total_quantity -= quantity_to_deduct
                 if stock.total_quantity < 0:
                      # Ini seharusnya tidak terjadi jika data konsisten, tapi handle just in case
                      print(f"Warning: Stock became negative for {variant} after deleting InventoryItem {instance.id}. Setting to 0.")
                      stock.total_quantity = 0
                 stock.save()
                 # Buat Transaction log penghapusan
                 Transaction.objects.create(
                    variant=variant,
                    # inventory_item=instance, # instance sudah dihapus
                    quantity=-quantity_to_deduct, # Negatif
                    transaction_type=Transaction.Type.ADJUSTMENT,
                    user=self.request.user,
                    notes=f"Penghapusan manual batch #{instance.id}"
                 )
         except Stock.DoesNotExist:
              print(f"Error: Stock level not found for variant {variant.id} during InventoryItem delete.")
              # Handle error
         except Exception as e:
              print(f"Error updating stock during InventoryItem delete {instance.id}: {e}")
              # Roll back? Transaction should handle this implicitly

# --- Views Permintaan Barang (Workflow) ---

class RequestViewSet(viewsets.ModelViewSet):
    """Endpoint untuk mengelola permintaan barang dan alur kerjanya."""
    queryset = Request.objects.select_related(
        'requester', 'supervisor1_approver', 'supervisor2_approver',
        'operator_processor', 'spmb_document'
    ).prefetch_related('items__variant__category').all() # Optimasi query

    def get_serializer_class(self):
        if self.action == 'list':
            return RequestListSerializer
        if self.action == 'create':
            return RequestCreateSerializer
        # Untuk retrieve, update (status), partial_update (status), actions
        return RequestDetailSerializer

    def get_permissions(self):
        """Tetapkan permission berdasarkan action."""
        if self.action == 'create':
            self.permission_classes = [IsPeminta]
        elif self.action in ['list', 'retrieve']:
            # Semua user bisa lihat list/detail, tapi queryset akan difilter
            self.permission_classes = [permissions.IsAuthenticated]
        elif self.action in ['update', 'partial_update']:
             # Hanya pemilik saat DRAFT, atau approver/admin di status lain
             # Dibatasi lebih ketat di dalam action saja
             self.permission_classes = [permissions.IsAuthenticated]
        elif self.action == 'destroy':
            # Hanya pemilik saat DRAFT, atau Admin
             self.permission_classes = [IsOwnerOfRequest & permissions.SAFE_METHODS | IsAdminUser] # Contoh gabungan
        # Permissions untuk custom actions diatur di decorator @action
        else:
             self.permission_classes = [permissions.IsAuthenticated] # Default
        return super().get_permissions()

    def get_queryset(self):
        """Filter request berdasarkan peran user."""
        user = self.request.user
        queryset = super().get_queryset()

        if user.is_admin:
            return queryset # Admin lihat semua
        elif user.is_peminta:
            # Peminta lihat request miliknya saja
            return queryset.filter(requester=user)
        elif user.is_atasan_peminta:
            # Atasan Peminta lihat request yang statusnya SUBMITTED (menunggu dia)
            # Idealnya: filter berdasarkan peminta yang merupakan bawahannya
            # Atau filter berdasarkan departemen yang sama?
            # return queryset.filter(status=Request.Status.SUBMITTED, requester__department_code=user.department_code)
            return queryset.filter(status=Request.Status.SUBMITTED) # Sementara lihat semua yg submitted
        elif user.is_atasan_operator:
            # Atasan Operator lihat request yang statusnya APPROVED_SPV1 (menunggu dia)
            return queryset.filter(status=Request.Status.APPROVED_SPV1)
        elif user.is_operator:
            # Operator lihat request yang statusnya APPROVED_SPV2 (menunggu dia proses) atau sedang diproses
            return queryset.filter(status__in=[Request.Status.APPROVED_SPV2, Request.Status.PROCESSING, Request.Status.COMPLETED])
        else:
            # Jika ada role lain atau user tidak punya role, jangan tampilkan apa-apa
            return queryset.none()

    def perform_create(self, serializer):
        # Set requester otomatis saat Peminta membuat request (status default DRAFT)
        serializer.save(requester=self.request.user)

    def _add_log(self, request_obj, user, action, comment=None, status_from=None, status_to=None):
         """Helper untuk mencatat log."""
         RequestLog.objects.create(
             request=request_obj,
             user=user,
             action=action,
             status_from=status_from or request_obj.status,
             status_to=status_to or request_obj.status,
             comment=comment
         )

    # --- Custom Actions for Workflow ---

    @action(detail=True, methods=['post'], permission_classes=[IsOwnerOfRequest])
    def submit(self, request, pk=None):
        """Aksi Peminta untuk mengajukan request dari DRAFT."""
        req = self.get_object()
        if req.status != Request.Status.DRAFT:
            return Response({"error": "Hanya request DRAFT yang bisa diajukan."}, status=status.HTTP_400_BAD_REQUEST)
        if not req.items.exists():
             return Response({"error": "Request harus memiliki minimal 1 item barang."}, status=status.HTTP_400_BAD_REQUEST)

        # Generate nomor request saat submit
        if not req.request_number:
             # Trigger _generate_request_number via save()
             req.status = Request.Status.SUBMITTED # Ubah status dulu agar save() men-generate nomor
             req.submitted_at = timezone.now()
             req.save() # Ini akan memanggil _generate_request_number
        else:
             # Jika nomor sudah ada (jarang terjadi di DRAFT), langsung update status
             req.status = Request.Status.SUBMITTED
             req.submitted_at = timezone.now()
             req.save(update_fields=['status', 'submitted_at'])

        self._add_log(req, request.user, "SUBMIT", status_from=Request.Status.DRAFT, status_to=Request.Status.SUBMITTED)
        serializer = self.get_serializer(req)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[CanApproveRequestSpv1])
    def approve_spv1(self, request, pk=None):
        """Aksi Atasan Peminta untuk menyetujui."""
        req = self.get_object()
        if req.status != Request.Status.SUBMITTED:
            return Response({"error": "Hanya request SUBMITTED yang bisa disetujui SPV1."}, status=status.HTTP_400_BAD_REQUEST)

        req.status = Request.Status.APPROVED_SPV1
        req.supervisor1_approver = request.user
        req.supervisor1_decision_at = timezone.now()
        req.save(update_fields=['status', 'supervisor1_approver', 'supervisor1_decision_at'])
        self._add_log(req, request.user, "APPROVE_SPV1", status_from=Request.Status.SUBMITTED, status_to=Request.Status.APPROVED_SPV1)
        serializer = self.get_serializer(req)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[CanApproveRequestSpv1])
    def reject_spv1(self, request, pk=None):
        """Aksi Atasan Peminta untuk menolak."""
        req = self.get_object()
        comment = request.data.get('comment', None)
        if not comment:
            return Response({"comment": ["Komentar penolakan wajib diisi."]}, status=status.HTTP_400_BAD_REQUEST)
        if req.status != Request.Status.SUBMITTED:
            return Response({"error": "Hanya request SUBMITTED yang bisa ditolak SPV1."}, status=status.HTTP_400_BAD_REQUEST)

        req.status = Request.Status.REJECTED_SPV1
        req.supervisor1_approver = request.user
        req.supervisor1_decision_at = timezone.now()
        req.supervisor1_rejection_reason = comment
        req.save(update_fields=['status', 'supervisor1_approver', 'supervisor1_decision_at', 'supervisor1_rejection_reason'])
        self._add_log(req, request.user, "REJECT_SPV1", comment=comment, status_from=Request.Status.SUBMITTED, status_to=Request.Status.REJECTED_SPV1)
        # Request dikembalikan ke Peminta (status REJECTED_SPV1)
        serializer = self.get_serializer(req)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[CanApproveRequestSpv2])
    def approve_spv2(self, request, pk=None):
        """Aksi Atasan Operator untuk menyetujui + set kuantitas final."""
        req = self.get_object()
        if req.status != Request.Status.APPROVED_SPV1:
             return Response({"error": "Hanya request APPROVED_SPV1 yang bisa disetujui SPV2."}, status=status.HTTP_400_BAD_REQUEST)

        # Data kuantitas yg disetujui per item (dikirim dari frontend)
        # Format: { "items": [ {"id": item_id1, "quantity_approved": qty1}, {"id": item_id2, "quantity_approved": qty2} ] }
        approved_items_data = request.data.get('items', [])
        item_updates = {item['id']: item['quantity_approved'] for item in approved_items_data if 'id' in item and 'quantity_approved' in item}

        try:
            with transaction.atomic():
                req.status = Request.Status.APPROVED_SPV2
                req.supervisor2_approver = request.user
                req.supervisor2_decision_at = timezone.now()
                req.save(update_fields=['status', 'supervisor2_approver', 'supervisor2_decision_at'])

                # Update kuantitas disetujui pada setiap item
                for item in req.items.all():
                    approved_qty = item_updates.get(item.id)
                    if approved_qty is not None:
                         # Validasi: tidak boleh lebih dari yg diminta
                         if approved_qty < 0:
                             raise serializers.ValidationError(f"Kuantitas disetujui untuk {item.variant.name} tidak boleh negatif.")
                         if approved_qty > item.quantity_requested:
                             raise serializers.ValidationError(f"Kuantitas disetujui ({approved_qty}) untuk {item.variant.name} tidak boleh melebihi yang diminta ({item.quantity_requested}).")
                         item.quantity_approved_spv2 = approved_qty
                         item.save(update_fields=['quantity_approved_spv2'])
                    else:
                         # Jika item tidak ada di data approval, setujui 0 atau sesuai permintaan?
                         # Asumsi: jika tidak disebut, berarti tidak disetujui (0)
                         item.quantity_approved_spv2 = 0
                         item.save(update_fields=['quantity_approved_spv2'])

                self._add_log(req, request.user, "APPROVE_SPV2", status_from=Request.Status.APPROVED_SPV1, status_to=Request.Status.APPROVED_SPV2)

        except serializers.ValidationError as e:
             return Response({"error": e.detail}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
             # Handle generic exceptions during transaction
             return Response({"error": f"Terjadi kesalahan internal: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


        serializer = self.get_serializer(req)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[CanApproveRequestSpv2])
    def reject_spv2(self, request, pk=None):
        """Aksi Atasan Operator untuk menolak."""
        req = self.get_object()
        comment = request.data.get('comment', None)
        if not comment:
            return Response({"comment": ["Komentar penolakan wajib diisi."]}, status=status.HTTP_400_BAD_REQUEST)
        if req.status != Request.Status.APPROVED_SPV1:
            return Response({"error": "Hanya request APPROVED_SPV1 yang bisa ditolak SPV2."}, status=status.HTTP_400_BAD_REQUEST)

        req.status = Request.Status.REJECTED_SPV2
        req.supervisor2_approver = request.user
        req.supervisor2_decision_at = timezone.now()
        req.supervisor2_rejection_reason = comment
        req.save(update_fields=['status', 'supervisor2_approver', 'supervisor2_decision_at', 'supervisor2_rejection_reason'])
        self._add_log(req, request.user, "REJECT_SPV2", comment=comment, status_from=Request.Status.APPROVED_SPV1, status_to=Request.Status.REJECTED_SPV2)
        # Request dikembalikan ke Atasan Peminta? Atau langsung ke Peminta? Sesuai alur: ke Atasan Peminta
        serializer = self.get_serializer(req)
        return Response(serializer.data)


    @action(detail=True, methods=['post'], permission_classes=[CanProcessRequestOperator])
    @transaction.atomic # Pastikan semua operasi DB (kurangi stok, buat SPMB, dll) berhasil atau gagal bersamaan
    def process(self, request, pk=None):
        """Aksi Operator untuk memproses barang keluar (FIFO)."""
        req = self.get_object()
        if req.status != Request.Status.APPROVED_SPV2:
            return Response({"error": "Hanya request APPROVED_SPV2 yang bisa diproses."}, status=status.HTTP_400_BAD_REQUEST)

        items_to_issue = req.items.filter(quantity_approved_spv2__gt=0) # Item yg disetujui > 0
        if not items_to_issue.exists():
             # Jika tidak ada item yg disetujui, langsung selesaikan? Atau tolak?
             req.status = Request.Status.COMPLETED # Anggap selesai tanpa barang keluar
             req.operator_processor = request.user
             req.operator_processed_at = timezone.now()
             req.save(update_fields=['status', 'operator_processor', 'operator_processed_at'])
             self._add_log(req, request.user, "PROCESS_COMPLETE_NO_ITEMS", status_from=Request.Status.APPROVED_SPV2, status_to=Request.Status.COMPLETED)
             return Response({"message": "Tidak ada item yang disetujui untuk dikeluarkan, request ditandai selesai."}, status=status.HTTP_200_OK)

        # --- Logika FIFO & Pengurangan Stok ---
        transactions_to_create = []
        spmb = None

        for item in items_to_issue:
            variant = item.variant
            qty_to_issue = item.quantity_approved_spv2 # Jumlah yg HARUS dikeluarkan
            qty_issued_so_far = 0

            # Ambil batch inventaris TERLAMA yg masih punya stok untuk varian ini
            inventory_batches = InventoryItem.objects.select_for_update().filter(
                variant=variant,
                quantity__gt=0
            ).order_by('entry_date', 'id') # FIFO order

            if not inventory_batches.exists():
                # Stok habis! Tidak bisa proses.
                # Kembalikan transaksi & raise error
                raise serializers.ValidationError(f"Stok habis untuk barang '{variant.name}'. Proses dibatalkan.")

            # Iterasi per batch untuk memenuhi kuantitas
            for batch in inventory_batches:
                take_from_batch = min(qty_to_issue - qty_issued_so_far, batch.quantity)

                if take_from_batch > 0:
                    # Kurangi stok batch
                    batch.quantity -= take_from_batch
                    batch.save(update_fields=['quantity'])

                    # Kurangi stok total
                    stock = Stock.objects.select_for_update().get(variant=variant)
                    stock.total_quantity -= take_from_batch
                    stock.save(update_fields=['total_quantity'])

                    # Siapkan data transaksi OUT
                    transactions_to_create.append(Transaction(
                        variant=variant,
                        inventory_item=batch, # Catat batch sumbernya
                        quantity=-take_from_batch, # Negatif untuk OUT
                        transaction_type=Transaction.Type.OUT,
                        user=request.user,
                        related_request=req,
                        # spmb akan diisi setelah dibuat
                        notes=f"Pengeluaran untuk Request #{req.id}"
                    ))

                    qty_issued_so_far += take_from_batch

                if qty_issued_so_far >= qty_to_issue:
                    break # Kebutuhan item ini sudah terpenuhi

            # Setelah iterasi batch, cek apakah kuantitas terpenuhi
            if qty_issued_so_far < qty_to_issue:
                 # Stok tidak cukup dari semua batch yang ada! Rollback transaksi.
                 raise serializers.ValidationError(f"Stok tidak mencukupi untuk '{variant.name}'. Diminta {qty_to_issue}, tersedia {qty_issued_so_far}. Proses dibatalkan.")

            # Catat jumlah yg berhasil dikeluarkan di RequestItem
            item.quantity_issued = qty_issued_so_far
            item.save(update_fields=['quantity_issued'])
        # --- Akhir Logika FIFO ---

        # Jika semua item berhasil diproses stoknya:
        # Buat SPMB
        spmb = SPMB.objects.create(
            request=req,
            issued_by=request.user
            # Nomor SPMB akan di-generate otomatis oleh model save()
        )

        # Update status Request
        req.status = Request.Status.COMPLETED # Selesai diproses, tunggu konfirmasi terima
        req.operator_processor = request.user
        req.operator_processed_at = timezone.now()
        req.save(update_fields=['status', 'operator_processor', 'operator_processed_at'])

        # Bulk create transactions (setelah SPMB ada)
        for t in transactions_to_create:
             t.related_spmb = spmb # Assign SPMB ke transaksi
        Transaction.objects.bulk_create(transactions_to_create)

        # Log
        self._add_log(req, request.user, "PROCESS_COMPLETE", status_from=Request.Status.APPROVED_SPV2, status_to=Request.Status.COMPLETED)

        # Return data request yang sudah diupdate + info SPMB
        serializer = self.get_serializer(req)
        # Mungkin tambahkan info SPMB ke response?
        response_data = serializer.data
        response_data['spmb_info'] = SPMBSerializer(spmb).data # Sertakan detail SPMB
        return Response(response_data)


    @action(detail=True, methods=['post'], permission_classes=[CanProcessRequestOperator])
    def reject_opr(self, request, pk=None):
         """Aksi Operator menolak memproses (misal stok rusak)."""
         req = self.get_object()
         comment = request.data.get('comment', None)
         if not comment:
             return Response({"comment": ["Komentar penolakan wajib diisi."]}, status=status.HTTP_400_BAD_REQUEST)
         if req.status != Request.Status.APPROVED_SPV2:
             return Response({"error": "Hanya request APPROVED_SPV2 yang bisa ditolak oleh Operator."}, status=status.HTTP_400_BAD_REQUEST)

         req.status = Request.Status.REJECTED_OPR
         req.operator_processor = request.user
         req.operator_processed_at = timezone.now() # Waktu penolakan
         req.operator_rejection_reason = comment
         req.save(update_fields=['status', 'operator_processor', 'operator_processed_at', 'operator_rejection_reason'])
         self._add_log(req, request.user, "REJECT_OPR", comment=comment, status_from=Request.Status.APPROVED_SPV2, status_to=Request.Status.REJECTED_OPR)
         # Request dikembalikan ke? Mungkin Atasan Operator? Atau Peminta? Tergantung alur.
         serializer = self.get_serializer(req)
         return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsOwnerOfRequest])
    def receive(self, request, pk=None):
        """Aksi Peminta untuk konfirmasi penerimaan barang."""
        req = self.get_object()
        if req.status != Request.Status.COMPLETED:
             return Response({"error": "Hanya request COMPLETED yang bisa dikonfirmasi penerimaannya."}, status=status.HTTP_400_BAD_REQUEST)

        req.status = Request.Status.RECEIVED
        req.received_at = timezone.now()
        req.save(update_fields=['status', 'received_at'])
        self._add_log(req, request.user, "RECEIVE_CONFIRM", status_from=Request.Status.COMPLETED, status_to=Request.Status.RECEIVED)
        serializer = self.get_serializer(req)
        return Response(serializer.data)


# --- Views Lain (SPMB, Log, Transaksi) ---
class SPMBViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SPMB.objects.select_related('request__requester', 'issued_by').all()
    serializer_class = SPMBSerializer
    permission_classes = [permissions.IsAuthenticated] # Sesuaikan lagi siapa yg boleh lihat detail SPMB

    def get_queryset(self):
         # Filter berdasarkan user? Admin lihat semua, Operator lihat yg dia buat, dll.
         user = self.request.user
         if user.is_admin or user.is_atasan_operator: # Contoh: Admin/Atasan Ops lihat semua
              return super().get_queryset()
         if user.is_operator:
              return super().get_queryset().filter(issued_by=user)
         if user.is_peminta:
              # Peminta lihat SPMB dari request miliknya
              return super().get_queryset().filter(request__requester=user)
         # TODO: Handle Atasan Peminta?
         return super().get_queryset().none()

class RequestLogViewSet(viewsets.ReadOnlyModelViewSet):
     queryset = RequestLog.objects.select_related('request', 'user').all()
     serializer_class = RequestLogSerializer
     permission_classes = [IsAdminUser] # Sementara hanya Admin yg bisa lihat semua log

class TransactionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Transaction.objects.select_related('variant', 'user', 'inventory_item', 'related_request', 'related_spmb').all()
    serializer_class = TransactionSerializer
    permission_classes = [IsAdminUser | IsOperator] # Hanya Admin/Operator lihat transaksi stok

# --- Views Stock Opname ---
class StockOpnameSessionViewSet(viewsets.ModelViewSet):
     queryset = StockOpnameSession.objects.select_related('created_by').all()
     serializer_class = StockOpnameSessionSerializer
     permission_classes = [IsAdminUser] # Hanya Admin yg bisa kelola sesi opname

     @action(detail=False, methods=['post'], serializer_class=StockOpnameFileUploadSerializer)
     def upload_opname(self, request):
         """Admin mengunggah file Excel hasil stock opname."""
         upload_serializer = StockOpnameFileUploadSerializer(data=request.data)
         if not upload_serializer.is_valid():
             return Response(upload_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

         validated_data = upload_serializer.validated_data
         file = validated_data['file']
         opname_date = validated_data['opname_date']
         notes = validated_data.get('notes')

         try:
             # Baca file Excel (contoh sederhana, perlu disesuaikan dengan format Excel Anda)
             # Asumsi format: Kolom A = Nama Varian (atau ID Varian), Kolom B = Jumlah Hitung Fisik
             # Anda mungkin perlu library 'pandas' atau 'openpyxl'
             # pip install pandas openpyxl
             try:
                 # df = pd.read_excel(file, engine='openpyxl') # Gunakan pandas jika nyaman
                 # Alternatif pakai openpyxl langsung
                 workbook = openpyxl.load_workbook(file, read_only=True)
                 sheet = workbook.active
             except Exception as e:
                  return Response({"error": f"Gagal membaca file Excel: {e}"}, status=status.HTTP_400_BAD_REQUEST)

             opname_items_to_create = []
             processed_variants = set()

             with transaction.atomic():
                 # Buat sesi opname dulu
                 session = StockOpnameSession.objects.create(
                     opname_date=opname_date,
                     uploaded_file=file, # Simpan file asli jika perlu
                     created_by=request.user,
                     notes=notes
                     # Status default PENDING_CONFIRMATION
                 )

                 # Iterasi baris Excel (skip header jika ada, misal dari baris 2)
                 # for index, row in df.iterrows(): # Jika pakai pandas
                 for row in sheet.iter_rows(min_row=2, values_only=True): # Jika pakai openpyxl
                     if not row or len(row) < 2 or row[0] is None or row[1] is None:
                          continue # Skip baris kosong

                     variant_identifier = str(row[0]).strip() # Bisa ID atau Nama Varian
                     try:
                          counted_quantity = int(row[1])
                          if counted_quantity < 0: raise ValueError("Kuantitas tidak boleh negatif")
                     except (ValueError, TypeError):
                          # Rollback dan beri error jika kuantitas tidak valid
                          raise serializers.ValidationError(f"Kuantitas tidak valid '{row[1]}' untuk varian '{variant_identifier}' di baris {sheet.max_row}. Proses dibatalkan.") # Perlu nomor baris yg benar

                     # Cari variant berdasarkan ID atau Nama
                     try:
                          # Coba cari berdasarkan ID dulu jika identifier adalah angka
                          if variant_identifier.isdigit():
                               variant = ProductVariant.objects.get(pk=int(variant_identifier))
                          else:
                               # Cari berdasarkan nama (asumsi unik atau kombinasi kategori+nama unik)
                               # Ini bisa ambigu jika nama tidak unik, ID lebih baik
                               variant = ProductVariant.objects.get(name__iexact=variant_identifier) # case-insensitive exact match
                     except ProductVariant.DoesNotExist:
                          # Rollback dan beri error jika varian tidak ditemukan
                          raise serializers.ValidationError(f"Varian '{variant_identifier}' tidak ditemukan di database. Proses dibatalkan.")
                     except ProductVariant.MultipleObjectsReturned:
                           raise serializers.ValidationError(f"Nama varian '{variant_identifier}' tidak unik. Gunakan ID Varian. Proses dibatalkan.")

                     if variant.id in processed_variants:
                          raise serializers.ValidationError(f"Varian '{variant.name}' muncul lebih dari sekali di file Excel. Proses dibatalkan.")
                     processed_variants.add(variant.id)

                     # Dapatkan jumlah sistem saat ini
                     stock = Stock.objects.filter(variant=variant).first()
                     system_quantity = stock.total_quantity if stock else 0

                     difference_value = counted_quantity - system_quantity

                     opname_items_to_create.append(
                         StockOpnameItem(
                             opname_session=session,
                             variant=variant,
                             system_quantity=system_quantity,
                             counted_quantity=counted_quantity,
                             difference=difference_value,
                             # difference, confirmation_status dihitung/default otomatis
                         )
                     )

                 # Bulk create item opname
                 StockOpnameItem.objects.bulk_create(opname_items_to_create)

         except serializers.ValidationError as e:
              # Hapus sesi opname jika terjadi error validasi data Excel
              if 'session' in locals() and session.pk: session.delete()
              return Response({"error": e.detail}, status=status.HTTP_400_BAD_REQUEST)
         except Exception as e:
              # Handle error tak terduga lainnya
              if 'session' in locals() and session.pk: session.delete()
              return Response({"error": f"Terjadi kesalahan internal saat memproses file: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

         # Berhasil, kembalikan data sesi yg baru dibuat
         response_serializer = StockOpnameSessionSerializer(session, context={'request': request})
         return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class StockOpnameItemViewSet(viewsets.ModelViewSet):
    queryset = StockOpnameItem.objects.select_related('opname_session', 'variant', 'confirmed_by').all()
    serializer_class = StockOpnameItemSerializer
    # Permission: Operator bisa lihat & konfirmasi, Admin bisa lihat semua
    # Filtering berdasarkan sesi akan dilakukan di frontend atau parameter query

    def get_permissions(self):
        if self.action == 'confirm':
            self.permission_classes = [IsOperator] # Hanya Operator/Admin yg bisa konfirmasi
        else:
            # Read access untuk Operator/Admin
            self.permission_classes = [IsOperator | IsAdminUser]
        return super().get_permissions()

    @action(detail=True, methods=['post'], serializer_class=StockOpnameConfirmSerializer)
    @transaction.atomic
    def confirm(self, request, pk=None):
         """Operator mengkonfirmasi perbedaan stock opname."""
         item = self.get_object()
         if item.confirmation_status != StockOpnameItem.ConfirmationStatus.PENDING:
             return Response({"error": "Item ini sudah dikonfirmasi sebelumnya."}, status=status.HTTP_400_BAD_REQUEST)

         confirm_serializer = StockOpnameConfirmSerializer(data=request.data)
         if not confirm_serializer.is_valid():
             return Response(confirm_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

         validated_data = confirm_serializer.validated_data
         new_status = validated_data['confirmation_status']
         notes = validated_data.get('confirmation_notes')

         # Update item opname
         item.confirmation_status = new_status
         item.confirmation_notes = notes
         item.confirmed_by = request.user
         item.confirmed_at = timezone.now()
         item.save()

         # Jika statusnya perlu penyesuaian stok
         if new_status == StockOpnameItem.ConfirmationStatus.CONFIRMED_ADJUST and item.difference != 0:
             # Lakukan penyesuaian stok
             stock, created = Stock.objects.select_for_update().get_or_create(variant=item.variant)
             original_stock = stock.total_quantity
             stock.total_quantity += item.difference # Tambah/kurang sesuai selisih
             stock.save()

             # Buat log transaksi penyesuaian
             Transaction.objects.create(
                 variant=item.variant,
                 quantity=item.difference, # Bisa positif atau negatif
                 transaction_type=Transaction.Type.ADJUSTMENT,
                 user=request.user,
                 notes=f"Penyesuaian Stock Opname Sesi #{item.opname_session.id}. Item Opname #{item.id}. Selisih: {item.difference}. Dari {original_stock} menjadi {stock.total_quantity}. Catatan: {notes or '-'}"
             )

         # TODO: Update status StockOpnameSession jika semua item sudah dikonfirmasi?
         # session = item.opname_session
         # if not session.items.filter(confirmation_status=StockOpnameItem.ConfirmationStatus.PENDING).exists():
         #      session.status = StockOpnameSession.Status.COMPLETED
         #      session.save(update_fields=['status'])

         serializer = self.get_serializer(item) # Return data item yg diupdate
         return Response(serializer.data)

# TODO: View untuk Dashboard (agregasi data)
class DashboardDataView(APIView):
     permission_classes = [permissions.IsAuthenticated] # Sesuaikan permission per data

     def get(self, request, *args, **kwargs):
         user = request.user
         data = {}

         # Contoh agregasi (perlu disesuaikan)
         if user.is_admin or user.is_operator or user.is_atasan_operator:
             data['total_variants'] = ProductVariant.objects.count()
             data['low_stock_items'] = StockSerializer(Stock.objects.filter(total_quantity__lte=F('low_stock_threshold')), many=True).data # Perlu import F
             data['pending_requests_spv2'] = Request.objects.filter(status=Request.Status.APPROVED_SPV1).count()
             data['pending_opname_confirmations'] = StockOpnameItem.objects.filter(confirmation_status=StockOpnameItem.ConfirmationStatus.PENDING).count()
             # Tambahkan grafik: Permintaan per unit/bulan, dll. (Query kompleks)

         if user.is_peminta:
             data['my_draft_requests'] = Request.objects.filter(requester=user, status=Request.Status.DRAFT).count()
             data['my_pending_requests'] = Request.objects.filter(requester=user, status__in=[Request.Status.SUBMITTED, Request.Status.APPROVED_SPV1]).count()

         # ... tambahkan data lain sesuai peran

         return Response(data)