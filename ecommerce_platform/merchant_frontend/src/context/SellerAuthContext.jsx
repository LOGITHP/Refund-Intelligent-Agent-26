import React, { createContext, useContext, useEffect, useState } from 'react';
import { sellerAuthApi } from '../services/api';

const SellerAuthContext = createContext(null);

export function SellerAuthProvider({ children }) {
  const [seller, setSeller] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('fk_merchant_token');
    if (token) {
      sellerAuthApi
        .me()
        .then((userData) => {
          if (userData.role === 'merchant') {
            setSeller(userData);
          } else {
            localStorage.removeItem('fk_merchant_token');
          }
        })
        .catch(() => {
          localStorage.removeItem('fk_merchant_token');
          setSeller(null);
        })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  const login = async (email, password) => {
    const res = await sellerAuthApi.login(email, password);
    if (res.user.role !== 'merchant') {
      throw new Error('This account belongs to a Customer. Please log in through the Shipkart Storefront.');
    }
    localStorage.setItem('fk_merchant_token', res.access_token);
    setSeller(res.user);
    return res.user;
  };

  const register = async (payload) => {
    const res = await sellerAuthApi.register(payload);
    localStorage.setItem('fk_merchant_token', res.access_token);
    setSeller(res.user);
    return res.user;
  };

  const logout = () => {
    localStorage.removeItem('fk_merchant_token');
    setSeller(null);
  };

  return (
    <SellerAuthContext.Provider value={{ seller, loading, login, register, logout }}>
      {children}
    </SellerAuthContext.Provider>
  );
}

export const useSellerAuth = () => useContext(SellerAuthContext);

