import React, { createContext, useContext, useEffect, useState } from 'react';
import { cartApi } from '../services/api';
import { useAuth } from './AuthContext';

const CartContext = createContext(null);

export function CartProvider({ children }) {
  const { user } = useAuth();
  const [cart, setCart] = useState({
    items: [],
    total_items: 0,
    total_mrp: 0,
    total_selling_price: 0,
    total_discount: 0,
    delivery_fee: 0,
    final_amount: 0,
  });

  const refreshCart = async () => {
    if (!user) {
      setCart({
        items: [],
        total_items: 0,
        total_mrp: 0,
        total_selling_price: 0,
        total_discount: 0,
        delivery_fee: 0,
        final_amount: 0,
      });
      return;
    }
    try {
      const data = await cartApi.get();
      setCart(data);
    } catch {
      // ignore if token invalid
    }
  };

  useEffect(() => {
    refreshCart();
  }, [user]);

  const addToCart = async (productId, quantity = 1) => {
    const data = await cartApi.add(productId, quantity);
    setCart(data);
    return data;
  };

  const updateQuantity = async (itemId, quantity) => {
    const data = await cartApi.update(itemId, quantity);
    setCart(data);
  };

  const removeFromCart = async (itemId) => {
    const data = await cartApi.remove(itemId);
    setCart(data);
  };

  return (
    <CartContext.Provider value={{ cart, refreshCart, addToCart, updateQuantity, removeFromCart }}>
      {children}
    </CartContext.Provider>
  );
}

export const useCart = () => useContext(CartContext);

