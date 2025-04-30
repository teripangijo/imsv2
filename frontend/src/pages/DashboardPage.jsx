// src/pages/DashboardPage.jsx
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext'; // 1. Import useAuth

function DashboardPage() {
  // 2. Dapatkan data user dan fungsi logout dari context
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    console.log('Logging out...');
    await logout(); // Panggil fungsi logout dari context
    console.log('Navigating to login page after logout...');
    navigate('/login'); // Arahkan kembali ke halaman login setelah logout
  };

  // Style sederhana (bisa diganti)
  const styles = {
    container: { padding: '20px' },
    welcomeMessage: { fontSize: '1.5em', marginBottom: '10px' },
    userInfo: { marginBottom: '20px', fontStyle: 'italic' },
    logoutButton: {
      padding: '8px 15px',
      backgroundColor: '#dc3545',
      color: 'white',
      border: 'none',
      borderRadius: '3px',
      cursor: 'pointer',
      fontSize: '14px',
    }
  };

  return (
    <div style={styles.container}>
      <h2>Dashboard</h2>

      {/* Tampilkan info user jika ada */}
      {user ? (
        <>
          <h3 style={styles.welcomeMessage}>
            Selamat datang, {user.first_name || user.email}!
          </h3>
          <p style={styles.userInfo}>
            Anda login sebagai: {user.role_display || user.role}
            {user.department_code && ` (Dept: ${user.department_code})`}
          </p>
          {/* TODO: Tambahkan konten dashboard sesuai peran di sini */}

          {/* Tombol Logout */}
          <button onClick={handleLogout} style={styles.logoutButton}>
            Logout
          </button>
        </>
      ) : (
        // Tampilkan pesan jika data user belum termuat (jarang terjadi jika ProtectedRoute benar)
        <p>Memuat data pengguna...</p>
      )}
    </div>
  );
}

export default DashboardPage;
