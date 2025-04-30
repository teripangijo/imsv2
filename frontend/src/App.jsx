// src/App.jsx
import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';

// Impor komponen halaman
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import ForceChangePasswordPage from './pages/ForceChangePasswordPage';
import ItemListingsPage from './pages/ItemListingsPage';
import ShoppingCartPage from './pages/ShoppingCartPage';
import MyRequestsPage from './pages/MyRequestsPage';
import RequestDetailPage from './pages/RequestDetailPage';
import ProtectedRoute from './components/ProtectedRoute';
// import NotFoundPage from './pages/NotFoundPage';

function App() {
  return (
    <Router>
      <div>
        <Routes>
          {/* Rute Publik */}
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<div>Halaman Utama (Publik)</div>} />

          {/* --- PINDAHKAN SEMENTARA UNTUK TES --- */}
          {/* Rute detail request (sementara di luar ProtectedRoute) */}
          <Route path="/requests/:requestId" element={<RequestDetailPage />} />
          {/* --- AKHIR PEMINDAHAN --- */}


          {/* Rute Terproteksi */}
          <Route element={<ProtectedRoute />}>
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/force-change-password" element={<ForceChangePasswordPage />} />
            <Route path="/items" element={<ItemListingsPage />} />
            <Route path="/cart" element={<ShoppingCartPage />} />
            <Route path="/my-requests" element={<MyRequestsPage />} />
            {/* <Route path="/requests/:requestId" element={<RequestDetailPage />} />  <-- Dipindah ke atas untuk tes */}
          </Route>

          {/* Rute Not Found (opsional) */}
          {/* <Route path="*" element={<NotFoundPage />} /> */}

        </Routes>
      </div>
    </Router>
  );
}

export default App;
