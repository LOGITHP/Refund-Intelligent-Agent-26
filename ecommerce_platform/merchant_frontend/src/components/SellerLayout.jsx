import React, { useState, useEffect, useRef } from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Package,
  ShoppingBag,
  RefreshCw,
  CreditCard,
  LogOut,
  Store,
} from 'lucide-react';
import { useSellerAuth } from '../context/SellerAuthContext';

export default function SellerLayout({ children }) {
  const { seller, logout } = useSellerAuth();
  const mainRef = useRef(null);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const checkScroll = () => {
      const isScrolled =
        (typeof window !== 'undefined' && window.scrollY > 10) ||
        ((mainRef.current?.scrollTop ?? 0) > 10);
      setScrolled(Boolean(isScrolled));
    };

    // Sync immediately on mount
    checkScroll();

    const mainEl = mainRef.current;
    window.addEventListener('scroll', checkScroll, { passive: true });
    if (mainEl) {
      mainEl.addEventListener('scroll', checkScroll, { passive: true });
    }

    return () => {
      window.removeEventListener('scroll', checkScroll);
      if (mainEl) {
        mainEl.removeEventListener('scroll', checkScroll);
      }
    };
  }, []);

  const navItems = [
    { to: '/', label: 'Dashboard', icon: LayoutDashboard },
    { to: '/listings', label: 'My Listings', icon: Package },
    { to: '/orders', label: 'Order Management', icon: ShoppingBag },
    { to: '/returns', label: 'Returns & Disputes', icon: RefreshCw },
    { to: '/settings/payments', label: 'Payment Settings', icon: CreditCard },
  ];

  return (
    <div className="h-screen overflow-hidden flex bg-[#f4f6f9]">
      {/* Dark Navy Sidebar (Shipkart Seller Hub - Static) */}
      <aside className="w-64 h-full bg-seller-navy text-white flex flex-col flex-shrink-0 shadow-xl select-none">
        <div className="p-5 border-b border-white/10 shrink-0">
          <div className="flex items-center gap-2">
            <Store className="w-6 h-6 text-seller-yellow" />
            <div>
              <h1 className="font-black text-lg tracking-tight leading-none">Shipkart</h1>
              <span className="text-[11px] font-bold text-seller-yellow uppercase tracking-widest">
                Seller Hub
              </span>
            </div>
          </div>
          <div className="mt-4 bg-white/10 rounded p-2.5 text-xs">
            <p className="text-gray-300 text-[10px] uppercase font-semibold">Active Business</p>
            <p className="font-bold text-white truncate">{seller?.business_name || seller?.full_name}</p>
          </div>
        </div>

        <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) =>
                  `relative flex items-center gap-3 px-4 py-3 rounded text-sm font-medium transition-all duration-200 ease-[var(--ease-apple-smooth)] motion-reduce:transition-none group ${
                    isActive
                      ? 'bg-seller-blue text-white shadow-md shadow-blue-500/20'
                      : 'text-gray-300 hover:bg-seller-navyHover hover:text-white'
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    <span
                      aria-hidden="true"
                      className={`absolute left-0 top-1.5 bottom-1.5 w-1 rounded-r bg-seller-yellow transition-all duration-200 ease-[var(--ease-apple-smooth)] motion-reduce:transition-none ${
                        isActive
                          ? 'opacity-100 scale-y-100 shadow-[0_0_8px_rgba(255,225,27,0.7)]'
                          : 'opacity-0 scale-y-50'
                      }`}
                    />
                    <Icon className="w-4 h-4 transition-transform duration-200 ease-[var(--ease-apple-smooth)] group-hover:scale-105" />
                    <span>{item.label}</span>
                  </>
                )}
              </NavLink>
            );
          })}
        </nav>

        <div className="p-4 border-t border-white/10 shrink-0">
          <button
            onClick={logout}
            className="w-full flex items-center gap-2 px-3 py-2 text-xs font-semibold text-red-300 hover:bg-red-500/20 hover:text-red-200 rounded transition duration-200 ease-[var(--ease-apple-smooth)] motion-reduce:transition-none"
          >
            <LogOut className="w-4 h-4" />
            <span>Sign Out</span>
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
        <header
          className={`px-6 py-3.5 flex items-center justify-between sticky top-0 z-20 transition-all duration-300 ease-[var(--ease-apple-smooth)] motion-reduce:transition-none ${
            scrolled
              ? 'bg-white/90 backdrop-blur-md shadow-sm border-b border-gray-200/80'
              : 'bg-white border-b border-gray-200'
          }`}
        >
          <h2 className="font-bold text-gray-800 text-base">Merchant Operations & Return Console</h2>
          <div className="flex items-center gap-4 text-xs">
            <span className="bg-blue-50 text-seller-blue font-bold px-2.5 py-1 rounded border border-blue-200">
              Seller Operations
            </span>
            <span className="text-gray-500 font-medium">{seller?.email}</span>
          </div>
        </header>

        <main ref={mainRef} className="flex-1 p-6 overflow-y-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
