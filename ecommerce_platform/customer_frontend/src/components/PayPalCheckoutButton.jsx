import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowRight,
  Info,
  Loader2,
  Lock,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react';
import { paymentsApi } from '../services/api';
import { useCart } from '../context/CartContext';

const PAYPAL_SDK_BASE = 'https://www.paypal.com/sdk/js';

function loadPayPalSdk(clientId, currency = 'USD') {
  const sdkSrc = `${PAYPAL_SDK_BASE}?client-id=${encodeURIComponent(
    clientId
  )}&currency=${encodeURIComponent(currency)}&intent=capture`;

  if (typeof window === 'undefined' || typeof document === 'undefined') {
    return Promise.reject(new Error('PayPal checkout is only available in a browser.'));
  }

  const existingScripts = Array.from(document.querySelectorAll('script[data-paypal-sdk="true"]'));
  let matchingScript = null;
  for (const script of existingScripts) {
    if (!matchingScript && script.src === sdkSrc && script.dataset.loaded !== 'error') {
      matchingScript = script;
    } else {
      script.remove();
    }
  }

  if (matchingScript) {
    if (window.paypal?.Buttons) {
      return Promise.resolve(window.paypal);
    }
    return new Promise((resolve, reject) => {
      matchingScript.addEventListener(
        'load',
        () => {
          if (window.paypal?.Buttons) resolve(window.paypal);
          else reject(new Error('PayPal checkout failed to initialize.'));
        },
        { once: true }
      );
      matchingScript.addEventListener(
        'error',
        () => {
          reject(new Error('Unable to load PayPal checkout script.'));
        },
        { once: true }
      );
    });
  }

  if (existingScripts.length > 0 && 'paypal' in window) {
    try {
      delete window.paypal;
    } catch {
      window.paypal = undefined;
    }
  }

  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = sdkSrc;
    script.async = true;
    script.dataset.paypalSdk = 'true';

    script.onload = () => {
      script.dataset.loaded = 'true';
      if (window.paypal?.Buttons) {
        resolve(window.paypal);
      } else {
        reject(new Error('PayPal checkout buttons are unavailable right now.'));
      }
    };

    script.onerror = () => {
      script.dataset.loaded = 'error';
      script.remove();
      reject(new Error('Unable to load PayPal checkout right now. Please try again.'));
    };

    document.head.appendChild(script);
  });
}

