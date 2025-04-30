// src/pages/RequestDetailPage.jsx
import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom'; // Import useParams untuk mengambil ID dari URL
import axiosInstance from '../api/axiosInstance';
import { useAuth } from '../contexts/AuthContext';

function RequestDetailPage() {
  const { requestId } = useParams(); // Mengambil parameter 'requestId' dari URL
  const [requestData, setRequestData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const { user } = useAuth(); // Ambil info user jika perlu untuk permission/tampilan

  useEffect(() => {
    const fetchRequestDetail = async () => {
      if (!requestId) return; // Jangan fetch jika ID tidak ada
      setLoading(true);
      setError(null);
      try {
        const response = await axiosInstance.get(`/requests/${requestId}/`);
        console.log("Request Detail Response:", response.data);
        setRequestData(response.data);
      } catch (err) {
        console.error("Error fetching request detail:", err);
        setError(err.response?.data?.detail || err.message || "Gagal memuat detail permintaan.");
        setRequestData(null);
      } finally {
        setLoading(false);
      }
    };

    fetchRequestDetail();
  }, [requestId]); // Fetch ulang jika requestId berubah

  // Style sederhana
  const styles = {
    container: { padding: '20px' },
    loading: { textAlign: 'center', padding: '20px', fontSize: '1.2em' },
    error: { color: 'red', padding: '20px' },
    detailSection: { marginBottom: '15px', paddingBottom: '10px', borderBottom: '1px solid #eee' },
    label: { fontWeight: 'bold', marginRight: '5px'},
    itemTable: { width: '100%', borderCollapse: 'collapse', marginTop: '10px' },
    th: { border: '1px solid #ddd', padding: '8px', textAlign: 'left', backgroundColor: '#f2f2f2' },
    td: { border: '1px solid #ddd', padding: '8px' },
  };

  if (loading) {
    return <div style={styles.loading}>Memuat detail permintaan ID: {requestId}...</div>;
  }

  if (error) {
    if (error.includes("tidak ditemukan") || (error.response && error.response.status === 404)) {
        return <div style={styles.error}>Error: Permintaan dengan ID {requestId} tidak ditemukan.</div>;
    }
    return <div style={styles.error}>Error: {error}</div>;
  }

  if (!requestData) {
    return <div style={styles.container}>Data permintaan tidak ditemukan atau gagal dimuat.</div>;
  }

  // Tampilkan detail permintaan
  return (
    <div style={styles.container}>
      <h2>Detail Permintaan {requestData.request_number || `(ID: ${requestData.id})`}</h2>

      <div style={styles.detailSection}>
        <p><span style={styles.label}>Status:</span> {requestData.status_display || requestData.status}</p>
        <p><span style={styles.label}>Peminta:</span> {requestData.requester?.email || 'N/A'}</p>
        <p><span style={styles.label}>Tanggal Dibuat:</span> {new Date(requestData.created_at).toLocaleString('id-ID')}</p>
        {requestData.submitted_at && <p><span style={styles.label}>Tanggal Diajukan:</span> {new Date(requestData.submitted_at).toLocaleString('id-ID')}</p>}
        {requestData.supervisor1_approver && <p><span style={styles.label}>Disetujui SPV1:</span> {requestData.supervisor1_approver.email} ({new Date(requestData.supervisor1_decision_at).toLocaleString('id-ID')})</p>}
        {requestData.supervisor1_rejection_reason && <p><span style={styles.label}>Alasan Tolak SPV1:</span> {requestData.supervisor1_rejection_reason}</p>}
        {/* TODO: Tampilkan info SPV2, Operator, Penerima */}
        {requestData.spmb_document && <p><span style={styles.label}>No. SPMB:</span> {requestData.spmb_document.spmb_number || '(Lihat Detail SPMB)'}</p>}
      </div>

      <h3>Item Barang yang Diminta:</h3>
      <table style={styles.itemTable}>
        <thead>
          <tr>
            <th style={styles.th}>Kode Barang</th>
            <th style={styles.th}>Jenis</th>
            <th style={styles.th}>Nama Spesifik</th>
            <th style={styles.th}>Satuan</th>
            <th style={styles.th}>Jml Diminta</th>
            <th style={styles.th}>Jml Disetujui SPV2</th>
            <th style={styles.th}>Jml Dikeluarkan</th>
          </tr>
        </thead>
        <tbody>
          {/* Lakukan map langsung, tapi cek validitas di dalam map */}
          {requestData.items && requestData.items.length > 0 ? (
            requestData.items.map(item => {
              // --- PERUBAHAN: Cek validitas DI DALAM map ---
              if (!item || !item.variant) {
                // Jika item atau variant tidak valid, kembalikan null
                // React akan mengabaikan null saat rendering
                return null;
              }
              // Jika valid, render baris tabel
              return (
                <tr key={item.id}>
                  <td style={styles.td}>{item.variant.full_code || 'N/A'}</td>
                  <td style={styles.td}>{item.variant.type_name || 'N/A'}</td>
                  <td style={styles.td}>{item.variant.variant_name || item.variant.name || 'N/A'}</td>
                  <td style={styles.td}>{item.variant.unit_of_measure || 'N/A'}</td>
                  <td style={styles.td}>{item.quantity_requested}</td>
                  <td style={styles.td}>{item.quantity_approved_spv2 ?? '-'}</td>
                  <td style={styles.td}>{item.quantity_issued}</td>
                </tr>
              );
              // --- AKHIR PERUBAHAN ---
            })
          ) : (
            <tr>
              <td colSpan="7" style={{ textAlign: 'center', padding: '10px' }}>Tidak ada item dalam permintaan ini.</td>
            </tr>
          )}
        </tbody>
      </table>

      {/* TODO: Tambahkan tombol aksi sesuai status dan peran */}

      <br />
      <Link to="/my-requests">Kembali ke Daftar Permintaan</Link>
    </div>
  );
}

export default RequestDetailPage;
