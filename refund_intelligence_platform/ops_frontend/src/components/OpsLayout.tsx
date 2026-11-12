import { useEffect, useRef, useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import {
  Bot,
  Clock,
  CreditCard,
  FileSearch,
  FolderKanban,
  LayoutDashboard,
  LogOut,
  Menu,
  Network,
  Scale,
  ShieldAlert,
  Store,
  X,
} from 'lucide-react';
import {
  OPS_TOKEN_EVENT,
  clearStoredToken,
  getStoredToken,
  getStoredUser,
  opsApi,
} from '../api/client';
import type { PlatformUser } from '../types/api';
import { PlatformLoginScreen } from './PlatformLoginScreen';

interface NavItem {
  to: string;
  label: string;
  icon: typeof LayoutDashboard;
  simulated?: boolean;
}

const NAV_GROUPS: Array<{ title: string; items: NavItem[] }> = [
  {
    title: 'Command Center',
    items: [
      { to: '/operations/dashboard', label: 'Overview', icon: LayoutDashboard },
      { to: '/operations/cases', label: 'Refund Cases', icon: FolderKanban },
      { to: '/operations/eta', label: 'ETA & Delay Alerts', icon: Clock },
    ],
  },
  {
    title: 'AI & Guardrails',
    items: [
      { to: '/operations/agents', label: '3-Agent Monitor', icon: Bot },
      { to: '/operations/compliance', label: 'Compliance Rules', icon: ShieldAlert },
      { to: '/operations/audit', label: 'Immutable Audit', icon: FileSearch },
    ],
  },
  {
    title: 'Simulators & Health',
    items: [
      { to: '/operations/integrations', label: 'Health & Carrier Sim', icon: Network, simulated: true },
      { to: '/operations/issuer-simulator', label: 'Issuer Bank Sim', icon: CreditCard, simulated: true },
      { to: '/operations/regulatory', label: 'Regulatory Sim', icon: Scale, simulated: true },
    ],
  },
];

export function OpsLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [token, setToken] = useState<string | null>(() => getStoredToken());
  const [currentUser, setCurrentUser] = useState<PlatformUser | null>(() => getStoredUser());
  const [scrolled, setScrolled] = useState(false);
  const mainRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const syncAuth = () => {
      setToken(getStoredToken());
      setCurrentUser(getStoredUser());
    };
    window.addEventListener(OPS_TOKEN_EVENT, syncAuth);
    window.addEventListener('storage', syncAuth);
    return () => {
      window.removeEventListener(OPS_TOKEN_EVENT, syncAuth);
      window.removeEventListener('storage', syncAuth);
    };
  }, []);

  useEffect(() => {
    if (!token) return;
    let active = true;
    opsApi
      .getMe()
      .then((res) => {
        if (active && res.user) {
          setCurrentUser(res.user);
        }
      })
      .catch(() => {
        // Any 401 clears token automatically and returns to login screen
      });
    return () => {
      active = false;
    };
  }, [token]);

  useEffect(() => {
    const mainEl = mainRef.current;
    if (!mainEl) return;
    const onScroll = () => setScrolled(mainEl.scrollTop > 10);
    onScroll();
    mainEl.addEventListener('scroll', onScroll, { passive: true });
    return () => mainEl.removeEventListener('scroll', onScroll);
  }, [token]);

  if (!token) {
    return (
      <PlatformLoginScreen
        onAuthenticated={(user) => {
          setToken(getStoredToken());
          setCurrentUser(user);
        }}
      />
    );
  }

  function handleSignOut() {
    clearStoredToken();
    setToken(null);
    setCurrentUser(null);
  }

  const sidebarContent = (
    <div className="flex h-full flex-col bg-shipkart-navy text-white select-none">
      {/* Brand + Active Operator (Matches Shipkart Seller Hub Sidebar) */}
      <div className="p-5 border-b border-white/10 shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Store className="w-6 h-6 text-shipkart-yellow" />
            <div>
              <h1 className="font-black text-lg tracking-tight leading-none">Shipkart</h1>
              <span className="text-[11px] font-bold text-shipkart-yellow uppercase tracking-widest">
                Refund Intel
              </span>
            </div>
          </div>
          <button
            type="button"
            className="rounded p-1 text-gray-300 hover:bg-white/10 hover:text-white lg:hidden"
            onClick={() => setSidebarOpen(false)}
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="mt-4 bg-white/10 rounded p-2.5 text-xs">
          <p className="text-gray-300 text-[10px] uppercase font-semibold">Active Operator</p>
          <p className="font-bold text-white truncate">
            {currentUser?.full_name || 'Platform Operations'}
          </p>
          <p className="text-[11px] text-blue-200 truncate">
            {currentUser?.email || 'Authenticated Session'}
          </p>
        </div>
      </div>

      {/* Navigation Links */}
      <nav className="flex-1 px-3 py-3 space-y-5 overflow-y-auto">
        {NAV_GROUPS.map((group) => (
          <div key={group.title}>
            <p className="px-3 mb-1.5 text-[10px] font-bold uppercase tracking-widest text-blue-200/60">
              {group.title}
            </p>
            <ul className="space-y-1">
              {group.items.map((item) => {
                const Icon = item.icon;
                return (
                  <li key={item.to}>
                    <NavLink
                      to={item.to}
                      onClick={() => setSidebarOpen(false)}
                      className={({ isActive }) =>
                        `relative flex items-center justify-between px-4 py-2.5 rounded text-sm font-medium transition-all duration-200 ease-[var(--ease-apple-smooth)] group ${
                          isActive
                            ? 'bg-shipkart-blue text-white shadow-md shadow-blue-500/20'
                            : 'text-gray-300 hover:bg-shipkart-navyHover hover:text-white'
                        }`
                      }
                    >
                      {({ isActive }) => (
                        <>
                          <span
                            aria-hidden="true"
                            className={`absolute left-0 top-1.5 bottom-1.5 w-1 rounded-r bg-shipkart-yellow transition-all duration-200 ease-[var(--ease-apple-smooth)] ${
                              isActive
                                ? 'opacity-100 scale-y-100 shadow-[0_0_8px_rgba(255,225,27,0.7)]'
                                : 'opacity-0 scale-y-50'
                            }`}
                          />
                          <span className="flex items-center gap-3">
                            <Icon className="w-4 h-4 shrink-0 transition-transform duration-200 ease-[var(--ease-apple-smooth)] group-hover:scale-105" />
                            <span>{item.label}</span>
                          </span>
                          {item.simulated && (
                            <span
                              className={`rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider ${
                                isActive
                                  ? 'bg-white/20 text-white'
                                  : 'bg-shipkart-yellow/15 text-shipkart-yellow'
                              }`}
                            >
                              Sim
                            </span>
                          )}
                        </>
                      )}
                    </NavLink>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      {/* Sign Out Pinned at Bottom */}
      <div className="p-4 border-t border-white/10 shrink-0">
        <button
          type="button"
          onClick={handleSignOut}
          className="w-full flex items-center gap-2 px-3 py-2 text-xs font-semibold text-red-300 hover:bg-red-500/20 hover:text-red-200 rounded transition duration-200 ease-[var(--ease-apple-smooth)]"
        >
          <LogOut className="w-4 h-4" />
          <span>Sign Out</span>
        </button>
      </div>
    </div>
  );

  return (
    <div className="h-screen overflow-hidden flex bg-shipkart-bg text-[#212121]">
      {/* Static Desktop Sidebar */}
      <aside className="hidden lg:block w-64 h-full shrink-0 shadow-xl">{sidebarContent}</aside>

      {/* Mobile Sidebar Drawer */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-40 flex lg:hidden">
          <div
            className="fixed inset-0 bg-shipkart-navy/60"
            onClick={() => setSidebarOpen(false)}
          />
          <aside className="relative z-50 w-64 h-full shadow-xl">{sidebarContent}</aside>
        </div>
      )}

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
        <header
          className={`px-6 py-3.5 flex items-center justify-between shrink-0 z-20 transition-all duration-300 ease-[var(--ease-apple-smooth)] ${
            scrolled
              ? 'bg-white/95 backdrop-blur-md shadow-sm border-b border-gray-200/80'
              : 'bg-white border-b border-gray-200'
          }`}
        >
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setSidebarOpen(true)}
              className="rounded border border-gray-200 p-1.5 text-gray-600 hover:bg-gray-100 lg:hidden"
            >
              <Menu className="h-4 w-4" />
            </button>
            <div>
              <h2 className="font-bold text-gray-800 text-base">
                Refund Intelligence &amp; Dispute Supervision
              </h2>
            </div>
          </div>

          <div className="flex items-center gap-3 text-xs">
            <span className="bg-blue-50 text-shipkart-blue font-bold px-2.5 py-1 rounded border border-blue-200">
              Platform Service
            </span>
            <span className="hidden sm:inline text-gray-500 font-medium">
              {currentUser?.email}
            </span>
          </div>
        </header>

        <main ref={mainRef} className="flex-1 p-6 overflow-y-auto">
          <div className="mx-auto w-full max-w-[1400px]">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
