// src/pages/ShoppingCartPage.jsx
import React, { useState, useContext } from 'react'; // Import useContext
import { useNavigate, Link } from 'react-router-dom'; // Import Link
// Import CartContext langsung untuk debug
import { useCart, CartContext } from '../contexts/CartContext';
import axiosInstance from '../api/axiosInstance';
import { useAuth } from '../contexts/AuthContext';

function ShoppingCartPage() {
  // --- DEBUGGING CONTEXT ---
  const cartContextValue = useContext(CartContext);
  console.log("Nilai CartContext di ShoppingCartPage:", cartContextValue);
  // --- AKHIR DEBUGGING ---

  // Coba ambil state/fungsi dari context dengan fallback
  const {
    cartItems = [], // Default ke array kosong
    itemCount = 0,  // Default ke 0
    removeFromCart,
    updateQuantity,
    clearCart
  } = useCart() || {}; // Beri fallback object kosong

  const { user } = useAuth();
  const navigate = useNavigate();

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);

  const handleQuantityChange = (variantId, newQuantity) => {
    // Pastikan updateQuantity adalah fungsi sebelum memanggil
    if (typeof updateQuantity !== 'function') {
        console.error("Fungsi updateQuantity tidak tersedia.");
        return;
    }
    const quantity = parseInt(newQuantity, 10);
    if (!isNaN(quantity) && quantity >= 0) {
      updateQuantity(variantId, quantity);
    } else if (newQuantity === '') {
        updateQuantity(variantId, 0);
    }
  };

  const handleRemoveItem = (variantId) => {
      if (typeof removeFromCart === 'function') {
          removeFromCart(variantId);
      } else {
           console.error("Fungsi removeFromCart tidak tersedia.");
      }
  }

  const handleClearCart = () => {
       if (typeof clearCart === 'function') {
           clearCart();
       } else {
            console.error("Fungsi clearCart tidak tersedia.");
       }
  }

  const handleSubmitRequest = async () => {
    if (!Array.isArray(cartItems) || cartItems.length === 0) {
      alert("Keranjang kosong. Silakan tambahkan barang terlebih dahulu.");
      return;
    }
    // Pastikan fungsi clearCart ada sebelum submit
    if (typeof clearCart !== 'function') {
        console.error("Fungsi clearCart tidak tersedia untuk submit.");
        alert("Terjadi kesalahan pada fungsi keranjang.");
        return;
    }

    setIsSubmitting(true);
    setSubmitError(null);
    console.log("Submitting request with items:", cartItems);

    const itemsForApi = cartItems.map(item => ({
        variant_id: item.variant.id,
        quantity_requested: item.quantity
    }));

    try {
        const response = await axiosInstance.post('/requests/', { items: itemsForApi });
        console.log("Request submitted successfully:", response.data);
        alert("Permintaan berhasil dibuat sebagai draft!");
        clearCart(); // Kosongkan keranjang
        navigate('/my-requests'); // Arahkan

    } catch (err) {
        console.error("Error submitting request:", err);
        const errMsg = err.response?.data?.detail || JSON.stringify(err.response?.data) || err.message || "Gagal mengajukan permintaan.";
        setSubmitError(errMsg);
        alert(`Gagal mengajukan permintaan: ${errMsg}`);
    } finally {
        setIsSubmitting(false);
    }
  };

  // Style sederhana
  const styles = {
    container: { padding: '20px' },
    table: { width: '100%', borderCollapse: 'collapse', marginTop: '20px', marginBottom: '20px' },
    th: { border: '1px solid #ddd', padding: '8px', textAlign: 'left', backgroundColor: '#f2f2f2' },
    td: { border: '1px solid #ddd', padding: '8px', verticalAlign: 'middle' },
    quantityInput: { width: '60px', padding: '5px', textAlign: 'center' },
    removeButton: { padding: '5px 10px', backgroundColor: '#dc3545', color: 'white', border: 'none', borderRadius: '3px', cursor: 'pointer', fontSize: '14px', marginLeft: '5px' },
    actionButtons: { marginTop: '20px', display: 'flex', justifyContent: 'space-between' },
    clearButton: { padding: '10px 15px', backgroundColor: '#ffc107', color: 'black', border: 'none', borderRadius: '3px', cursor: 'pointer', fontSize: '16px' },
    submitButton: { padding: '10px 15px', backgroundColor: '#007bff', color: 'white', border: 'none', borderRadius: '3px', cursor: 'pointer', fontSize: '16px' },
    error: { color: 'red', marginTop: '10px' },
  };

  // Jika context belum termuat (meskipun seharusnya cepat)
  if (cartContextValue === null) {
      return <div>Loading cart context...</div>;
  }

  return (
    <div style={styles.container}>
      <h2>Keranjang Permintaan Barang</h2>

      {!cartItems || cartItems.length === 0 ? ( // Cek cartItems sebelum akses length
        <p>Keranjang Anda kosong. Silakan <Link to="/items">pilih barang</Link>.</p>
      ) : (
        <>
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Kode Barang</th>
                <th style={styles.th}>Jenis & Nama Spesifik</th>
                <th style={styles.th}>Satuan</th>
                <th style={styles.th}>Jumlah Diminta</th>
                <th style={styles.th}>Aksi</th>
              </tr>
            </thead>
            <tbody>
              {cartItems.map((item) => (
                // Pastikan item dan item.variant ada sebelum akses propertinya
                item && item.variant && (
                  <tr key={item.variant.id}>
                    <td style={styles.td}>{item.variant.full_code || 'N/A'}</td>
                    <td style={styles.td}>{item.variant.type_name || ''} - {item.variant.variant_name || item.variant.name || 'N/A'}</td>
                    <td style={styles.td}>{item.variant.unit_of_measure || 'N/A'}</td>
                    <td style={styles.td}>
                      <input
                        type="number"
                        min="0"
                        value={item.quantity}
                        onChange={(e) => handleQuantityChange(item.variant.id, e.target.value)}
                        style={styles.quantityInput}
                        disabled={isSubmitting || typeof updateQuantity !== 'function'} // Disable jika fungsi tidak ada
                      />
                    </td>
                    <td style={styles.td}>
                      <button
                        onClick={() => handleRemoveItem(item.variant.id)}
                        style={styles.removeButton}
                        disabled={isSubmitting || typeof removeFromCart !== 'function'} // Disable jika fungsi tidak ada
                      >
                        Hapus
                      </button>
                    </td>
                  </tr>
                )
              ))}
            </tbody>
          </table>

          <div style={styles.actionButtons}>
            <button onClick={handleClearCart} style={styles.clearButton} disabled={isSubmitting || typeof clearCart !== 'function'}>
              Kosongkan Keranjang
            </button>
            <button onClick={handleSubmitRequest} style={styles.submitButton} disabled={isSubmitting || typeof clearCart !== 'function'}>
              {isSubmitting ? 'Mengajukan...' : 'Ajukan Permintaan (Draft)'}
            </button>
          </div>
          {submitError && <p style={styles.error}>Error: {submitError}</p>}
        </>
      )}
    </div>
  );
}

export default ShoppingCartPage;
