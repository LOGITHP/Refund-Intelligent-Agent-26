import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Search, ShoppingCart, User as UserIcon, LogOut, PackageCheck } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useCart } from '../context/CartContext';
import AuthModal from './AuthModal';

export default function Navbar({ onSearch }) {
  const { user, logout } = useAuth();
  const { cart } = useCart();
  const [searchTerm, setSearchTerm] = useState('');
  const [isAuthOpen, setIsAuthOpen] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 12);
    };
    handleScroll();
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    if (onSearch) {
      onSearch(searchTerm);
    } else {
      navigate(`/?search=${encodeURIComponent(searchTerm)}`);
    }
  };

  return (
    <>
      <header
        className={`sticky top-0 z-40 text-white transition-all duration-300 ease-[var(--ease-apple-smooth)] motion-reduce:transition-none ${
          scrolled
            ? 'bg-[#2874f0]/[0.92] backdrop-blur-md shadow-lg'
            : 'bg-fk-blue shadow-md'
        }`}
      >
        <div className="max-w-[1240px] mx-auto px-4 py-2.5 flex items-center justify-between gap-4">
          {/* Logo & Tagline */}
          <Link to="/" className="flex flex-col flex-shrink-0 group">
            <span className="text-xl font-black italic tracking-wide text-white flex items-center gap-0.5">
              Shipkart
            </span>
            <span className="text-[11px] text-gray-200 italic -mt-1 group-hover:underline flex items-center gap-1">
              Explore <span className="text-fk-yellow font-bold">Plus</span>
              <span className="text-fk-yellow text-xs">✦</span>
            </span>
          </Link>

          {/* Search Bar */}
          <form onSubmit={handleSearchSubmit} className="flex-1 max-w-xl relative">
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search for Products, Brands and More"
              className="w-full bg-white text-fk-dark placeholder-gray-500 text-sm py-2 px-4 pr-10 rounded-sm shadow-inner focus:outline-none"
            />
            <button
              type="submit"
              className="absolute right-0 top-0 bottom-0 px-3 text-fk-blue hover:text-blue-700 flex items-center justify-center"
            >
              <Search className="w-4 h-4" />
            </button>
          </form>

          {/* Action Links */}
          <div className="flex items-center gap-6 text-sm font-medium">
            {/* User Login / Profile Dropdown */}
            {user ? (
              <div className="relative" onMouseLeave={() => setShowDropdown(false)}>
                <button
                  onClick={() => setShowDropdown(!showDropdown)}
                  className="flex items-center gap-1.5 bg-white text-fk-blue font-semibold px-4 py-1.5 rounded-sm shadow-sm hover:bg-gray-100 transition"
                >
                  <UserIcon className="w-4 h-4" />
                  <span>{user.full_name?.split(' ')[0] || 'Account'}</span>
                </button>
                {showDropdown && (
                  <div className="apple-link-enter absolute right-0 mt-0.5 w-48 bg-white text-fk-dark rounded-sm shadow-xl py-2 z-50 border border-gray-100">
                    <div className="px-4 py-2 border-b border-gray-100 text-xs text-gray-500">
                      Logged in as <br />
                      <strong className="text-gray-800 text-sm">{user.email}</strong>
                    </div>
                    <Link
                      to="/orders"
                      onClick={() => setShowDropdown(false)}
                      className="flex items-center gap-2 px-4 py-2 hover:bg-gray-50 text-sm text-gray-700"
                    >
                      <PackageCheck className="w-4 h-4 text-fk-blue" />
                      Orders & Returns
                    </Link>
                    <button
                      onClick={() => {
                        logout();
                        setShowDropdown(false);
                      }}
                      className="w-full flex items-center gap-2 px-4 py-2 hover:bg-gray-50 text-sm text-red-600 text-left"
                    >
                      <LogOut className="w-4 h-4" />
                      Logout
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <button
                onClick={() => setIsAuthOpen(true)}
                className="bg-white text-fk-blue font-semibold px-6 py-1.5 rounded-sm shadow-sm hover:bg-gray-100 transition"
              >
                Login
              </button>
            )}

            {/* Cart Link */}
            <Link to="/cart" className="flex items-center gap-1.5 hover:text-fk-yellow transition relative">
              <ShoppingCart className="w-5 h-5" />
              <span>Cart</span>
              {cart?.total_items > 0 && (
                <span
                  key={cart.total_items}
                  className="apple-badge-pop absolute -top-2 -right-3 bg-fk-yellow text-fk-dark font-black text-[11px] px-1.5 py-[1px] rounded-full border border-fk-blue"
                >
                  {cart.total_items}
                </span>
              )}
            </Link>
          </div>
        </div>
      </header>

      {/* Auth Modal */}
      <AuthModal isOpen={isAuthOpen} onClose={() => setIsAuthOpen(false)} />
    </>
  );
}

