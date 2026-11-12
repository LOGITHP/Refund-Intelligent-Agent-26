import { useEffect, useState } from 'react';
import { Lock, ShieldCheck, Store, UserPlus } from 'lucide-react';
import { OpsApiError, opsApi } from '../api/client';
import type { PlatformUser } from '../types/api';

interface PlatformLoginScreenProps {
  onAuthenticated: (user: PlatformUser) => void;
}

export function PlatformLoginScreen({ onAuthenticated }: PlatformLoginScreenProps) {
  const [checkingStatus, setCheckingStatus] = useState(true);
  const [hasOperators, setHasOperators] = useState<boolean>(true);
  const [mode, setMode] = useState<'login' | 'setup'>('login');

  const [fullName, setFullName] = useState('Platform Operations Lead');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    opsApi
      .getAuthStatus()
      .then((res) => {
        if (!active) return;
        setHasOperators(res.has_operators);
        setMode(res.has_operators ? 'login' : 'setup');
      })
      .catch(() => {
        if (!active) return;
        setHasOperators(true);
        setMode('login');
      })
      .finally(() => {
        if (active) setCheckingStatus(false);
      });
    return () => {
      active = false;
    };
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    const cleanEmail = email.trim().toLowerCase();
    if (!cleanEmail || !cleanEmail.includes('@')) {
      setError('Please enter a valid platform operator email address.');
      return;
    }
    if (mode === 'setup') {
      if (password.length < 8) {
        setError('Password must be at least 8 characters long.');
        return;
      }
      if (password !== confirmPassword) {
        setError('Passwords do not match.');
        return;
      }
    } else if (!password) {
      setError('Please enter your password.');
      return;
    }

    setSubmitting(true);
    try {
      const auth =
        mode === 'setup'
          ? await opsApi.setupFirstOperator({
              email: cleanEmail,
              password,
              full_name: fullName.trim() || 'Platform Operations Lead',
            })
          : await opsApi.login({
              email: cleanEmail,
              password,
            });
      onAuthenticated(auth.user);
    } catch (err) {
      if (err instanceof OpsApiError) {
        if (err.status === 409) {
          setHasOperators(true);
          setMode('login');
        }
        setError(err.message);
      } else {
        setError('Authentication failed. Please try again.');
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-shipkart-navy flex items-center justify-center p-4">
      <div className="bg-white rounded shadow-2xl max-w-4xl w-full grid grid-cols-1 md:grid-cols-2 overflow-hidden apple-panel-enter">
        {/* Left Brand Banner (Matches Shipkart Seller Hub Login) */}
        <div className="bg-shipkart-navyHover text-white p-10 flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-2.5 mb-6">
              <Store className="w-8 h-8 text-shipkart-yellow" />
              <div>
                <h1 className="font-black text-2xl leading-none tracking-tight">Shipkart</h1>
                <span className="text-xs font-bold text-shipkart-yellow uppercase tracking-widest">
                  Refund Intelligence
                </span>
              </div>
            </div>

            <h2 className="text-xl font-bold leading-snug">
              Dispute verification, carrier delays &amp; payout supervision
            </h2>
            <p className="text-blue-200 text-sm mt-3 leading-relaxed">
              Dedicated Platform Operations Portal — separated from Merchant Seller and Customer
              accounts. Investigate return timelines, test card-rail and regulatory scenarios, and
              audit 3-agent AI briefs in one workspace.
            </p>
          </div>

          <div className="bg-white/10 border border-white/15 rounded p-4 text-xs space-y-2 mt-8">
            <div className="flex items-center gap-2 text-shipkart-yellow font-bold">
              <ShieldCheck className="w-4 h-4 shrink-0" />
              <span>Secret Isolation &amp; REF-001 Guardrail</span>
            </div>
            <p className="text-gray-200 leading-relaxed">
              Merchant PayPal credentials remain sealed inside the commerce vault. AI agents only
              advise; explicit Merchant Seller approval is required before any refund executes.
            </p>
          </div>
        </div>

        {/* Right Form */}
        <div className="p-8 md:p-10 flex flex-col justify-between bg-white">
          <div>
            <h3 className="text-xl font-bold text-gray-800 mb-1">
              {mode === 'setup' ? 'Initialize First Platform Operator' : 'Platform Service Sign In'}
            </h3>
            <p className="text-xs text-gray-500 mb-5">
              {mode === 'setup'
                ? 'One-time setup to create the primary Refund Operations administrator.'
                : 'Sign in with your dedicated Refund Intelligence service credentials.'}
            </p>

            {!checkingStatus && !hasOperators && (
              <div className="mb-4 rounded border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-shipkart-blue font-medium">
                No platform operator account exists yet. Complete one-time setup below to begin.
              </div>
            )}

            {error && (
              <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-700 text-xs rounded apple-anim-fade">
                {error}
              </div>
            )}

            {checkingStatus ? (
              <div className="py-10 text-center text-xs text-gray-500">
                Checking platform service status…
              </div>
            ) : (
              <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
                {mode === 'setup' && (
                  <div>
                    <label className="text-xs font-bold text-gray-600 uppercase">Full Name</label>
                    <input
                      type="text"
                      required
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      placeholder="Platform Operations Lead"
                      className="w-full mt-1 border border-gray-300 rounded px-3 py-2 text-sm text-gray-900 focus:border-shipkart-blue focus:outline-none"
                    />
                  </div>
                )}

                <div>
                  <label className="text-xs font-bold text-gray-600 uppercase">
                    Operator Email
                  </label>
                  <input
                    type="email"
                    required
                    autoComplete="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="operator@company.com"
                    className="w-full mt-1 border border-gray-300 rounded px-3 py-2 text-sm text-gray-900 focus:border-shipkart-blue focus:outline-none"
                  />
                </div>

                <div>
                  <label className="text-xs font-bold text-gray-600 uppercase">Password</label>
                  <input
                    type="password"
                    required
                    autoComplete={mode === 'setup' ? 'new-password' : 'current-password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder={mode === 'setup' ? 'Minimum 8 characters' : 'Enter password'}
                    className="w-full mt-1 border border-gray-300 rounded px-3 py-2 text-sm text-gray-900 focus:border-shipkart-blue focus:outline-none"
                  />
                </div>

                {mode === 'setup' && (
                  <div>
                    <label className="text-xs font-bold text-gray-600 uppercase">
                      Confirm Password
                    </label>
                    <input
                      type="password"
                      required
                      autoComplete="new-password"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      placeholder="Re-enter password"
                      className="w-full mt-1 border border-gray-300 rounded px-3 py-2 text-sm text-gray-900 focus:border-shipkart-blue focus:outline-none"
                    />
                  </div>
                )}

                <button
                  type="submit"
                  disabled={submitting}
                  className="w-full flex items-center justify-center gap-2 bg-shipkart-blue hover:bg-shipkart-blueHover text-white font-bold py-2.5 rounded text-sm shadow transition-all duration-200 ease-[var(--ease-apple-smooth)] disabled:opacity-50"
                >
                  {mode === 'setup' ? (
                    <UserPlus className="w-4 h-4" />
                  ) : (
                    <Lock className="w-4 h-4" />
                  )}
                  {submitting
                    ? 'Authenticating...'
                    : mode === 'setup'
                    ? 'Initialize Operator & Sign In'
                    : 'Sign In to Refund Console'}
                </button>
              </form>
            )}
          </div>

          <div className="pt-5 text-center border-t border-gray-100 mt-6">
            <p className="text-[11px] text-gray-500">
              Authenticated via isolated platform JWT session
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
