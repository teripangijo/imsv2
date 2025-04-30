// src/pages/ItemListingsPage.jsx
import React, { useState, useEffect, useContext } from 'react';
import { Link } from 'react-router-dom'; // 1. Import Link
import axiosInstance from '../api/axiosInstance';
import { useAuth } from '../contexts/AuthContext';
// Import CartContext secara langsung untuk debug (bisa dihapus jika sudah OK)
import { useCart, CartContext } from '../contexts/CartContext';

function ItemListingsPage() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const { user } = useAuth();

  // Ambil context cart
  const cartContextValue = useContext(CartContext);
  console.log("Nilai CartContext di ItemListingsPage:", cartContextValue);

  // Ambil fungsi dan state dari context cart
  const { addToCart, itemCount } = useCart() || {}; // Beri fallback

  useEffect(() => {
    const fetchStockLevels = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await axiosInstance.get('/stock-levels/');
        console.log("Stock Levels Response:", response.data);
        if (response.data && Array.isArray(response.data.results)) {
             setItems(response.data.results);
        } else {
             console.error("Format data stok tidak sesuai:", response.data);
             setItems([]);
             setError("Gagal memuat data stok: format tidak dikenal.");
        }
      } catch (err) {
        console.error("Error fetching stock levels:", err);
        setError(err.response?.data?.detail || err.message || "Gagal memuat daftar barang.");
        setItems([]);
      } finally {
        setLoading(false);
      }
    };
    fetchStockLevels();
  }, []);

  const handleAddToCart = (variant) => {
    if (typeof addToCart === 'function') {
        if (variant && typeof variant.id !== 'undefined') {
            addToCart(variant, 1);
            alert(`${variant.variant_name || variant.name || 'Barang'} ditambahkan ke keranjang!`);
        } else {
            console.error("Gagal menambah ke keranjang: data varian tidak valid", variant);
            alert("Gagal menambahkan barang ke keranjang.");
        }
    } else {
         console.error("Fungsi addToCart tidak tersedia dari context.");
         alert("Gagal menambahkan ke keranjang: fungsi tidak tersedia.");
    }
  };

  // Style sederhana
  const styles = {
    container: { padding: '20px' },
    table: { width: '100%', borderCollapse: 'collapse', marginTop: '20px' },
    th: { border: '1px solid #ddd', padding: '8px', textAlign: 'left', backgroundColor: '#f2f2f2' },
    td: { border: '1px solid #ddd', padding: '8px' },
    outOfStock: { color: '#999', fontStyle: 'italic' },
    loading: { textAlign: 'center', padding: '20px', fontSize: '1.2em' },
    error: { color: 'red', textAlign: 'center', padding: '20px' },
    addButton: { marginLeft: '10px', padding: '5px 10px', cursor: 'pointer', backgroundColor: '#28a745', color: 'white', border: 'none', borderRadius: '3px' },
    cartLink: { display: 'inline-block', marginTop: '15px', padding: '10px 15px', backgroundColor: '#17a2b8', color: 'white', textDecoration: 'none', borderRadius: '3px' } // Style untuk link keranjang
  };

  if (loading) {
    return <div style={styles.loading}>Memuat daftar barang...</div>;
  }

  if (error) {
    return <div style={styles.error}>Error: {error}</div>;
  }

  return (
    <div style={styles.container}>
      <h2>Daftar Barang Persediaan</h2>
      <p>Pilih barang yang ingin Anda minta.</p>

      {/* Link ke Keranjang */}
      <Link to="/cart" style={styles.cartLink}>
        Lihat Keranjang ({itemCount || 0}) {/* Tampilkan jumlah item */}
      </Link>

      {/* TODO: Tambahkan fitur search/filter di sini nanti */}

      <table style={styles.table}>
        <thead>
          <tr>
            <th style={styles.th}>Kode Barang</th>
            <th style={styles.th}>Jenis Barang</th>
            <th style={styles.th}>Nama Spesifik (Merk/Tipe)</th>
            <th style={styles.th}>Satuan</th>
            <th style={styles.th}>Stok Tersedia</th>
            <th style={styles.th}>Aksi</th>
          </tr>
        </thead>
        <tbody>
          {items.length === 0 ? (
            <tr>
              <td colSpan="6" style={{ textAlign: 'center', padding: '20px' }}>
                Tidak ada data barang tersedia.
              </td>
            </tr>
          ) : (
            items.map((stockItem) => {
              const isOutOfStock = stockItem.total_quantity <= 0;
              const rowStyle = isOutOfStock ? styles.outOfStock : {};
              const variantData = stockItem.variant || {};

              return (
                <tr key={variantData.id || `stock-${stockItem.variant_id}`} style={rowStyle}>
                  <td style={styles.td}>{variantData.full_code || 'N/A'}</td>
                  <td style={styles.td}>{variantData.type_name || 'N/A'}</td>
                  <td style={styles.td}>{variantData.variant_name || variantData.name || 'N/A'}</td>
                  <td style={styles.td}>{variantData.unit_of_measure || 'N/A'}</td>
                  <td style={styles.td}>{stockItem.total_quantity}</td>
                  <td style={styles.td}>
                    {!isOutOfStock && variantData.id && (
                       <button
                         style={styles.addButton}
                         onClick={() => handleAddToCart(variantData)}
                         disabled={!addToCart}
                       >
                         + Keranjang
                       </button>
                    )}
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}

export default ItemListingsPage;
