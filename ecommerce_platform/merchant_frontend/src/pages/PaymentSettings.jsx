import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowRight,
  Check,
  CheckCircle2,
  Clock,
  Copy,
  DollarSign,
  Eye,
  EyeOff,
  Globe,
  Info,
  KeyRound,
  Loader2,
  Lock,
  Mail,
  RefreshCw,
  Save,
  ShieldAlert,
  ShieldCheck,
  Store,
  Trash2,
  Wallet,
  Zap,
} from 'lucide-react';
import { merchantPaymentsApi, merchantProductsApi } from '../services/api';

function isWebhookIdUrlLike(value) {
  const trimmed = String(value || '').trim();
  if (!trimmed) return false;
  return /^https?:\/\//i.test(trimmed) || trimmed.includes('/');
}

function formatUsd(value) {
  return `$${Number(value || 0).toFixed(2)}`;
}

function formatInr(value) {
  return `₹${Number(value || 0).toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function formatProviderMode(mode) {
  if (!mode) return 'Platform Sandbox';
  return mode
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(' ');
}

function settlementBadgeClass(status) {
  switch (status) {
    case 'CAPTURED':
    case 'SETTLED':
      return 'bg-green-100 text-green-700 border-green-200';
    case 'REFUNDED':
    case 'PARTIALLY_REFUNDED':
      return 'bg-purple-100 text-purple-700 border-purple-200';
    case 'EXCEPTION_REVIEW':
    case 'FAILED':
      return 'bg-red-100 text-red-700 border-red-200';
    case 'CANCELLED':
      return 'bg-gray-100 text-gray-600 border-gray-200';
    default:
      return 'bg-amber-50 text-amber-800 border-amber-200';
  }
}

function fulfillmentBadgeClass(status) {
  switch (status) {
    case 'DELIVERED':
      return 'bg-green-100 text-green-700';
    case 'ORDERED':
    case 'PACKED':
    case 'SHIPPED':
    case 'OUT_FOR_DELIVERY':
      return 'bg-blue-50 text-seller-blue';
    case 'CAPTURE_EXCEPTION':
    case 'CANCELLED':
      return 'bg-red-100 text-red-700';
    default:
      return 'bg-gray-100 text-gray-700';
  }
}

export default function PaymentSettings() {
  const [settings, setSettings] = useState(null);
  const [allocations, setAllocations] = useState([]);
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [allocationsLoading, setAllocationsLoading] = useState(false);
  const [loadError, setLoadError] = useState('');

  const [form, setForm] = useState({
    payout_paypal_email: '',
    payout_currency: 'USD',
    auto_refund_limit_usd: '150.00',
    return_window_days: '7',
    is_active: true,
  });

  // Direct PayPal REST Credentials state (secret is never prefilled from GET)
  const [paypalEnv, setPaypalEnv] = useState('SANDBOX');
  const [paypalClientId, setPaypalClientId] = useState('');
  const [paypalClientSecret, setPaypalClientSecret] = useState('');
  const [showClientSecret, setShowClientSecret] = useState(false);
  const [paypalWebhookId, setPaypalWebhookId] = useState('');
  const [copiedWebhookUrl, setCopiedWebhookUrl] = useState(false);

  const [paypalSaving, setPaypalSaving] = useState(false);
  const [paypalTesting, setPaypalTesting] = useState(false);
  const [paypalDisconnecting, setPaypalDisconnecting] = useState(false);
  const [paypalError, setPaypalError] = useState('');
  const [paypalSuccess, setPaypalSuccess] = useState('');

  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [saveSuccess, setSaveSuccess] = useState('');

  const hydrateForm = (data) => {
    setForm({
      payout_paypal_email: data?.payout_paypal_email || '',
      payout_currency: data?.payout_currency || 'USD',
      auto_refund_limit_usd:
        data?.auto_refund_limit_usd !== undefined && data?.auto_refund_limit_usd !== null
          ? Number(data.auto_refund_limit_usd).toFixed(2)
          : '150.00',
      return_window_days:
        data?.return_window_days !== undefined && data?.return_window_days !== null
          ? String(data.return_window_days)
          : '7',
      is_active: data?.is_active ?? true,
    });
  };

  const hydratePayPalFields = (data) => {
    setPaypalEnv(data?.paypal_environment === 'LIVE' ? 'LIVE' : 'SANDBOX');
    setPaypalClientId(data?.paypal_client_id || '');
    setPaypalWebhookId(data?.paypal_webhook_id || '');
    // Never prefill client secret from GET API
    setPaypalClientSecret('');
    setShowClientSecret(false);
  };

  const loadData = useCallback(async () => {
    setLoading(true);
    setLoadError('');
    try {
      const [settingsData, allocData, productData] = await Promise.all([
        merchantPaymentsApi.getSettings(),
        merchantPaymentsApi.getAllocations(),
        merchantProductsApi.myProducts().catch(() => []),
      ]);
      setSettings(settingsData);
      hydrateForm(settingsData);
      hydratePayPalFields(settingsData);
      setAllocations(Array.isArray(allocData) ? allocData : []);
      setProducts(Array.isArray(productData) ? productData : []);
    } catch (err) {
      setLoadError(err.message || 'Failed loading merchant payment settings.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const refreshAllocations = async () => {
    setAllocationsLoading(true);
    try {
      const allocData = await merchantPaymentsApi.getAllocations();
      setAllocations(Array.isArray(allocData) ? allocData : []);
    } catch (err) {
      setLoadError(err.message || 'Unable to refresh order allocations.');
    } finally {
      setAllocationsLoading(false);
    }
  };

  const buildPolicyPayload = () => {
    const parsedLimit = Number(form.auto_refund_limit_usd);
    if (Number.isNaN(parsedLimit) || parsedLimit < 0) {
      throw new Error('Auto-refund approval limit must be a non-negative USD amount.');
    }

    const parsedDays = Number(form.return_window_days);
    if (!Number.isInteger(parsedDays) || parsedDays < 1 || parsedDays > 90) {
      throw new Error('Return & refund window must be a whole number between 1 and 90 days.');
    }

    const trimmedEmail = form.payout_paypal_email.trim();
    return {
      payout_paypal_email: trimmedEmail ? trimmedEmail : null,
      payout_currency: 'USD',
      auto_refund_limit_usd: Number(parsedLimit.toFixed(2)),
      return_window_days: parsedDays,
      is_active: Boolean(form.is_active),
    };
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setSaveError('');
    setSaveSuccess('');

    let policyFields;
    try {
      policyFields = buildPolicyPayload();
    } catch (validationErr) {
      setSaveError(validationErr.message);
      return;
    }

    setSaving(true);
    try {
      // Do NOT send paypal_client_secret when saving payout preferences
      const updated = await merchantPaymentsApi.updateSettings(policyFields);
      setSettings(updated);
      hydrateForm(updated);
      setSaveSuccess('Payment & payout preferences saved successfully.');
    } catch (err) {
      setSaveError(err.message || 'Failed saving payment preferences.');
    } finally {
      setSaving(false);
    }
  };

  const webhookIdLooksLikeUrl = useMemo(() => isWebhookIdUrlLike(paypalWebhookId), [paypalWebhookId]);

  const ownedCount = useMemo(() => {
    if (!Array.isArray(products)) return 0;
    return products.filter((p) =>
      settings?.merchant_id != null ? p.merchant_id === settings.merchant_id : p.merchant_id != null
    ).length;
  }, [products, settings?.merchant_id]);

  const handleVerifyAndSavePayPal = async (e) => {
    e.preventDefault();
    setPaypalError('');
    setPaypalSuccess('');

    const trimmedClientId = paypalClientId.trim();
    const secret = paypalClientSecret.trim();
    const trimmedWebhookId = paypalWebhookId.trim();

    if (!trimmedClientId) {
      setPaypalError('PayPal Client ID is required.');
      return;
    }

    if (!secret && !settings?.has_client_secret) {
      setPaypalError('PayPal Client Secret is required when configuring credentials for the first time.');
      return;
    }

    if (isWebhookIdUrlLike(trimmedWebhookId)) {
      setPaypalError(
        'This looks like a Callback URL, not a PayPal Webhook ID like 8PT597350X239142B. Leave blank if optional or paste the Webhook ID generated in PayPal Dashboard.'
      );
      return;
    }

    let policyFields;
    try {
      policyFields = buildPolicyPayload();
    } catch (validationErr) {
      setPaypalError(validationErr.message);
      return;
    }

    setPaypalSaving(true);
    try {
      const updated = await merchantPaymentsApi.updateSettings({
        ...policyFields,
        paypal_environment: paypalEnv,
        paypal_client_id: trimmedClientId,
        ...(secret ? { paypal_client_secret: secret } : {}),
        paypal_webhook_id: trimmedWebhookId ? trimmedWebhookId : null,
        verify_before_save: true,
      });
      setSettings(updated);
      hydrateForm(updated);
      hydratePayPalFields(updated);
      const verifiedNote = updated?.credential_verified_at
        ? ` Verified on ${new Date(updated.credential_verified_at).toLocaleString()}.`
        : '';
      setPaypalSuccess(`PayPal REST credentials verified and saved.${verifiedNote}`);
    } catch (err) {
      setPaypalError(err.message || 'Failed verifying and saving PayPal credentials.');
    } finally {
      setPaypalSaving(false);
    }
  };

  const handleTestSavedConnection = async () => {
    setPaypalError('');
    setPaypalSuccess('');
    setPaypalTesting(true);
    try {
      const verifyResult = await merchantPaymentsApi.verifyPayPal({});
      const refreshed = await merchantPaymentsApi.getSettings();
      setSettings(refreshed);
      hydrateForm(refreshed);
      hydratePayPalFields(refreshed);
      const verifiedAt = refreshed?.credential_verified_at || verifyResult?.credential_verified_at;
      const verifiedNote = verifiedAt
        ? ` Verified on ${new Date(verifiedAt).toLocaleString()}.`
        : '';
      setPaypalSuccess(`PayPal REST API connection test succeeded.${verifiedNote}`);
    } catch (err) {
      setPaypalError(err.message || 'PayPal connection test failed.');
    } finally {
      setPaypalTesting(false);
    }
  };

  const handleDisconnectKeys = async () => {
    if (
      !window.confirm(
        'Disconnect your Direct PayPal REST credentials? Direct PayPal checkouts for your products will become inactive until new keys are saved.'
      )
    ) {
      return;
    }

    setPaypalError('');
    setPaypalSuccess('');
    setPaypalDisconnecting(true);
    try {
      const res = await merchantPaymentsApi.clearPayPalCredentials();
      const refreshed =
        res && typeof res === 'object' && 'paypal_configured' in res
          ? res
          : await merchantPaymentsApi.getSettings();
      setSettings(refreshed);
      hydrateForm(refreshed);
      hydratePayPalFields(refreshed);
      setPaypalSuccess('Direct PayPal REST credentials disconnected.');
    } catch (err) {
      setPaypalError(err.message || 'Failed disconnecting PayPal credentials.');
    } finally {
      setPaypalDisconnecting(false);
    }
  };

  const webhookEndpointUrl = useMemo(() => {
    const baseUrl =
      import.meta.env.VITE_API_URL ||
      (typeof window !== 'undefined' ? window.location.origin : '');
    const path =
      settings?.webhook_callback_path ||
      '/api/v1/webhooks/paypal/' + (settings?.merchant_id ?? '');
    return `${baseUrl}${path}`;
  }, [settings?.webhook_callback_path, settings?.merchant_id]);

  const handleCopyWebhookUrl = async () => {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(webhookEndpointUrl);
      } else {
        const textArea = document.createElement('textarea');
        textArea.value = webhookEndpointUrl;
        textArea.style.position = 'fixed';
        textArea.style.opacity = '0';
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
      }
      setCopiedWebhookUrl(true);
      setTimeout(() => setCopiedWebhookUrl(false), 2000);
    } catch {
      setPaypalError('Unable to copy Webhook Endpoint URL to clipboard.');
    }
  };

  const paypalStatus = useMemo(() => {
    if (settings?.paypal_configured && settings?.credential_verified_at) {
      return {
        label: 'Verified & Live',
        pillClass: 'bg-emerald-100 text-emerald-800 border border-emerald-200',
        bannerBorder: 'border-emerald-200',
        headerBg: 'bg-emerald-50/60',
        iconBg: 'bg-emerald-100 text-emerald-700',
        isVerified: true,
      };
    }
    if (settings?.paypal_configured && !settings?.credential_verified_at) {
      return {
        label: 'Credentials Saved (Unverified)',
        pillClass: 'bg-amber-100 text-amber-800 border border-amber-200',
        bannerBorder: 'border-amber-200',
        headerBg: 'bg-amber-50/60',
        iconBg: 'bg-amber-100 text-amber-700',
        isVerified: false,
      };
    }
    return {
      label: 'Not Configured — Direct PayPal Inactive',
      pillClass: 'bg-gray-100 text-gray-700 border border-gray-200',
      bannerBorder: 'border-gray-200',
      headerBg: 'bg-gray-50',
      iconBg: 'bg-amber-100 text-amber-700',
      isVerified: false,
    };
  }, [settings?.paypal_configured, settings?.credential_verified_at]);

  const ledgerTotals = useMemo(() => {
    return allocations.reduce(
      (acc, row) => ({
        netUsd: acc.netUsd + Number(row.net_merchant_usd || 0),
        refundedUsd: acc.refundedUsd + Number(row.refunded_usd || 0),
        grossUsd: acc.grossUsd + Number(row.gross_usd || 0),
      }),
      { netUsd: 0, refundedUsd: 0, grossUsd: 0 }
    );
  }, [allocations]);

  if (loading) {
    return (
      <div className="bg-white rounded shadow-sm border border-gray-100 p-8 flex items-center justify-center gap-2 text-xs text-gray-500">
        <Loader2 className="w-4 h-4 animate-spin text-seller-blue" />
        <span>Loading payment settings & settlement allocations...</span>
      </div>
    );
  }

  const paypalBusy = paypalSaving || paypalTesting || paypalDisconnecting;

  return (
    <div className="space-y-5">
      {/* Page Header */}
      <div className="bg-white p-4 rounded shadow-sm border border-gray-100 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 className="font-bold text-base text-gray-800">
            Payments, Payout Preferences & Settlement Ledger
          </h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Connect your Direct PayPal REST App credentials, configure automated refund approval caps,
            and inspect order-level USD settlement allocations.
          </p>
        </div>
        <button
          type="button"
          onClick={loadData}
          className="self-start sm:self-auto inline-flex items-center gap-1.5 px-3 py-1.5 rounded border border-gray-200 text-xs font-semibold text-gray-700 hover:bg-gray-50 transition"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          <span>Reload</span>
        </button>
      </div>

      {loadError && (
        <div
          role="alert"
          className="bg-red-50 border border-red-200 text-red-800 rounded p-3.5 text-xs flex items-center justify-between gap-3"
        >
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-red-600 flex-shrink-0" />
            <span>{loadError}</span>
          </div>
          <button
            type="button"
            onClick={loadData}
            className="font-bold underline hover:text-red-900"
          >
            Retry
          </button>
        </div>
      )}

      {settings?.paypal_configured && ownedCount === 0 && (
        <div className="bg-amber-50 border border-amber-200 text-amber-900 rounded shadow-sm p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-full bg-amber-100 text-amber-700 flex-shrink-0">
              <Store className="w-4 h-4" />
            </div>
            <div className="space-y-0.5 text-xs">
              <p className="font-bold text-amber-950">
                Your store owns 0 product listings yet
              </p>
              <p className="text-amber-800 leading-relaxed">
                Your Direct PayPal keys are Verified &amp; Live, but your store owns 0 listings yet.
                Claim starter items or publish a product in My Listings so customers can check out
                with your PayPal account.
              </p>
            </div>
          </div>
          <Link
            to="/listings"
            className="inline-flex items-center justify-center gap-1.5 bg-seller-blue hover:bg-blue-700 text-white text-xs font-bold px-4 py-2 rounded shadow transition flex-shrink-0"
          >
            <span>Go to My Listings</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      )}

      {/* Direct PayPal REST Credentials Setup */}
      <form
        onSubmit={handleVerifyAndSavePayPal}
        className={`bg-white rounded shadow-sm border overflow-hidden ${paypalStatus.bannerBorder}`}
      >
        <div
          className={`px-5 py-4 border-b flex flex-col lg:flex-row lg:items-center justify-between gap-4 ${paypalStatus.headerBg}`}
        >
          <div className="flex items-start gap-3">
            <div className={`p-2 rounded-full flex-shrink-0 ${paypalStatus.iconBg}`}>
              {paypalStatus.isVerified ? (
                <ShieldCheck className="w-5 h-5" />
              ) : (
                <KeyRound className="w-5 h-5" />
              )}
            </div>
            <div className="space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-sm font-bold text-gray-900">
                  Direct PayPal REST Credentials Setup
                </h3>
                <span
                  className={`text-[11px] font-bold px-2.5 py-0.5 rounded-full ${paypalStatus.pillClass}`}
                >
                  {paypalStatus.label}
                </span>
              </div>
              <p className="text-xs text-gray-600 leading-relaxed max-w-3xl">
                Customer checkouts for your products settle directly into your configured PayPal
                account using your REST App credentials. Your Client Secret is encrypted with
                AES-256-GCM before storage and is never shown again.
              </p>
              {settings?.credential_verified_at && (
                <p className="text-[11px] text-emerald-700 font-semibold flex items-center gap-1 pt-0.5">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>
                    Last verified: {new Date(settings.credential_verified_at).toLocaleString()}
                  </span>
                </p>
              )}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-xs flex-shrink-0">
            <div className="bg-white border border-gray-200 rounded px-3 py-1.5">
              <span className="text-gray-400 text-[10px] uppercase font-bold block">Environment</span>
              <span className="font-bold text-gray-800">
                {settings?.paypal_environment || paypalEnv}
              </span>
            </div>
            <div className="bg-white border border-gray-200 rounded px-3 py-1.5">
              <span className="text-gray-400 text-[10px] uppercase font-bold block">Provider Mode</span>
              <span className="font-bold text-seller-blue">
                {formatProviderMode(settings?.payment_provider_mode)}
              </span>
            </div>
          </div>
        </div>

        <div className="p-5 space-y-5">
          {paypalError && (
            <div
              role="alert"
              className="bg-red-50 border border-red-200 text-red-800 rounded p-3 text-xs flex items-center gap-2"
            >
              <ShieldAlert className="w-4 h-4 text-red-600 flex-shrink-0" />
              <span>{paypalError}</span>
            </div>
          )}

          {paypalSuccess && (
            <div
              role="status"
              className="bg-emerald-50 border border-emerald-200 text-emerald-800 rounded p-3 text-xs flex items-center gap-2"
            >
              <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
              <span>{paypalSuccess}</span>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {/* PayPal Environment */}
            <div className="space-y-1.5">
              <label
                htmlFor="paypal_environment"
                className="block text-xs font-bold text-gray-700 uppercase"
              >
                PayPal Environment
              </label>
              <div className="relative">
                <Globe className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                <select
                  id="paypal_environment"
                  value={paypalEnv}
                  onChange={(e) => setPaypalEnv(e.target.value)}
                  className="w-full border border-gray-300 rounded pl-9 pr-3 py-2 text-xs text-gray-800 bg-white focus:border-seller-blue focus:outline-none"
                >
                  <option value="SANDBOX">SANDBOX — PayPal Sandbox Testing</option>
                  <option value="LIVE">LIVE — Production Live</option>
                </select>
              </div>
              <p className="text-[11px] text-gray-500">
                Use Sandbox keys for testing or Live keys for production customer settlements.
              </p>
            </div>

            {/* PayPal Client ID */}
            <div className="space-y-1.5">
              <label
                htmlFor="paypal_client_id"
                className="block text-xs font-bold text-gray-700 uppercase"
              >
                PayPal Client ID
              </label>
              <div className="relative">
                <KeyRound className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                <input
                  id="paypal_client_id"
                  type="text"
                  autoComplete="off"
                  placeholder="AabC123... (PayPal REST App Client ID)"
                  value={paypalClientId}
                  onChange={(e) => setPaypalClientId(e.target.value)}
                  className="w-full border border-gray-300 rounded pl-9 pr-3 py-2 text-xs font-mono text-gray-800 focus:border-seller-blue focus:outline-none"
                />
              </div>
              <p className="text-[11px] text-gray-500">
                Public identifier from your PayPal Developer Dashboard REST App.
              </p>
            </div>

            {/* PayPal Client Secret */}
            <div className="space-y-1.5 md:col-span-2">
              <div className="flex flex-wrap items-center justify-between gap-1.5">
                <label
                  htmlFor="paypal_client_secret"
                  className="block text-xs font-bold text-gray-700 uppercase"
                >
                  PayPal Client Secret
                </label>
                {settings?.has_client_secret && (
                  <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-200">
                    <Lock className="w-3 h-3" />
                    <span>
                      Secret encrypted &amp; saved (ending ••••{settings.client_secret_last4 || '****'})
                    </span>
                  </span>
                )}
              </div>
              <div className="relative">
                <Lock className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                <input
                  id="paypal_client_secret"
                  type={showClientSecret ? 'text' : 'password'}
                  autoComplete="new-password"
                  placeholder={
                    settings?.has_client_secret
                      ? 'Leave blank to keep stored secret, or enter new secret to rotate'
                      : 'Enter your PayPal REST App Client Secret'
                  }
                  value={paypalClientSecret}
                  onChange={(e) => setPaypalClientSecret(e.target.value)}
                  className="w-full border border-gray-300 rounded pl-9 pr-10 py-2 text-xs font-mono text-gray-800 focus:border-seller-blue focus:outline-none"
                />
                <button
                  type="button"
                  onClick={() => setShowClientSecret((prev) => !prev)}
                  aria-label={showClientSecret ? 'Hide client secret' : 'Show client secret'}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-700 p-1"
                >
                  {showClientSecret ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              <p className="text-[11px] text-gray-500">
                Encrypted with AES-256-GCM at rest. Never returned by the API once stored.
              </p>
            </div>
          </div>

          {/* Two-Step Webhook Setup (Optional) */}
          <div className="bg-gray-50 border border-gray-200 rounded p-4 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-200 pb-2.5">
              <div>
                <h4 className="text-xs font-bold text-gray-800 uppercase">
                  Webhook Verification Setup <span className="text-gray-400 font-normal">(Optional)</span>
                </h4>
                <p className="text-[11px] text-gray-500 mt-0.5">
                  Follow Step 1 then Step 2 below only if you want cryptographic webhook verification.
                </p>
              </div>
            </div>

            {/* Step 1: Callback URL to register in PayPal */}
            <div className="space-y-1.5">
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center px-2 py-0.5 rounded bg-blue-50 text-seller-blue border border-blue-200 text-[10px] font-bold uppercase">
                  Step 1
                </span>
                <label
                  htmlFor="webhook_endpoint_url"
                  className="block text-xs font-bold text-gray-700"
                >
                  Copy Callback URL to register in PayPal Developer Dashboard
                </label>
              </div>
              <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
                <input
                  id="webhook_endpoint_url"
                  type="text"
                  readOnly
                  value={webhookEndpointUrl}
                  onClick={(e) => e.target.select()}
                  className="flex-1 bg-white border border-gray-300 rounded px-3 py-2 text-xs font-mono text-gray-700 focus:outline-none"
                />
                <button
                  type="button"
                  onClick={handleCopyWebhookUrl}
                  className="inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded border border-gray-300 bg-white hover:bg-gray-100 text-xs font-bold text-gray-700 transition flex-shrink-0"
                >
                  {copiedWebhookUrl ? (
                    <>
                      <Check className="w-3.5 h-3.5 text-emerald-600" />
                      <span className="text-emerald-700">Copied!</span>
                    </>
                  ) : (
                    <>
                      <Copy className="w-3.5 h-3.5" />
                      <span>Copy URL</span>
                    </>
                  )}
                </button>
              </div>
              <p className="text-[11px] text-gray-500">
                Add this callback endpoint under Webhooks in your PayPal REST App to receive capture
                and refund notifications.
              </p>
            </div>

            {/* Step 2: PayPal Webhook ID returned by PayPal */}
            <div className="space-y-1.5 pt-2 border-t border-gray-200">
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center px-2 py-0.5 rounded bg-gray-200 text-gray-700 text-[10px] font-bold uppercase">
                  Step 2
                </span>
                <label
                  htmlFor="paypal_webhook_id"
                  className="block text-xs font-bold text-gray-700"
                >
                  PayPal Webhook ID <span className="text-gray-400 font-normal">(Optional)</span>
                </label>
              </div>
              <input
                id="paypal_webhook_id"
                type="text"
                autoComplete="off"
                placeholder="8PT597350X239142B (or leave blank)"
                value={paypalWebhookId}
                onChange={(e) => setPaypalWebhookId(e.target.value)}
                className={`w-full bg-white border rounded px-3 py-2 text-xs font-mono text-gray-800 focus:outline-none ${
                  webhookIdLooksLikeUrl
                    ? 'border-amber-400 focus:border-amber-500 bg-amber-50/40'
                    : 'border-gray-300 focus:border-seller-blue'
                }`}
              />
              {webhookIdLooksLikeUrl && (
                <div
                  role="alert"
                  className="bg-amber-50 border border-amber-300 text-amber-900 rounded p-2.5 text-xs flex items-start gap-2"
                >
                  <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
                  <span>
                    This looks like a Callback URL, not a PayPal Webhook ID like{' '}
                    <code className="font-mono font-bold">8PT597350X239142B</code>. Leave blank if
                    optional or paste the Webhook ID generated in PayPal Dashboard.
                  </span>
                </div>
              )}
              <p className="text-[11px] text-gray-500">
                Paste PayPal&apos;s generated Webhook ID above — leave blank if testing locally
                without webhooks.
              </p>
            </div>
          </div>

          {/* Credential Action Buttons */}
          <div className="border-t pt-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2.5">
              <button
                type="submit"
                disabled={paypalBusy || webhookIdLooksLikeUrl}
                className="bg-seller-blue hover:bg-blue-700 disabled:opacity-60 text-white text-xs font-bold px-4 py-2.5 rounded shadow flex items-center gap-2 transition"
              >
                {paypalSaving ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <ShieldCheck className="w-4 h-4" />
                )}
                <span>{paypalSaving ? 'Verifying & Saving...' : 'Verify & Save PayPal Keys'}</span>
              </button>

              {settings?.paypal_configured && (
                <button
                  type="button"
                  onClick={handleTestSavedConnection}
                  disabled={paypalBusy}
                  className="bg-white hover:bg-gray-50 disabled:opacity-60 text-gray-800 border border-gray-300 text-xs font-bold px-4 py-2.5 rounded flex items-center gap-2 transition"
                >
                  {paypalTesting ? (
                    <Loader2 className="w-4 h-4 animate-spin text-seller-blue" />
                  ) : (
                    <Zap className="w-4 h-4 text-seller-blue" />
                  )}
                  <span>{paypalTesting ? 'Testing...' : 'Test Saved Connection'}</span>
                </button>
              )}
            </div>

            {settings?.paypal_configured && (
              <button
                type="button"
                onClick={handleDisconnectKeys}
                disabled={paypalBusy}
                className="bg-white hover:bg-red-50 disabled:opacity-60 text-red-700 border border-red-200 text-xs font-bold px-3.5 py-2 rounded flex items-center gap-1.5 transition"
              >
                {paypalDisconnecting ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Trash2 className="w-3.5 h-3.5" />
                )}
                <span>{paypalDisconnecting ? 'Disconnecting...' : 'Disconnect Keys'}</span>
              </button>
            )}
          </div>
        </div>
      </form>

      {/* Payout & Auto-Refund Preferences Form */}
      <form
        onSubmit={handleSave}
        className="bg-white rounded shadow-sm border border-gray-100 overflow-hidden"
      >
        <div className="px-5 py-3.5 border-b bg-gray-50 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Wallet className="w-4 h-4 text-seller-blue" />
            <h3 className="font-bold text-sm text-gray-800">
              Payout Destination & Auto-Refund Policy Controls
            </h3>
          </div>
          {settings?.updated_at && (
            <span className="text-[11px] text-gray-500">
              Last updated: {new Date(settings.updated_at).toLocaleString()}
            </span>
          )}
        </div>

        <div className="p-5 space-y-5">
          {saveError && (
            <div
              role="alert"
              className="bg-red-50 border border-red-200 text-red-800 rounded p-3 text-xs flex items-center gap-2"
            >
              <AlertTriangle className="w-4 h-4 text-red-600 flex-shrink-0" />
              <span>{saveError}</span>
            </div>
          )}

          {saveSuccess && (
            <div
              role="status"
              className="bg-emerald-50 border border-emerald-200 text-emerald-800 rounded p-3 text-xs flex items-center gap-2"
            >
              <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
              <span>{saveSuccess}</span>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {/* Settlement PayPal Business Email */}
            <div className="space-y-1.5">
              <label
                htmlFor="payout_paypal_email"
                className="block text-xs font-bold text-gray-700 uppercase"
              >
                Settlement PayPal Business Email
              </label>
              <div className="relative">
                <Mail className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  id="payout_paypal_email"
                  type="email"
                  placeholder="merchant-payouts@business.example.com"
                  value={form.payout_paypal_email}
                  onChange={(e) =>
                    setForm((prev) => ({ ...prev, payout_paypal_email: e.target.value }))
                  }
                  className="w-full border border-gray-300 rounded pl-9 pr-3 py-2 text-xs text-gray-800 focus:border-seller-blue focus:outline-none"
                />
              </div>
              <p className="text-[11px] text-gray-500">
                Optional Sandbox recipient email used for merchant settlement attribution records.
              </p>
            </div>

            {/* Payout Currency (Fixed USD for Sandbox) */}
            <div className="space-y-1.5">
              <label className="block text-xs font-bold text-gray-700 uppercase">
                Settlement Ledger Currency
              </label>
              <div className="flex items-center justify-between border border-gray-200 bg-gray-50 rounded px-3 py-2 text-xs">
                <span className="font-bold text-gray-800">USD — US Dollar</span>
                <span className="text-[11px] font-semibold px-2 py-0.5 rounded bg-blue-50 text-seller-blue border border-blue-100">
                  Sandbox Standard
                </span>
              </div>
              <p className="text-[11px] text-gray-500">
                PayPal Sandbox platform allocations and refunds are accounted in USD.
              </p>
            </div>

            {/* Auto-Refund Approval Limit */}
            <div className="space-y-1.5">
              <label
                htmlFor="auto_refund_limit_usd"
                className="block text-xs font-bold text-gray-700 uppercase"
              >
                Auto-Refund Approval Limit (USD)
              </label>
              <div className="relative">
                <DollarSign className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  id="auto_refund_limit_usd"
                  type="number"
                  min="0"
                  step="0.01"
                  required
                  value={form.auto_refund_limit_usd}
                  onChange={(e) =>
                    setForm((prev) => ({ ...prev, auto_refund_limit_usd: e.target.value }))
                  }
                  className="w-full border border-gray-300 rounded pl-9 pr-14 py-2 text-xs text-gray-800 focus:border-seller-blue focus:outline-none"
                />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[11px] font-bold text-gray-400">
                  USD
                </span>
              </div>
              <p className="text-[11px] text-gray-500">
                Maximum USD return value eligible for automated refund approval without manual hold.
              </p>
            </div>

            {/* Refund Window Days */}
            <div className="space-y-1.5">
              <label
                htmlFor="return_window_days"
                className="block text-xs font-bold text-gray-700 uppercase"
              >
                Refund Eligibility Window (Days)
              </label>
              <div className="relative">
                <Clock className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  id="return_window_days"
                  type="number"
                  min="1"
                  max="90"
                  step="1"
                  required
                  value={form.return_window_days}
                  onChange={(e) =>
                    setForm((prev) => ({ ...prev, return_window_days: e.target.value }))
                  }
                  className="w-full border border-gray-300 rounded pl-9 pr-14 py-2 text-xs text-gray-800 focus:border-seller-blue focus:outline-none"
                />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[11px] font-bold text-gray-400">
                  DAYS
                </span>
              </div>
              <p className="text-[11px] text-gray-500">
                Allowed between 1 and 90 days from delivery confirmation.
              </p>
            </div>
          </div>

          {/* Active Payout Ledger Tracking Toggle */}
          <div className="border-t pt-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <label className="flex items-start gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(e) =>
                  setForm((prev) => ({ ...prev, is_active: e.target.checked }))
                }
                className="mt-0.5 h-4 w-4 rounded border-gray-300 text-seller-blue accent-seller-blue"
              />
              <div>
                <span className="block text-xs font-bold text-gray-800">
                  Enable Active Payout Ledger Tracking
                </span>
                <span className="block text-[11px] text-gray-500 mt-0.5">
                  Automatically record gross revenue, platform fees, net USD settlement, and refund
                  adjustments for incoming PayPal orders.
                </span>
              </div>
            </label>

            <button
              type="submit"
              disabled={saving}
              className="bg-seller-blue hover:bg-blue-700 disabled:opacity-60 text-white text-xs font-bold px-5 py-2.5 rounded shadow flex items-center justify-center gap-2 transition flex-shrink-0"
            >
              {saving ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Save className="w-4 h-4" />
              )}
              <span>{saving ? 'Saving...' : 'Save Payment Preferences'}</span>
            </button>
          </div>
        </div>
      </form>

      {/* Live Per-Order Merchant Allocations Table */}
      <div className="bg-white rounded shadow-sm border border-gray-100 overflow-hidden">
        <div className="px-5 py-3.5 border-b bg-gray-50 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h3 className="font-bold text-sm text-gray-800">
              Per-Order Merchant Settlement Allocations
            </h3>
            <p className="text-[11px] text-gray-500">
              Live settlement breakdown across catalog INR amounts, USD captures, and refund deductions.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2 text-xs bg-white border border-gray-200 rounded px-3 py-1">
              <span className="text-gray-500">Net USD:</span>
              <span className="font-bold text-emerald-700">{formatUsd(ledgerTotals.netUsd)}</span>
            </div>
            <div className="flex items-center gap-2 text-xs bg-white border border-gray-200 rounded px-3 py-1">
              <span className="text-gray-500">Refunded:</span>
              <span className="font-bold text-red-600">{formatUsd(ledgerTotals.refundedUsd)}</span>
            </div>
            <button
              type="button"
              onClick={refreshAllocations}
              disabled={allocationsLoading}
              className="inline-flex items-center gap-1.5 text-xs font-bold text-seller-blue hover:underline disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${allocationsLoading ? 'animate-spin' : ''}`} />
              <span>Refresh</span>
            </button>
          </div>
        </div>

        {allocations.length === 0 ? (
          <div className="p-10 text-center text-xs text-gray-500 space-y-2">
            <Info className="w-8 h-8 text-gray-300 mx-auto" />
            <p className="font-semibold text-gray-700">No order allocations recorded yet.</p>
            <p className="text-gray-400">
              Completed and pending customer orders containing your products will appear here with
              their USD settlement details.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-gray-50/80 border-b border-gray-200 text-[11px] font-bold text-gray-500 uppercase">
                  <th className="py-3 px-4">Order #</th>
                  <th className="py-3 px-4 text-right">Gross (INR)</th>
                  <th className="py-3 px-4 text-right">Gross (USD)</th>
                  <th className="py-3 px-4 text-right">Platform Fee</th>
                  <th className="py-3 px-4 text-right">Net Merchant (USD)</th>
                  <th className="py-3 px-4 text-right">Refunded (USD)</th>
                  <th className="py-3 px-4">Fulfillment</th>
                  <th className="py-3 px-4">Settlement</th>
                  <th className="py-3 px-4">PayPal Capture ID</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {allocations.map((alloc) => (
                  <tr key={alloc.id} className="hover:bg-gray-50/70 transition">
                    <td className="py-3 px-4 whitespace-nowrap">
                      <span className="font-bold text-seller-blue">
                        {alloc.order_number || `#${alloc.order_id}`}
                      </span>
                      {alloc.payment_status && (
                        <span className="block text-[10px] text-gray-400 mt-0.5">
                          {alloc.payment_status}
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-right whitespace-nowrap font-medium text-gray-800">
                      {formatInr(alloc.gross_inr)}
                    </td>
                    <td className="py-3 px-4 text-right whitespace-nowrap font-semibold text-gray-900">
                      {formatUsd(alloc.gross_usd)}
                    </td>
                    <td className="py-3 px-4 text-right whitespace-nowrap text-gray-500">
                      {formatUsd(alloc.platform_fee_usd)}
                    </td>
                    <td className="py-3 px-4 text-right whitespace-nowrap font-bold text-emerald-700">
                      {formatUsd(alloc.net_merchant_usd)}
                    </td>
                    <td className="py-3 px-4 text-right whitespace-nowrap font-semibold text-red-600">
                      {formatUsd(alloc.refunded_usd)}
                    </td>
                    <td className="py-3 px-4 whitespace-nowrap">
                      <span
                        className={`inline-block text-[11px] font-bold px-2 py-0.5 rounded ${fulfillmentBadgeClass(
                          alloc.fulfillment_status
                        )}`}
                      >
                        {alloc.fulfillment_status}
                      </span>
                    </td>
                    <td className="py-3 px-4 whitespace-nowrap">
                      <span
                        className={`inline-block text-[11px] font-bold px-2 py-0.5 rounded border ${settlementBadgeClass(
                          alloc.settlement_status
                        )}`}
                      >
                        {alloc.settlement_status}
                      </span>
                    </td>
                    <td className="py-3 px-4 whitespace-nowrap">
                      {alloc.paypal_capture_id ? (
                        <code className="text-[11px] font-mono bg-gray-100 text-gray-800 px-2 py-0.5 rounded">
                          {alloc.paypal_capture_id}
                        </code>
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
