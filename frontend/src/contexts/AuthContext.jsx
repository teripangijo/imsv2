// src/contexts/AuthContext.jsx
import React, { createContext, useState, useContext, useEffect } from 'react';
import axiosInstance from '../api/axiosInstance'; // Import instance Axios

// 1. Buat Context
const AuthContext = createContext(null);

// 2. Buat Provider Component
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(localStorage.getItem('authToken')); // Coba ambil token dari localStorage saat awal load
  const [loading, setLoading] = useState(true); // Loading state untuk cek token awal

  // Efek untuk cek token saat aplikasi pertama kali load atau token berubah
  useEffect(() => {
    const verifyToken = async () => {
      const storedToken = localStorage.getItem('authToken');
      if (storedToken) {
        setToken(storedToken); // Set token di state
        try {
          // --- PERUBAHAN URL DI SINI ---
          // Panggil endpoint /api/auth/profile/ untuk verifikasi token & dapat data user
          console.log('Verifying token using /auth/profile/ ...');
          const response = await axiosInstance.get('/auth/profile/'); // Gunakan URL baru
          // --- AKHIR PERUBAHAN URL ---

          setUser(response.data); // Simpan data user jika token valid
          console.log('Token valid, user data:', response.data);
        } catch (error) {
          // Jika token tidak valid (misal: 404, 401, 403 dari endpoint profile)
          console.error('Token verification failed:', error.response?.data || error.message);
          localStorage.removeItem('authToken'); // Hapus token invalid
          setToken(null);
          setUser(null);
        }
      } else {
        // Tidak ada token tersimpan
        setToken(null);
        setUser(null);
      }
      setLoading(false); // Selesai loading pengecekan awal
    };

    verifyToken();
  }, []); // Dependency array kosong agar hanya jalan sekali saat mount

  // Fungsi untuk login
  const login = (userData, authToken) => {
    localStorage.setItem('authToken', authToken); // Simpan token ke localStorage
    setToken(authToken); // Update state token
    setUser(userData); // Update state user
  };

  // Fungsi untuk logout
  const logout = async () => {
    try {
      // Panggil API logout backend untuk menghapus token di server (opsional tapi bagus)
      await axiosInstance.post('/auth/logout/');
      console.log('Server logout successful');
    } catch (error) {
      console.error('Server logout failed:', error.response?.data || error.message);
      // Tetap lanjutkan logout di frontend meskipun server gagal
    } finally {
      localStorage.removeItem('authToken'); // Hapus token dari localStorage
      setToken(null); // Reset state token
      setUser(null); // Reset state user
      // Navigasi ke login biasanya dilakukan di komponen pemanggil logout
    }
  };

  // Nilai yang akan disediakan oleh Context
  const value = {
    isAuthenticated: !!token && !!user, // User dianggap login jika ada token DAN data user
    user,
    token,
    login,
    logout,
    loadingAuth: loading, // Sediakan status loading auth awal
  };

  // Render children hanya setelah loading selesai (opsional, tapi mencegah flash)
  // if (loading) {
  //   return <div>Loading authentication...</div>; // Atau tampilkan spinner
  // }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// 3. Buat Custom Hook untuk menggunakan Context
export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
