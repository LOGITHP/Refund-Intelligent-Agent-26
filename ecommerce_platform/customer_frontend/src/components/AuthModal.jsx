import React, { useState } from 'react';
import { X, Sparkles, UserPlus, LogIn } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export default function AuthModal({ isOpen, onClose }) {
  const { login, register } = useAuth();
  const [isRegister, setIsRegister] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [phone, setPhone] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      if (isRegister) {
        await register({ email, password, full_name: fullName, phone });
      } else {
        await login(email, password);
      }
      onClose();
    } catch (err) {
      setError(err.message || 'Authentication failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="apple-scrim-enter fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="apple-panel-enter bg-white rounded-sm shadow-2xl flex max-w-2xl w-full overflow-hidden relative min-h-[460px]">
        <button
          onClick={onClose}
          className="absolute right-3 top-3 text-gray-400 hover:text-gray-700 z-10 p-1"
          aria-label="Close modal"
        >
          <X className="w-5 h-5" />
        </button>

        {/* Left Shipkart Blue Banner */}
        <div className="w-2/5 bg-fk-blue p-8 text-white flex flex-col justify-between hidden sm:flex">
          <div>
            <h2 className="text-2xl font-bold leading-tight">
              {isRegister ? 'Create Customer Account' : 'Customer Login'}
            </h2>
            <p className="text-gray-200 text-sm mt-3 leading-relaxed">
              {isRegister
                ? 'Register with your email and password to place orders, track deliveries, and manage returns.'
                : 'Sign in with your account to access Orders, Cart, Tax Invoices, and Return Requests.'}
            </p>
          </div>
          <div className="bg-blue-600/60 p-3 rounded text-xs text-blue-100 flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-fk-yellow flex-shrink-0" />
            <span>Safe & encrypted account authentication</span>
          </div>
        </div>

        {/* Right Form Container */}
        <div className="w-full sm:w-3/5 p-8 flex flex-col justify-between">
          <div>
            {/* Mode Switch Pills */}
            <div className="grid grid-cols-2 gap-2 mb-5 bg-gray-100 p-1 rounded">
              <button
                type="button"
                onClick={() => {
                  setIsRegister(false);
                  setError('');
                }}
                className={`py-1.5 text-xs font-bold rounded flex items-center justify-center gap-1.5 transition ${
                  !isRegister ? 'bg-white text-fk-blue shadow-sm' : 'text-gray-600'
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
                className={`py-1.5 text-xs font-bold rounded flex items-center justify-center gap-1.5 transition ${
                  isRegister ? 'bg-white text-fk-blue shadow-sm' : 'text-gray-600'
                }`}
              >
                <UserPlus className="w-3.5 h-3.5" /> Create Account
              </button>
            </div>

            {error && (
              <div className="mb-4 p-2.5 bg-red-50 border border-red-200 text-red-600 text-xs rounded">
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              {isRegister && (
                <>
                  <div>
                    <label className="text-xs font-semibold text-gray-600">Full Name</label>
                    <input
                      type="text"
                      required
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      placeholder="Enter your full name"
                      className="w-full mt-1 px-3 py-2 border border-gray-300 rounded text-sm focus:border-fk-blue focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-semibold text-gray-600">Mobile Phone</label>
                    <input
                      type="tel"
                      value={phone}
                      onChange={(e) => setPhone(e.target.value)}
                      placeholder="10-digit mobile number"
                      className="w-full mt-1 px-3 py-2 border border-gray-300 rounded text-sm focus:border-fk-blue focus:outline-none"
                    />
                  </div>
                </>
              )}

              <div>
                <label className="text-xs font-semibold text-gray-600">Email Address</label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  className="w-full mt-1 px-3 py-2 border border-gray-300 rounded text-sm focus:border-fk-blue focus:outline-none"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-gray-600">Password</label>
                <input
                  type="password"
                  required
                  minLength={6}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter password (min 6 chars)"
                  className="w-full mt-1 px-3 py-2 border border-gray-300 rounded text-sm focus:border-fk-blue focus:outline-none"
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full bg-fk-orange hover:bg-orange-600 text-white font-bold py-2.5 rounded text-sm shadow transition"
              >
                {loading ? 'Please wait...' : isRegister ? 'Create Customer Account' : 'Sign In'}
              </button>
            </form>
          </div>

          <div className="pt-4 text-center border-t border-gray-100">
            <button
              type="button"
              onClick={() => {
                setIsRegister(!isRegister);
                setError('');
              }}
              className="text-fk-blue hover:underline text-xs font-semibold"
            >
              {isRegister ? 'Already have an account? Sign In' : 'New customer? Create an account'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
