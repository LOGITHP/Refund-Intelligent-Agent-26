import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { SellerAuthProvider, useSellerAuth } from './context/SellerAuthContext';
import SellerLayout from './components/SellerLayout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Listings from './pages/Listings';
import Orders from './pages/Orders';
import Returns from './pages/Returns';
import PaymentSettings from './pages/PaymentSettings';

function ProtectedSellerRoutes() {
  const { seller, loading } = useSellerAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#f4f6f9] text-sm text-gray-500">
        Verifying Seller Hub Session...
      </div>
    );
  }

  if (!seller) {
    return <Login />;
  }

  return (
    <SellerLayout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/listings" element={<Listings />} />
        <Route path="/orders" element={<Orders />} />
        <Route path="/returns" element={<Returns />} />
        <Route path="/settings/payments" element={<PaymentSettings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </SellerLayout>
  );
}

export default function App() {
  return (
    <SellerAuthProvider>
      <BrowserRouter>
        <ProtectedSellerRoutes />
      </BrowserRouter>
    </SellerAuthProvider>
  );
}

