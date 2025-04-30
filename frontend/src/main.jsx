// src/main.jsx (atau index.js jika pakai CRA)
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css' // atau file CSS global Anda
import { AuthProvider } from './contexts/AuthContext'; // Import AuthProvider
import { CartProvider } from './contexts/CartContext';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    {/* Pastikan AuthProvider membungkus CartProvider, atau sebaliknya */}
    {/* Urutan ini biasanya tidak terlalu kritikal, tapi membungkus App adalah kuncinya */}
    <AuthProvider>
      <CartProvider> {/* 2. Bungkus App dengan CartProvider */}
        <App />
      </CartProvider>
    </AuthProvider>
  </React.StrictMode>,
)