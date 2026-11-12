import React, { useState, useRef } from 'react';
import { Store, ShieldCheck, LogIn, UserPlus } from 'lucide-react';
import { useSellerAuth } from '../context/SellerAuthContext';
import { useStaggeredReveal } from '../motion/useStaggeredReveal';

export default function Login() {
  const { login, register } = useSellerAuth();
  const [isRegister, setIsRegister] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [businessName, setBusinessName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const heroRef = useRef(null);
  useStaggeredReveal(heroRef, { triggerKey: 'login-hero' });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      if (isRegister) {
        await register({ email, password, full_name: fullName, business_name: businessName });
      } else {
        await login(email, password);
      }
    } catch (err) {
      setError(err.message || 'Authentication failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-seller-navy flex items-center justify-center p-4">
      <div className="bg-white rounded shadow-2xl max-w-4xl w-full grid grid-cols-1 md:grid-cols-2 overflow-hidden apple-panel-enter">
        {/* Left Seller Hub Banner */}
        <div ref={heroRef} className="bg-[#1c3553] text-white p-10 flex flex-col justify-between">
          <div>
            <div data-staggered-item className="flex items-center gap-2 mb-6">
              <Store className="w-8 h-8 text-seller-yellow" />
              <div>
                <h1 className="font-black text-2xl leading-none">Shipkart</h1>
                <span className="text-xs font-bold text-seller-yellow uppercase tracking-widest">
                  Seller Hub
                </span>
              </div>
            </div>
            <h2 data-staggered-item className="text-xl font-bold leading-snug">
              Grow your business & manage disputes seamlessly
            </h2>
            <p data-staggered-item className="text-blue-200 text-sm mt-3 leading-relaxed">
              Independent Merchant Operations Portal. Register your seller account to manage product listings, fulfill incoming customer orders, and review return requests with customer evidence.
            </p>
          </div>

          <div data-staggered-item className="bg-white/10 border border-white/15 rounded p-4 text-xs space-y-2 mt-8">
            <div className="flex items-center gap-2 text-seller-yellow font-bold">
              <ShieldCheck className="w-4 h-4" />
              <span>Seller Protection & Dispute Tools</span>
            </div>
            <p className="text-gray-200">
              Inspect customer-submitted condition photos, verify delivery timelines, and manage return claims effortlessly.
            </p>
          </div>
        </div>

        {/* Right Form */}
        <div className="p-8 md:p-10 flex flex-col justify-between">
          <div>
            <h3 className="text-xl font-bold text-gray-800 mb-1">
              {isRegister ? 'Register Seller Account' : 'Merchant Sign In'}
            </h3>
            <p className="text-xs text-gray-500 mb-5">
              Access your Shipkart Seller Hub Dashboard
            </p>

            {/* Mode Switch Pills */}
            <div className="grid grid-cols-2 gap-2 mb-5 bg-gray-100 p-1 rounded">
              <button
                type="button"
                onClick={() => {
                  setIsRegister(false);
                  setError('');
                }}
                className={`py-1.5 text-xs font-bold rounded flex items-center justify-center gap-1.5 transition-all duration-200 ease-[var(--ease-apple-smooth)] motion-reduce:transition-none ${
                  !isRegister ? 'bg-white text-seller-blue shadow-sm' : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                <LogIn className="w-3.5 h-3.5" /> Sign In
              </button>
              <button
                type="button"
                onClick={() => {
                  setIsRegister(true);
                  setError('');
                }}
                className={`py-1.5 text-xs font-bold rounded flex items-center justify-center gap-1.5 transition-all duration-200 ease-[var(--ease-apple-smooth)] motion-reduce:transition-none ${
                  isRegister ? 'bg-white text-seller-blue shadow-sm' : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                <UserPlus className="w-3.5 h-3.5" /> Register Seller
              </button>
            </div>

            {error && (
              <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-600 text-xs rounded apple-anim-fade">
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              {isRegister && (
                <div className="space-y-4 apple-link-enter">
                  <div>
                    <label className="text-xs font-bold text-gray-600 uppercase">Full Name</label>
                    <input
                      type="text"
                      required
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      placeholder="Merchant Owner Name"
                      className="w-full mt-1 border border-gray-300 rounded px-3 py-2 text-sm focus:border-seller-blue focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-bold text-gray-600 uppercase">Business / Store Name</label>
                    <input
                      type="text"
                      required
                      value={businessName}
                      onChange={(e) => setBusinessName(e.target.value)}
                      placeholder="e.g. RetailNet Electronics"
                      className="w-full mt-1 border border-gray-300 rounded px-3 py-2 text-sm focus:border-seller-blue focus:outline-none"
                    />
                  </div>
                </div>
              )}

              <div>
                <label className="text-xs font-bold text-gray-600 uppercase">Seller Email</label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="merchant@yourstore.com"
                  className="w-full mt-1 border border-gray-300 rounded px-3 py-2 text-sm focus:border-seller-blue focus:outline-none"
                />
              </div>

              <div>
                <label className="text-xs font-bold text-gray-600 uppercase">Password</label>
                <input
                  type="password"
                  required
                  minLength={6}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter password (min 6 chars)"
                  className="w-full mt-1 border border-gray-300 rounded px-3 py-2 text-sm focus:border-seller-blue focus:outline-none"
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full bg-seller-blue hover:bg-blue-700 text-white font-bold py-2.5 rounded text-sm shadow transition-all duration-200 ease-[var(--ease-apple-smooth)] motion-reduce:transition-none"
              >
                {loading ? 'Authenticating...' : isRegister ? 'Create Seller Account' : 'Sign In to Seller Hub'}
              </button>
            </form>
          </div>

          <div className="pt-6 text-center border-t border-gray-100 mt-6">
            <button
              type="button"
              onClick={() => {
                setIsRegister(!isRegister);
                setError('');
              }}
              className="text-xs font-bold text-seller-blue hover:underline transition-colors duration-150 ease-[var(--ease-apple-smooth)]"
            >
              {isRegister ? 'Already registered? Sign In' : 'New Merchant? Register your Business'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
