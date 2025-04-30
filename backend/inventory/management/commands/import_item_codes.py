# backend/inventory/management/commands/import_item_codes.py

import csv
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction, IntegrityError # Pastikan IntegrityError diimpor jika digunakan di model save
from inventory.models import ( # Impor model hierarki kode Anda
    ItemCodeGolongan, ItemCodeBidang, ItemCodeKelompok, ItemCodeSubKelompok, ItemCodeBarang
)
# from django.utils.text import slugify # Tidak terpakai, bisa dihapus

class Command(BaseCommand):
    help = 'Imports Item Classification Codes from a specified CSV file (delimiter specified in code)'

    def add_arguments(self, parser):
        # Tambahkan argumen untuk path file CSV
        parser.add_argument('csv_filepath', type=str, help='The full path to the CSV file')

    @transaction.atomic # Bungkus seluruh proses dalam satu transaksi database
    def handle(self, *args, **options):
        csv_filepath = Path(options['csv_filepath'])
        if not csv_filepath.is_file():
            raise CommandError(f"File not found at path: {csv_filepath}")

        self.stdout.write(f"Starting import from {csv_filepath}...")

        # Cache untuk menyimpan objek yg sudah dibuat agar tidak query berulang
        golongan_cache = {}
        bidang_cache = {}
        kelompok_cache = {}
        subkelompok_cache = {}

        items_created_count = 0
        items_updated_count = 0
        rows_processed = 0

        try:
            with open(csv_filepath, mode='r', encoding='utf-8-sig') as csvfile: # utf-8-sig untuk handle BOM jika ada
                # Gunakan delimiter titik koma (;) sesuai file Anda
                reader = csv.DictReader(csvfile, delimiter=';')

                for row in reader:
                    rows_processed += 1
                    print(f"\n--- Memproses Baris: {rows_processed + 1} ---") # DEBUG AWAL BARIS
                    golongan_obj = None # Inisialisasi untuk baris ini
                    bidang_obj = None
                    kelompok_obj = None
                    subkelompok_obj = None
                    barang_obj = None
                    created = False

                    try:
                        # Ambil data dari baris CSV, bersihkan spasi
                        kd_gol = row.get('kd_gol', '').strip()
                        kdbid = row.get('kdbid', '').strip()
                        kdkel = row.get('kdkel', '').strip()
                        kdskel = row.get('kdskel', '').strip()
                        kd_brg = row.get('kd_brg', '').strip()
                        ur_sskel = row.get('ur_sskel', '').strip() # Ini deskripsi dasar
                        kd_akun = row.get('kd_akun', '').strip() or None # Jadikan None jika kosong
                        ur_akun = row.get('ur_akun', '').strip() or None

                        # Validasi dasar (pastikan kode utama tidak kosong)
                        if not all([kd_gol, kdbid, kdkel, kdskel, kd_brg, ur_sskel]):
                            self.stderr.write(self.style.WARNING(f"Skipping row {rows_processed + 1}: Missing required code or description data."))
                            continue

                        print(f"DEBUG Baris {rows_processed + 1}: Data Parsed -> G:{kd_gol}, B:{kdbid}, K:{kdkel}, SK:{kdskel}, BRG:{kd_brg}") # DEBUG PARSING

                        # 1. Get or Create Golongan
                        golongan_obj = golongan_cache.get(kd_gol)
                        if not golongan_obj:
                            golongan_obj, created = ItemCodeGolongan.objects.get_or_create(
                                code=kd_gol,
                                defaults={'description': None} # Placeholder deskripsi
                            )
                            golongan_cache[kd_gol] = golongan_obj
                            # if created: self.stdout.write(f"  Created Golongan: {kd_gol}") # Kurangi verbosity

                        # 2. Get or Create Bidang
                        bidang_key = (golongan_obj.id, kdbid)
                        bidang_obj = bidang_cache.get(bidang_key)
                        if not bidang_obj:
                            bidang_obj, created = ItemCodeBidang.objects.get_or_create(
                                golongan=golongan_obj,
                                code=kdbid,
                                defaults={'description': None}
                            )
                            bidang_cache[bidang_key] = bidang_obj
                            # if created: self.stdout.write(f"  Created Bidang: {golongan_obj.code}.{kdbid}")

                        # 3. Get or Create Kelompok
                        kelompok_key = (bidang_obj.id, kdkel)
                        kelompok_obj = kelompok_cache.get(kelompok_key)
                        if not kelompok_obj:
                            kelompok_obj, created = ItemCodeKelompok.objects.get_or_create(
                                bidang=bidang_obj,
                                code=kdkel,
                                defaults={'description': None}
                            )
                            kelompok_cache[kelompok_key] = kelompok_obj
                            # if created: self.stdout.write(f"  Created Kelompok: {bidang_obj}.{kdkel}")

                        # 4. Get or Create SubKelompok
                        subkelompok_key = (kelompok_obj.id, kdskel)
                        subkelompok_obj = subkelompok_cache.get(subkelompok_key)
                        if not subkelompok_obj:
                            subkelompok_obj, created = ItemCodeSubKelompok.objects.get_or_create(
                                kelompok=kelompok_obj,
                                code=kdskel,
                                # Gunakan ur_sskel sebagai deskripsi dasar SubKelompok
                                defaults={'base_description': ur_sskel}
                            )
                            subkelompok_cache[subkelompok_key] = subkelompok_obj
                            # if created: self.stdout.write(f"  Created SubKelompok: {kelompok_obj}.{kdskel} - {ur_sskel[:30]}...")


                        # --- DEBUG SEBELUM ItemCodeBarang ---
                        print(f"DEBUG Baris {rows_processed + 1}: Mencari/membuat ItemCodeBarang dengan subkel_id={getattr(subkelompok_obj, 'id', 'None')}, code={kd_brg}")
                        barang_defaults = {
                            'base_description': ur_sskel, # ur_sskel sepertinya deskripsi barang dasar
                            'account_code': kd_akun,
                            'account_description': ur_akun
                        }
                        print(f"DEBUG Baris {rows_processed + 1}: Defaults: {barang_defaults}")
                        # --- AKHIR DEBUG ---

                        # 5. Get or Create ItemCodeBarang (Barang Dasar)
                        barang_obj, created = ItemCodeBarang.objects.update_or_create(
                            sub_kelompok=subkelompok_obj,
                            code=kd_brg,
                            defaults=barang_defaults
                        )

                        # --- DEBUG SETELAH ItemCodeBarang ---
                        # Coba akses full_base_code SETELAH objek disimpan/diupdate
                        # Perlu refresh_from_db jika ingin lihat nilai yg di-generate save()
                        # barang_obj.refresh_from_db() # Uncomment jika perlu lihat kode yg baru di-generate
                        print(f"DEBUG Baris {rows_processed + 1}: update_or_create selesai. Created={created}. Obj ID={getattr(barang_obj, 'id', 'None')}. Obj full_code={getattr(barang_obj, 'full_base_code', 'N/A')}")
                        # --- AKHIR DEBUG ---

                        if created:
                            items_created_count += 1
                        else:
                            items_updated_count += 1

                    except Exception as e_row:
                        # Log error per baris
                        self.stderr.write(self.style.ERROR(f"Error processing row {rows_processed + 1}: {type(e_row).__name__}: {e_row} - Data: {row}"))
                        # Jika ingin berhenti total saat ada error baris, raise CommandError di sini
                        # raise CommandError(f"Failed processing row {rows_processed + 1}")

        except FileNotFoundError:
            raise CommandError(f"File not found at path: {csv_filepath}")
        except Exception as e:
            # Tangkap error umum lainnya
            import traceback
            self.stderr.write(self.style.ERROR(f"An unexpected error occurred during import: {e}"))
            traceback.print_exc() # Cetak traceback lengkap
            raise CommandError(f"Import failed due to an unexpected error.")

        self.stdout.write(self.style.SUCCESS(f"Import finished. Processed {rows_processed} rows."))
        self.stdout.write(self.style.SUCCESS(f"Created {items_created_count} new base items, Updated {items_updated_count} existing base items."))

