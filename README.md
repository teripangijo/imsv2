# Inventory Management System

Aplikasi berbasis web untuk manajemen dan pencatatan barang persediaan (inventory) dengan alur kerja permintaan dan persetujuan yang terstruktur.

**Teknologi Utama:**

* **Backend:** Python, Django, Django REST Framework
* **Frontend:** React (direncanakan)
* **Database:** PostgreSQL

## Deskripsi

Sistem ini dirancang untuk mengelola siklus hidup barang persediaan, mulai dari pencatatan barang masuk berdasarkan pembelian, pengelolaan stok dengan metode FIFO, proses permintaan barang oleh unit pengguna, alur persetujuan berjenjang, hingga pelaporan dan analisis data persediaan. Aplikasi ini menerapkan kontrol akses berbasis peran untuk memastikan setiap pengguna hanya dapat mengakses fitur sesuai wewenangnya.

## Fitur Backend (Sudah Diimplementasikan/Dirancang)

Berikut adalah fitur-fitur utama yang telah dirancang dan sebagian diimplementasikan pada sisi backend API:

**1. Manajemen Pengguna & Akses:**
    * **Otentikasi:** Login/Logout berbasis Token (DRF Authtoken).
    * **Manajemen Password:** Fitur ganti password dan wajib ganti password saat login pertama.
    * **Peran Pengguna (Roles):**
        * Peminta Barang
        * Atasan Peminta Barang
        * Operator Persediaan
        * Atasan Operator Persediaan
        * Administrator
    * **Hak Akses (Permissions):** Kontrol akses berbasis peran untuk setiap endpoint API dan aksi.

**2. Klasifikasi & Manajemen Barang:**
    * **Hierarki Kodefikasi:** Pengelolaan kode barang secara hierarkis (Golongan -> Bidang -> Kelompok -> Sub-Kelompok -> Barang Dasar).
        * Impor data kode barang dasar dari file CSV via management command.
        * Penyimpanan deskripsi (placeholder) untuk setiap level hierarki.
    * **Varian Produk Spesifik:**
        * Pencatatan detail barang spesifik (Jenis, Merk/Tipe, Satuan).
        * Pembuatan otomatis kode spesifik 3 digit unik per barang dasar.
        * Pembuatan otomatis kode lengkap unik per varian.
        * Kemampuan mencari/membuat varian baru secara dinamis saat input pembelian.

**3. Manajemen Stok & Inventaris:**
    * **Pencatatan Barang Masuk:**
        * Input manual data pembelian (via API endpoint `InventoryItem`).
        * Upload massal data pembelian dari file Excel/CSV (via API endpoint `upload_receipt`).
    * **Manajemen Kuitansi (`Receipt`):** Pencatatan informasi kuitansi pembelian dan menghubungkannya ke item inventaris.
    * **Pelacakan Batch (`InventoryItem`):** Setiap barang masuk dicatat sebagai batch terpisah dengan harga beli dan tanggal masuknya.
    * **Metode FIFO:** Pengeluaran barang otomatis mengambil dari batch terlama yang masih tersedia.
    * **Level Stok (`Stock`):** Pembaruan otomatis jumlah total stok per varian setiap ada barang masuk/keluar/disesuaikan.
    * **Ambang Batas Stok Rendah:** Pengaturan batas minimum per varian.

**4. Alur Kerja Permintaan Barang:**
    * **Pembuatan Draft:** Peminta membuat draft permintaan.
    * **Pengajuan:** Peminta mengajukan draft, nomor permintaan otomatis ter-generate.
    * **Persetujuan Atasan Peminta (SPV1):** Approve/Reject dengan komentar.
    * **Persetujuan Atasan Operator (SPV2):** Approve (dengan penyesuaian kuantitas per item)/Reject dengan komentar.
    * **Pemrosesan Operator:**
        * Memproses barang keluar berdasarkan persetujuan SPV2 dan stok (FIFO).
        * Generate otomatis nomor Surat Perintah Mengeluarkan Barang (SPMB).
        * Menolak pemrosesan dengan komentar.
    * **Konfirmasi Penerimaan:** Peminta melakukan konfirmasi setelah barang diterima.
    * **Logging:** Pencatatan otomatis setiap langkah dan perubahan status permintaan (`RequestLog`).

**5. Transaksi & Pelaporan:**
    * **Log Transaksi (`Transaction`):** Pencatatan otomatis setiap pergerakan stok (IN, OUT, ADJUSTMENT) beserta detail user, barang, kuantitas, dan referensi (Request/SPMB/Receipt).
    * **API Laporan (Read-Only):**
        * Laporan Stok Terkini (dengan filter & search).
        * Laporan Nilai Stok (berdasarkan perhitungan FIFO).
        * Laporan Stok Minimum (Alert).
        * Laporan Barang Slow/Fast Moving (berdasarkan transaksi keluar per periode).
        * Laporan Histori Transaksi (dengan filter tanggal, tipe, varian & search).
        * Laporan Konsumsi per Unit Peminta (dengan filter tanggal & departemen).
    * **Ekspor Data (CSV):** Kemampuan ekspor untuk Laporan Stok Terkini dan Laporan Histori Transaksi.

**6. Stock Opname:**
    * Pembuatan Sesi Opname oleh Admin.
    * Upload hasil perhitungan fisik dari file Excel oleh Admin.
    * Pencatatan otomatis selisih antara sistem dan fisik (`StockOpnameItem`).
    * Konfirmasi hasil opname oleh Operator (Match, Adjust, Reject).
    * Penyesuaian otomatis stok dan pencatatan transaksi jika Operator memilih 'Adjust'.

## TODO / Pengembangan Selanjutnya

* Implementasi Frontend React.
* Implementasi fitur laporan dan ekspor yang tersisa di backend.
* Penambahan fitur dashboard visual.
* Unit testing dan integration testing.
* Deployment.
* Pengisian deskripsi hierarki kode barang.
* Ekspor PDF (jika diperlukan).


