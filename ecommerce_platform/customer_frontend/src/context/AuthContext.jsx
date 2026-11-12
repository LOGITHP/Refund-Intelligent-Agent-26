import React, { createContext, useContext, useEffect, useState } from 'react';
import { authApi } from '../services/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('fk_customer_token');
    if (token) {
      authApi
        .me()
        .then((userData) => {
          if (userData.role === 'customer') {
            setUser(userData);
          } else {
            localStorage.removeItem('fk_customer_token');
          }
        })
        .catch(() => {
          localStorage.removeItem('fk_customer_token');
          setUser(null);
        })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  const login = async (email, password) => {
    const res = await authApi.login(email, password);
    if (res.user.role !== 'customer') {
      throw new Error('Please sign in using a customer account.');
    }
    localStorage.setItem('fk_customer_token', res.access_token);
    setUser(res.user);
    return res.user;
  };

  const register = async (payload) => {
    const res = await authApi.register(payload);
    localStorage.setItem('fk_customer_token', res.access_token);
    setUser(res.user);
    return res.user;
  };

  const logout = () => {
    localStorage.removeItem('fk_customer_token');
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);

