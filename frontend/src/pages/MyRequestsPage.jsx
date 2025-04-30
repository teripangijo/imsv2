// src/pages/MyRequestsPage.jsx
import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom'; // Import useNavigate
import axiosInstance from '../api/axiosInstance';
import { useAuth } from '../contexts/AuthContext';

function MyRequestsPage() {
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const { user } = useAuth();
  const navigate = useNavigate(); // Hook untuk navigasi

  // Fungsi untuk mengambil data permintaan
  const fetchMyRequests = async () => {
    if (!user) {
      // Jika user belum ada, tunggu atau tampilkan pesan
      // Mungkin perlu state loading terpisah untuk user vs data
      // Untuk sekarang, anggap user sudah ada jika halaman ini bisa diakses
      // setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await axiosInstance.get('/requests/');
      console.log("My Requests Response:", response.data);
      if (response.data && Array.isArray(response.data.results)) {
        setRequests(response.data.results);
      } else {
        setRequests([]);
        setError("Gagal memuat data permintaan: format tidak dikenal.");
      }
    } catch (err) {
      console.error("Error fetching my requests:", err);
      setError(err.response?.data?.detail || err.message || "Gagal memuat daftar permintaan.");
      setRequests([]);
    } finally {
      setLoading(false);
    }
  };

  // Fetch data saat komponen mount atau user berubah
  useEffect(() => {
    fetchMyRequests();
  }, [user]);

  // --- FUNGSI BARU UNTUK MENGAJUKAN DRAFT ---
  const handleSubmitDraft = async (requestId) => {
      if (!confirm(`Apakah Anda yakin ingin mengajukan permintaan ID ${requestId}?`)) {
          return;
      }
      // Set loading spesifik untuk tombol ini jika perlu
      // setSubmittingId(requestId);
      try {
          // Panggil API untuk submit draft
          const response = await axiosInstance.post(`/requests/${requestId}/submit/`);
          console.log(`Request ${requestId} submitted:`, response.data);
          alert(`Permintaan ${response.data.request_number || requestId} berhasil diajukan.`);
          // Refresh daftar permintaan untuk melihat status terbaru
          fetchMyRequests();
      } catch (err) {
          console.error(`Error submitting request ${requestId}:`, err);
          alert(`Gagal mengajukan permintaan: ${err.response?.data?.error || err.message}`);
      } finally {
          // setSubmittingId(null);
      }
  };
  // --- AKHIR FUNGSI BARU ---

  // --- FUNGSI BARU UNTUK KONFIRMASI TERIMA ---
  const handleReceiveItems = async (requestId) => {
      if (!confirm(`Apakah Anda yakin ingin konfirmasi penerimaan barang untuk permintaan ID ${requestId}?`)) {
          return;
      }
      // Set loading spesifik jika perlu
      try {
          // Panggil API untuk konfirmasi terima
          const response = await axiosInstance.post(`/requests/${requestId}/receive/`);
          console.log(`Request ${requestId} received:`, response.data);
          alert(`Konfirmasi penerimaan untuk ${response.data.request_number || requestId} berhasil.`);
          // Refresh daftar permintaan
          fetchMyRequests();
      } catch (err) {
          console.error(`Error confirming receipt for request ${requestId}:`, err);
          alert(`Gagal konfirmasi penerimaan: ${err.response?.data?.error || err.message}`);
      } finally {
          // Reset loading spesifik
      }
  };
  // --- AKHIR FUNGSI BARU ---


  // Style sederhana
  const styles = {
    container: { padding: '20px' },
    table: { width: '100%', borderCollapse: 'collapse', marginTop: '20px' },
    th: { border: '1px solid #ddd', padding: '8px', textAlign: 'left', backgroundColor: '#f2f2f2' },
    td: { border: '1px solid #ddd', padding: '8px' },
    loading: { textAlign: 'center', padding: '20px', fontSize: '1.2em' },
    error: { color: 'red', textAlign: 'center', padding: '20px' },
    link: { textDecoration: 'none', color: '#007bff' },
    actionButton: { marginLeft: '10px', padding: '3px 8px', fontSize: '12px', cursor: 'pointer' }
  };

  if (loading) {
    return <div style={styles.loading}>Memuat daftar permintaan...</div>;
  }

  if (error) {
    return <div style={styles.error}>Error: {error}</div>;
  }

  return (
    <div style={styles.container}>
      <h2>Daftar Permintaan Barang Saya</h2>

      <table style={styles.table}>
        <thead>
          <tr>
            <th style={styles.th}>Nomor Permintaan</th>
            <th style={styles.th}>Tanggal Dibuat</th>
            <th style={styles.th}>Tanggal Diajukan</th>
            <th style={styles.th}>Status</th>
            <th style={styles.th}>Nomor SPMB</th>
            <th style={styles.th}>Aksi</th>
          </tr>
        </thead>
        <tbody>
          {requests.length === 0 ? (
            <tr>
              <td colSpan="6" style={{ textAlign: 'center', padding: '20px' }}>
                Anda belum membuat permintaan barang.
              </td>
            </tr>
          ) : (
            requests.map((req) => (
              <tr key={req.id}>
                <td style={styles.td}>{req.request_number || '(Draft)'}</td>
                <td style={styles.td}>{new Date(req.created_at).toLocaleDateString('id-ID')}</td>
                <td style={styles.td}>{req.submitted_at ? new Date(req.submitted_at).toLocaleDateString('id-ID') : '-'}</td>
                <td style={styles.td}>{req.status_display || req.status}</td>
                <td style={styles.td}>{req.spmb_number || '-'}</td>
                <td style={styles.td}>
                  {/* TODO: Tambahkan Link ke Detail Request */}
                  <Link to={`/requests/${req.id}`} style={styles.link}>Lihat Detail</Link>

                  {/* Tombol Ajukan untuk Draft */}
                  {req.status === 'DRAFT' && (
                      <button
                        style={{...styles.actionButton, backgroundColor: '#ffc107', color: 'black'}}
                        // --- PANGGIL FUNGSI BARU ---
                        onClick={() => handleSubmitDraft(req.id)}
                        // --- AKHIR PANGGILAN FUNGSI ---
                      >
                        Ajukan
                      </button>
                  )}

                   {/* Tombol Terima Barang untuk Completed */}
                   {req.status === 'COMPLETED' && (
                      <button
                        style={{...styles.actionButton, backgroundColor: '#28a745', color: 'white'}}
                        // --- PANGGIL FUNGSI BARU ---
                        onClick={() => handleReceiveItems(req.id)}
                        // --- AKHIR PANGGILAN FUNGSI ---
                      >
                        Terima Barang
                      </button>
                  )}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

export default MyRequestsPage;