function formatInr(amount) {
  return Number(amount || 0).toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatUsd(amount) {
  return Number(amount || 0).toFixed(2);
}

export default function PayPalCheckoutButton({
  clientConfig,
  merchantGroup = null,
  loadingConfig = false,
  configError = '',
  selectedAddress,
  buyNowProductId = null,
  buyNowQty = 1,
  onRefreshConfig,
  onOrderCaptured,
  onSwitchToStandard,
}) {
  const navigate = useNavigate();
  const { refreshCart } = useCart();

  const activeConfig = merchantGroup || clientConfig;

  const containerRef = useRef(null);
  const buttonsInstanceRef = useRef(null);
  const pendingOrderIdRef = useRef(null);
  const createErrorHandledRef = useRef(false);

  const latestPropsRef = useRef({
    selectedAddress,
    buyNowProductId,
    buyNowQty,
    refreshCart,
    navigate,
    onRefreshConfig,
    onOrderCaptured,
    activeConfig,
  });

  useEffect(() => {
    latestPropsRef.current = {
      selectedAddress,
      buyNowProductId,
      buyNowQty,
      refreshCart,
      navigate,
      onRefreshConfig,
      onOrderCaptured,
      activeConfig,
    };
  }, [
    selectedAddress,
    buyNowProductId,
    buyNowQty,
    refreshCart,
    navigate,
    onRefreshConfig,
    onOrderCaptured,
    activeConfig,
  ]);

  const [sdkLoading, setSdkLoading] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [statusNotice, setStatusNotice] = useState('');
  const [exceptionOrder, setExceptionOrder] = useState(null);

  const isReadyToRenderButtons = Boolean(
    !loadingConfig &&
      !configError &&
      activeConfig?.configured &&
      activeConfig?.eligible &&
      activeConfig?.client_id &&
      !exceptionOrder
  );

  const releasePendingReservation = async () => {
    const localOrderId = pendingOrderIdRef.current;
    if (!localOrderId) return;
    pendingOrderIdRef.current = null;
    try {
      await paymentsApi.cancelPayPalOrder(localOrderId);
    } catch {
      // Ignore if reservation already released or order transitioned
    }
    if (typeof latestPropsRef.current.onRefreshConfig === 'function') {
      latestPropsRef.current.onRefreshConfig();
    }
  };

  // Release any uncaptured reservation if the user switches methods or leaves checkout
  useEffect(() => {
    return () => {
      const danglingOrderId = pendingOrderIdRef.current;
      if (danglingOrderId) {
        pendingOrderIdRef.current = null;
        paymentsApi.cancelPayPalOrder(danglingOrderId).catch(() => {});
      }
    };
  }, []);

  useEffect(() => {
    if (!isReadyToRenderButtons) {
      return undefined;
    }

    let cancelled = false;
    setSdkLoading(true);
    setErrorMsg('');

    loadPayPalSdk(activeConfig.client_id, activeConfig.paypal_currency || 'USD')
      .then((paypal) => {
        if (cancelled || !containerRef.current || !paypal?.Buttons) return;

        containerRef.current.innerHTML = '';

        const buttons = paypal.Buttons({
          style: {
            layout: 'vertical',
            color: 'gold',
            shape: 'rect',
            label: 'paypal',
            height: 44,
          },
          createOrder: async () => {
            createErrorHandledRef.current = false;
            const {
              selectedAddress: addr,
              buyNowProductId: prodId,
              buyNowQty: qty,
              activeConfig: cfg,
            } = latestPropsRef.current;

            if (!addr) {
              const msg = 'Please select a delivery address before continuing with PayPal.';
              createErrorHandledRef.current = true;
              setErrorMsg(msg);
              throw new Error(msg);
            }

            setErrorMsg('');
            setStatusNotice('');

            try {
              const payload = {
                shipping_address: addr,
                ...(prodId
                  ? {
                      buy_now_product_id: Number(prodId),
                      buy_now_quantity: Math.max(1, Number(qty) || 1),
                    }
                  : {
                      merchant_id: cfg?.merchant_id ?? null,
                      is_platform_catalog: Boolean(cfg?.is_platform_catalog),
                    }),
              };
              const res = await paymentsApi.createPayPalOrder(payload);
              pendingOrderIdRef.current = res.local_order_id;
              return res.paypal_order_id;
            } catch (err) {
              createErrorHandledRef.current = true;
              setErrorMsg(err.message || 'Unable to create PayPal order. Please try again.');
              throw err;
            }
          },
          onApprove: async (data) => {
            const localOrderId = pendingOrderIdRef.current;
            if (!localOrderId) {
              setErrorMsg('Order reference expired. Please initiate PayPal checkout again.');
              return;
            }

            setCapturing(true);
            setErrorMsg('');
            setStatusNotice('');

            try {
              const order = await paymentsApi.capturePayPalOrder({
                local_order_id: localOrderId,
                paypal_order_id: data.orderID,
              });
              pendingOrderIdRef.current = null;

              await latestPropsRef.current.refreshCart().catch(() => {});

              if (order.status === 'CAPTURE_EXCEPTION') {
                setExceptionOrder(order);
                setCapturing(false);
                return;
              }

              if (typeof latestPropsRef.current.onOrderCaptured === 'function') {
                setCapturing(false);
                await latestPropsRef.current.onOrderCaptured(order);
              } else {
                latestPropsRef.current.navigate(`/orders/${order.id}/track`);
              }
            } catch (err) {
              setErrorMsg(
                err.message ||
                  'Payment capture could not be verified. Please retry or use Standard Shipkart Checkout.'
              );
              setCapturing(false);
            }
          },
          onCancel: async () => {
            await releasePendingReservation();
            if (!cancelled) {
              setStatusNotice(
                'PayPal Sandbox checkout was cancelled and any reserved stock has been released. You can try again or choose Standard Shipkart Checkout.'
              );
            }
          },
          onError: async (err) => {
            await releasePendingReservation();
            if (!cancelled) {
              if (!createErrorHandledRef.current) {
                const detail =
                  err && typeof err.message === 'string' && err.message.trim()
                    ? err.message
                    : 'PayPal Sandbox checkout encountered an issue. Any reserved stock has been released.';
                setErrorMsg(detail);
              }
              createErrorHandledRef.current = false;
            }
          },
        });

        buttonsInstanceRef.current = buttons;
        if (typeof buttons.isEligible === 'function' && !buttons.isEligible()) {
          setErrorMsg('PayPal checkout is not available in this browser session.');
          return null;
        }
        return buttons.render(containerRef.current);
      })
      .catch((err) => {
        if (!cancelled) {
          setErrorMsg(err.message || 'Unable to initialize PayPal Sandbox buttons.');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setSdkLoading(false);
        }
      });

    return () => {
      cancelled = true;
      const instance = buttonsInstanceRef.current;
      buttonsInstanceRef.current = null;
      if (instance && typeof instance.close === 'function') {
        Promise.resolve(instance.close()).catch(() => {});
      }
      if (containerRef.current) {
        containerRef.current.innerHTML = '';
      }
    };
  }, [
    isReadyToRenderButtons,
    activeConfig?.client_id,
    activeConfig?.paypal_currency,
  ]);

  if (loadingConfig) {
    return (
      <div className="rounded border border-blue-100 bg-white p-4 flex items-center gap-3 text-xs text-gray-600 apple-anim-fade">
        <Loader2 className="w-4 h-4 text-fk-blue animate-spin flex-shrink-0" />
        <span>Checking PayPal Sandbox availability and USD settlement total...</span>
      </div>
    );
  }

  if (configError) {
    return (
      <div className="rounded border border-amber-200 bg-amber-50 p-4 space-y-2.5 text-xs text-amber-900 apple-panel-enter">
        <div className="flex items-start gap-2.5">
          <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-bold">Unable to load PayPal Sandbox configuration</p>
            <p className="text-amber-800 mt-0.5">{configError}</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2 pl-6">
          {onRefreshConfig && (
            <button
              type="button"
              onClick={onRefreshConfig}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-sm border border-amber-300 bg-white text-amber-900 font-bold hover:bg-amber-100 transition"
            >
              <RefreshCw className="w-3.5 h-3.5" /> Retry
            </button>
          )}
          {onSwitchToStandard && (
            <button
              type="button"
              onClick={onSwitchToStandard}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-sm bg-fk-orange text-white font-bold hover:bg-orange-600 transition"
            >
              Use Standard Checkout
            </button>
          )}
        </div>
      </div>
    );
  }

  const originalAmount = activeConfig?.original_amount ?? 0;
  const paypalAmount = activeConfig?.paypal_amount ?? 0;
  const paypalCurrency = activeConfig?.paypal_currency || clientConfig?.paypal_currency || 'USD';
  const originalCurrency = activeConfig?.original_currency || clientConfig?.original_currency || 'INR';
  const environment = activeConfig?.environment || clientConfig?.environment;
  const merchantName = activeConfig?.merchant_name;

  return (
    <div className="space-y-3 apple-panel-enter">
      {/* Transparent Dual-Total Settlement Disclosure Box */}
      <div className="rounded border border-blue-200 bg-white p-4 space-y-2.5">
        <div className="flex items-center justify-between gap-2 border-b border-gray-100 pb-2">
          <div className="flex items-center gap-1.5 text-xs font-bold text-fk-dark uppercase tracking-wide">
            <Lock className="w-3.5 h-3.5 text-fk-blue" />
            <span>
              PayPal Sandbox Settlement Summary
              {merchantName ? ` — ${merchantName}` : ''}
            </span>
          </div>
          <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-blue-50 text-fk-blue border border-blue-100 uppercase flex-shrink-0">
            {environment === 'LIVE' ? 'Live' : 'Sandbox Test Mode'}
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
          <div className="bg-gray-50 rounded p-2.5 border border-gray-100">
            <p className="text-[11px] text-gray-500 font-medium">Catalog Total ({originalCurrency})</p>
            <p className="text-sm font-bold text-fk-dark mt-0.5">
              ₹{formatInr(originalAmount)} <span className="text-[11px] font-semibold text-gray-500">{originalCurrency}</span>
            </p>
          </div>
          <div className="bg-blue-50/60 rounded p-2.5 border border-blue-100">
            <p className="text-[11px] text-fk-blue font-semibold">
              PayPal Sandbox Settlement Total ({paypalCurrency})
            </p>
            <p className="text-sm font-extrabold text-fk-dark mt-0.5">
              ${formatUsd(paypalAmount)} <span className="text-[11px] font-bold text-fk-blue">{paypalCurrency}</span>
            </p>
          </div>
        </div>

        <p className="text-[11px] text-gray-500 flex items-start gap-1.5">
          <Info className="w-3.5 h-3.5 text-fk-blue flex-shrink-0 mt-0.5" />
          <span>
            Orders paid via PayPal Sandbox settle in explicit {paypalCurrency} Sandbox pricing ($
            {formatUsd(paypalAmount)} {paypalCurrency}) for test checkout verification.
          </span>
        </p>
      </div>

      {/* Case 1: PayPal not configured for this seller / catalog item */}
      {activeConfig && !activeConfig.configured && (
        <div className="rounded border border-blue-200 bg-blue-50/70 p-4 space-y-2.5 text-xs text-fk-dark">
          <div className="flex items-start gap-2.5">
            <Info className="w-4 h-4 text-fk-blue flex-shrink-0 mt-0.5" />
            <div>
              {activeConfig.is_platform_catalog ? (
                <>
                  <p className="font-bold text-fk-dark">Unclaimed Platform Starter Catalog Item</p>
                  <p className="text-gray-600 mt-0.5 leading-relaxed">
                    This item has not been claimed by a merchant seller yet, so Direct PayPal isn&apos;t
                    attached. You can switch to Standard Checkout below to complete your order immediately.
                  </p>
                </>
              ) : (
                <>
                  <p className="font-bold text-fk-dark">
                    {merchantName
                      ? `${merchantName} — PayPal Not Activated Yet`
                      : 'Seller PayPal Not Activated Yet'}
                  </p>
                  <p className="text-gray-600 mt-0.5 leading-relaxed">
                    This seller hasn&apos;t activated Direct PayPal checkout yet. Switch to Standard
                    Checkout below to place your order immediately.
                  </p>
                </>
              )}
            </div>
          </div>
          {onSwitchToStandard && (
            <div className="pl-6">
              <button
                type="button"
                onClick={onSwitchToStandard}
                className="bg-fk-orange hover:bg-orange-600 text-white font-bold text-xs px-4 py-2 rounded-sm shadow-sm uppercase transition"
              >
                Switch to Standard Checkout
              </button>
            </div>
          )}
        </div>
      )}

      {/* Case 2: Configured, but order/cart not eligible */}
      {activeConfig?.configured && !activeConfig?.eligible && (
        <div className="rounded border border-amber-200 bg-amber-50 p-4 space-y-2 text-xs text-amber-900">
          <div className="flex items-start gap-2.5">
            <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-bold">PayPal Sandbox Checkout Unavailable for Current Items</p>
              <p className="text-amber-800 mt-0.5">
                {activeConfig.reason && !/backend|credential|client_id|secret|env/i.test(activeConfig.reason)
                  ? activeConfig.reason
                  : 'One or more items in your checkout are currently ineligible for PayPal checkout. You can use Standard Checkout instead.'}
              </p>
            </div>
          </div>
          {onSwitchToStandard && (
            <div className="pl-6 pt-1">
              <button
                type="button"
                onClick={onSwitchToStandard}
                className="bg-white border border-amber-300 hover:bg-amber-100 text-amber-900 font-bold text-xs px-3 py-1.5 rounded-sm transition"
              >
                Use Standard Checkout Instead
              </button>
            </div>
          )}
        </div>
      )}

      {/* Case 3: Capture Exception Review Alert */}
      {exceptionOrder && (
        <div
          role="alert"
          className="rounded border border-red-200 bg-red-50 p-4 space-y-3 text-xs text-red-900 apple-panel-enter"
        >
          <div className="flex items-start gap-2.5">
            <AlertTriangle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
            <div className="space-y-1">
              <p className="font-bold text-sm text-red-800">
                Order Flagged for Exception Review ({exceptionOrder.order_number})
              </p>
              <p className="text-red-800 leading-relaxed">
                Your PayPal payment was authorized, but final inventory verification could not be
                completed ({exceptionOrder.payment_status}). This order has been routed for exception
                review and automatic resolution.
              </p>
            </div>
          </div>
          <div className="pl-7">
            <button
              type="button"
              onClick={() => navigate(`/orders/${exceptionOrder.id}/track`)}
              className="inline-flex items-center gap-1.5 bg-red-600 hover:bg-red-700 text-white font-bold text-xs px-4 py-2 rounded-sm shadow transition"
            >
              <span>View Order & Exception Status</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}

      {/* Status & Error Banners */}
      {statusNotice && (
        <div className="rounded border border-blue-200 bg-blue-50 p-3 text-xs text-blue-900 flex items-start gap-2">
          <Info className="w-4 h-4 text-fk-blue flex-shrink-0 mt-0.5" />
          <span>{statusNotice}</span>
        </div>
      )}

      {errorMsg && (
        <div
          role="alert"
          className="rounded border border-red-200 bg-red-50 p-3 text-xs text-red-800 flex items-start gap-2"
        >
          <AlertTriangle className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Case 4: Eligible — PayPal JS SDK Buttons Container */}
      {isReadyToRenderButtons && (
        <div className="rounded border border-gray-200 bg-white p-4 space-y-3 relative">
          {!selectedAddress && (
            <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2 font-medium">
              Please select a delivery address in Step 2 before proceeding with PayPal.
            </p>
          )}

          {sdkLoading && (
            <div className="flex items-center justify-center gap-2 py-4 text-xs text-gray-500">
              <Loader2 className="w-4 h-4 text-fk-blue animate-spin" />
              <span>Loading secure PayPal Sandbox buttons...</span>
            </div>
          )}

          {capturing && (
            <div className="rounded bg-blue-50/90 border border-blue-200 p-4 flex items-center justify-center gap-2.5 text-xs font-semibold text-fk-blue">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>Capturing PayPal Sandbox payment and generating your invoice...</span>
            </div>
          )}

          <div
            ref={containerRef}
            className={capturing ? 'opacity-50 pointer-events-none' : 'min-h-[48px]'}
          />

          <div className="flex items-center justify-between text-[11px] text-gray-500 pt-1 border-t border-gray-100">
            <span className="flex items-center gap-1">
              <ShieldCheck className="w-3.5 h-3.5 text-fk-green" />
              Protected PayPal Sandbox Checkout
            </span>
            <span className="font-semibold text-fk-dark">
              Total: ${formatUsd(paypalAmount)} {paypalCurrency}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
