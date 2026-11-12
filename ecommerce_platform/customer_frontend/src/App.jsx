import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { CartProvider } from './context/CartContext';

import Home from './pages/Home';
import ProductDetail from './pages/ProductDetail';
import Cart from './pages/Cart';
import Checkout from './pages/Checkout';
import Orders from './pages/Orders';
import OrderTrack from './pages/OrderTrack';
import InfoPage from './pages/InfoPage';

export default function App() {
  return (
    <AuthProvider>
      <CartProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/product/:id" element={<ProductDetail />} />
            <Route path="/cart" element={<Cart />} />
            <Route path="/checkout" element={<Checkout />} />
            <Route path="/orders" element={<Orders />} />
            <Route path="/orders/:id/track" element={<OrderTrack />} />

            {/* About Section Pages */}
            <Route path="/about" element={<InfoPage pageKey="about" />} />
            <Route path="/careers" element={<InfoPage pageKey="careers" />} />
            <Route path="/stories" element={<InfoPage pageKey="stories" />} />
            <Route path="/press" element={<InfoPage pageKey="press" />} />

            {/* Consumer Policy Pages */}
            <Route path="/policy/returns" element={<InfoPage pageKey="returns" />} />
            <Route path="/policy/terms" element={<InfoPage pageKey="terms" />} />
            <Route path="/policy/refund-tracker" element={<InfoPage pageKey="refund-tracker" />} />
            <Route path="/policy/invoices" element={<InfoPage pageKey="invoices" />} />
          </Routes>
        </BrowserRouter>
      </CartProvider>
    </AuthProvider>
  );
}
