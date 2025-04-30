// src/pages/LoginPage.jsx
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
// import axiosInstance from '../api/axiosInstance'; // Masih nonaktifkan Axios
import { useAuth } from '../contexts/AuthContext';

function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { login } = useAuth();

  const handleSubmit = async (event) => {
    event.preventDefault();
    setLoading(true);
    setError(null);

    // --- Menggunakan Fetch API (Error handling disederhanakan) ---
    const apiUrl = 'http://127.0.0.1:8000/api/auth/login/'; // Pastikan URL benar

    try {
      const response = await fetch(apiUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        body: JSON.stringify({
          email: email,
          password: password,
        }),
      });

      // Langsung coba parse JSON, biarkan error jika gagal
      const data = await response.json();

      // Periksa status OK *setelah* coba parse JSON
      if (!response.ok) {
        // Jika tidak OK, lempar error dengan data JSON (jika ada) atau status text
        throw new Error(data.error?.detail || JSON.stringify(data) || response.statusText);
      }

      // Jika OK, lanjutkan proses login
      console.log('Login Response (Fetch):', data);
      const { token, user } = data;
      login(user, token);
      console.log('Login function from context called.');

      // Navigasi
      if (user && user.password_reset_required) {
        console.log('Password reset required, navigating to change password page...');
        navigate('/force-change-password');
      } else {
        console.log('Login sukses, navigating to dashboard...');
        navigate('/dashboard');
      }

    } catch (err) {
      // Tangkap semua jenis error (network, parsing, atau dari throw di atas)
      console.error('Login Error (Fetch):', err);
      // Tampilkan pesan errornya
      // Jika error jaringan, err.message biasanya "Failed to fetch"
      setError(err.message || 'Login gagal. Terjadi kesalahan.');
    } finally {
      setLoading(false);
    }
    // --- Akhir Fetch API ---
  };

  // Style (sama seperti sebelumnya)
  const styles = {
    container: { display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '80vh', padding: '20px' },
    form: { display: 'flex', flexDirection: 'column', width: '300px', padding: '20px', border: '1px solid #ccc', borderRadius: '5px', boxShadow: '0 2px 4px rgba(0,0,0,0.1)' },
    inputGroup: { marginBottom: '15px' },
    label: { marginBottom: '5px', display: 'block', fontWeight: 'bold' },
    input: { width: '100%', padding: '8px', border: '1px solid #ccc', borderRadius: '3px', boxSizing: 'border-box' },
    button: { padding: '10px 15px', backgroundColor: '#007bff', color: 'white', border: 'none', borderRadius: '3px', cursor: 'pointer', fontSize: '16px', opacity: 1 },
    error: { color: 'red', marginBottom: '10px', fontSize: '14px', textAlign: 'center' },
  };

  return (
    <div style={styles.container}>
      <h2>Login Aplikasi Persediaan</h2>
      <form onSubmit={handleSubmit} style={styles.form}>
        <div style={styles.inputGroup}>
          <label htmlFor="email" style={styles.label}>Alamat Email:</label>
          <input
            type="email"
            id="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            style={styles.input}
            disabled={loading}
          />
        </div>
        <div style={styles.inputGroup}>
          <label htmlFor="password" style={styles.label}>Password:</label>
          <input
            type="password"
            id="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            style={styles.input}
            disabled={loading}
          />
        </div>
        {error && <p style={styles.error}>{error}</p>}
        <button type="submit" style={styles.button} disabled={loading}>
          {loading ? 'Loading...' : 'Login'}
        </button>
      </form>
    </div>
  );
}

export default LoginPage;
