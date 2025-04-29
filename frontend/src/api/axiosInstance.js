import axios from 'axios';

const axiosInstance = axios.create({
  baseURL: 'http://127.0.0.1:8000/api/', // URL base API backend Anda
  timeout: 5000, // Timeout request (ms)
  headers: {
    'Content-Type': 'application/json',
    accept: 'application/json',
  },
});

// Interceptor untuk menambahkan token Auth ke setiap request
axiosInstance.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('authToken'); // Ambil token dari local storage
    if (token) {
      config.headers['Authorization'] = `Token ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

export default axiosInstance;