import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Minus, Plus, Trash2, ShieldCheck, ShoppingBag } from 'lucide-react';
import Navbar from '../components/Navbar';
import Footer from '../components/Footer';
import { useCart } from '../context/CartContext';
import { useAuth } from '../context/AuthContext';
import { resolveMediaUrl } from '../services/api';

export default function Cart() {
  const { cart, updateQuantity, removeFromCart } = useCart();
  const { user } = useAuth();
  const navigate = useNavigate();

  if (!user) {
    return (
      <div className="min-h-screen flex flex-col">
        <Navbar />
        <main className="flex-1 max-w-[1240px] w-full mx-auto px-4 py-12 text-center bg-white my-6 rounded-sm shadow-sm">
          <ShoppingBag className="w-16 h-16 text-gray-300 mx-auto mb-3" />
          <h2 className="text-lg font-bold text-fk-dark">Missing Cart items?</h2>
          <p className="text-xs text-gray-500 mt-1">Login to see the items you added previously</p>
          <Link to="/" className="inline-block mt-4 bg-fk-orange text-white font-bold px-8 py-2.5 rounded-sm text-sm shadow">
            Continue Shopping
          </Link>
        </main>
        <Footer />
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col">
      <Navbar />

      <main className="flex-1 max-w-[1240px] w-full mx-auto px-4 py-6">
        {cart.items.length === 0 ? (
          <div className="bg-white rounded-sm shadow-sm p-12 text-center">
            <ShoppingBag className="w-16 h-16 text-gray-300 mx-auto mb-4" />
            <h2 className="text-lg font-bold text-fk-dark">Your cart is empty!</h2>
            <p className="text-xs text-gray-500 mt-1">Add items to it now.</p>
            <Link to="/" className="inline-block mt-5 bg-fk-blue text-white font-bold px-10 py-2.5 rounded-sm text-sm shadow">
              Shop Now
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
            {/* Left Items Column (8 cols) */}
            <div className="lg:col-span-8 bg-white rounded-sm shadow-sm divide-y divide-gray-200">
              <div className="p-4 flex justify-between items-center bg-gray-50/70">
                <h1 className="font-bold text-base text-fk-dark">My Cart ({cart.total_items})</h1>
                <span className="text-xs text-gray-500">Shipkart Assured Delivery</span>
              </div>

              {cart.items.map((item) => {
                const p = item.product;
                const disc = Math.round(((p.mrp - p.price) / p.mrp) * 100);
                return (
                  <div key={item.id} className="p-5 flex gap-5">
                    <div className="w-24 h-24 flex-shrink-0 flex flex-col items-center">
                      <img
                        src={resolveMediaUrl(p.image_url)}
                        alt={p.title}
                        className="w-20 h-20 object-contain"
                      />
                    </div>

                    <div className="flex-1 space-y-2">
                      <Link to={`/product/${p.id}`} className="text-sm font-medium text-fk-dark hover:text-fk-blue">
                        {p.title}
                      </Link>
                      <p className="text-xs text-gray-400">{p.brand} | {p.category}</p>
                      <div className="flex flex-wrap items-center gap-2 text-xs">
                        <span className="text-gray-600">
                          Sold by:{' '}
                          <strong className="text-fk-dark font-semibold">
                            {p.seller_name || 'Shipkart Platform Catalog'}
                          </strong>
                        </span>
                        {p.paypal_ready ? (
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-blue-50 text-fk-blue border border-blue-200">
                            Direct PayPal + Standard Checkout
                          </span>
                        ) : (
                          <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-gray-100 text-gray-600 border border-gray-200">
                            Standard Checkout
                          </span>
                        )}
                      </div>

                      <div className="flex items-baseline gap-2.5 pt-1">
                        <span className="text-base font-bold text-fk-dark">
                          ₹{(p.price * item.quantity).toLocaleString('en-IN')}
                        </span>
                        <span className="text-xs text-gray-400 line-through">
                          ₹{(p.mrp * item.quantity).toLocaleString('en-IN')}
                        </span>
                        <span className="text-xs text-fk-green font-bold">{disc}% Off</span>
                      </div>

                      {/* Stepper & Remove */}
                      <div className="flex items-center gap-6 pt-3">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => updateQuantity(item.id, item.quantity - 1)}
                            className="w-7 h-7 rounded-full border border-gray-300 flex items-center justify-center hover:bg-gray-100"
                          >
                            <Minus className="w-3.5 h-3.5" />
                          </button>
                          <span className="w-8 text-center text-sm font-bold border border-gray-200 py-0.5 rounded">
                            {item.quantity}
                          </span>
                          <button
                            onClick={() => updateQuantity(item.id, item.quantity + 1)}
                            className="w-7 h-7 rounded-full border border-gray-300 flex items-center justify-center hover:bg-gray-100"
                          >
                            <Plus className="w-3.5 h-3.5" />
                          </button>
                        </div>

                        <button
                          onClick={() => removeFromCart(item.id)}
                          className="text-xs font-bold text-gray-700 hover:text-red-600 uppercase flex items-center gap-1"
                        >
                          <Trash2 className="w-3.5 h-3.5" /> Remove
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}

              {/* Place Order Footer Bar */}
              <div className="p-4 bg-white flex justify-end sticky bottom-0 border-t shadow-[0_-2px_6px_rgba(0,0,0,0.06)]">
                <button
                  onClick={() => navigate('/checkout')}
                  className="bg-fk-orange hover:bg-orange-600 text-white font-bold px-10 py-3 rounded-sm text-sm shadow-md transition uppercase tracking-wide"
                >
                  Place Order
                </button>
              </div>
            </div>

            {/* Right Price Details Card (4 cols) */}
            <div className="lg:col-span-4 bg-white rounded-sm shadow-sm p-5 sticky top-20 space-y-4">
              <h2 className="text-sm font-bold text-gray-500 uppercase border-b pb-3">Price Details</h2>

              <div className="space-y-3 text-sm">
                <div className="flex justify-between">
                  <span>Price ({cart.total_items} items)</span>
                  <span>₹{cart.total_mrp.toLocaleString('en-IN')}</span>
                </div>
                <div className="flex justify-between">
                  <span>Discount</span>
                  <span className="text-fk-green font-medium">- ₹{cart.total_discount.toLocaleString('en-IN')}</span>
                </div>
                <div className="flex justify-between">
                  <span>Delivery Charges</span>
                  <span className="text-fk-green font-medium">
                    {cart.delivery_fee === 0 ? 'FREE' : `₹${cart.delivery_fee}`}
                  </span>
                </div>
              </div>

              <div className="border-t border-dashed pt-3 flex justify-between items-center text-base font-bold text-fk-dark">
                <span>Total Amount</span>
                <span>₹{cart.final_amount.toLocaleString('en-IN')}</span>
              </div>

              {Number(cart.paypal_amount) > 0 && (
                <div className="flex justify-between items-center text-xs text-gray-600">
                  <span>PayPal Sandbox Total</span>
                  <span className="font-bold text-fk-blue">
                    ${Number(cart.paypal_amount).toFixed(2)} {cart.paypal_currency || 'USD'}
                  </span>
                </div>
              )}

              <p className="text-xs text-fk-green font-bold border-t pt-3">
                You will save ₹{cart.total_discount.toLocaleString('en-IN')} on this order
              </p>

              <div className="flex items-center gap-2 text-xs text-gray-500 pt-2">
                <ShieldCheck className="w-5 h-5 text-gray-400 flex-shrink-0" />
                <span>Safe and Secure Payments. 100% Authentic products.</span>
              </div>
            </div>
          </div>
        )}
      </main>

      <Footer />
    </div>
  );
}

