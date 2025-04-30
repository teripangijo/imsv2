// src/components/ProtectedRoute.jsx
import React from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

/**
 * Komponen untuk melindungi route.
 * Jika user sudah login (authenticated), tampilkan konten route (Outlet).
 * Jika belum login, arahkan ke halaman login, simpan lokasi asal.
 */
function ProtectedRoute() {
  const { isAuthenticated, loadingAuth } = useAuth(); // Dapatkan status login & loading dari context
  const location = useLocation(); // Dapatkan lokasi saat ini untuk redirect kembali setelah login

  // Tampilkan loading indicator jika status auth awal belum selesai dicek
  if (loadingAuth) {
    return <div>Memverifikasi autentikasi...</div>; // Atau tampilkan spinner
  }

  // Jika sudah terautentikasi, render komponen anak (halaman yang dituju)
  if (isAuthenticated) {
    return <Outlet />; // Outlet akan merender elemen route yang dibungkus oleh ProtectedRoute
  }

  // Jika tidak terautentikasi, arahkan ke halaman login
  // state={{ from: location }} menyimpan lokasi asal agar bisa kembali setelah login
  return <Navigate to="/login" state={{ from: location }} replace />;
}

export default ProtectedRoute;
