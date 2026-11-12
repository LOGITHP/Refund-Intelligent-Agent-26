import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import {
  ArrowRight,
  Check,
  CheckCircle2,
  CreditCard,
  Globe,
  Info,
  Plus,
  ShieldCheck,
  Store,
} from 'lucide-react';
import Navbar from '../components/Navbar';
import Footer from '../components/Footer';
import PayPalCheckoutButton from '../components/PayPalCheckoutButton';
import { authApi, ordersApi, paymentsApi, productsApi, resolveMediaUrl } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { useCart } from '../context/CartContext';

function getMerchantGroupKey(group) {
  if (!group) return '';
  return group.is_platform_catalog
    ? 'platform-catalog'
    : `merchant-${group.merchant_id ?? 'unknown'}`;
}

export default function Checkout() {
  const [searchParams] = useSearchParams();
  const buyNowProductId = searchParams.get('buy_now_product_id');
  const buyNowQty = Number(searchParams.get('quantity') || 1);

  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuth();
  const { cart, refreshCart } = useCart();

  const [addresses, setAddresses] = useState([]);
  const [selectedAddress, setSelectedAddress] = useState(null);
  const [showNewAddress, setShowNewAddress] = useState(false);
  const [buyNowProduct, setBuyNowProduct] = useState(null);
  const [step, setStep] = useState(2); // 2: Address, 3: Summary, 4: Payment Point
  const [placingOrder, setPlacingOrder] = useState(false);

  const [paypalConfig, setPaypalConfig] = useState(null);
  const [paypalConfigLoading, setPaypalConfigLoading] = useState(true);
  const [paypalConfigError, setPaypalConfigError] = useState('');
  const [paymentMethod, setPaymentMethod] = useState('STANDARD_CHECKOUT');
  const [activeMerchantKey, setActiveMerchantKey] = useState('');
  const [completedSplitOrders, setCompletedSplitOrders] = useState([]);
  const userSelectedMethodRef = useRef(false);

  const [newAddr, setNewAddr] = useState({
    full_name: user?.full_name || '',
    phone: user?.phone || '',
    pincode: '',
    locality: '',
    street_address: '',
    city: '',
    state: '',
    address_type: 'HOME',
    is_default: true,
  });

  const fetchPayPalConfig = useCallback(async () => {
    if (authLoading || !user) return null;
    setPaypalConfigLoading(true);
    setPaypalConfigError('');
    try {
      const data = await paymentsApi.clientConfig({
        buy_now_product_id: buyNowProductId,
        buy_now_quantity: buyNowQty,
      });
      setPaypalConfig(data);

      const groups = Array.isArray(data?.groups) ? data.groups : [];
      if (groups.length > 0) {
        setActiveMerchantKey((prevKey) => {
          if (prevKey && groups.some((g) => getMerchantGroupKey(g) === prevKey)) {
            return prevKey;
          }
          const nextEligible = groups.find((g) => g.configured && g.eligible) || groups[0];
          return getMerchantGroupKey(nextEligible);
        });
      } else {
        setActiveMerchantKey('');
      }

      if (!userSelectedMethodRef.current) {
        const hasEligibleGroup = groups.some((g) => g.configured && g.eligible);
        setPaymentMethod(
          (data?.configured && data?.eligible) || hasEligibleGroup
            ? 'PAYPAL_SANDBOX'
            : 'STANDARD_CHECKOUT'
        );
      }
      return data;
    } catch (err) {
      setPaypalConfigError(err.message || 'Unable to check PayPal Sandbox availability.');
      if (!userSelectedMethodRef.current) {
        setPaymentMethod('STANDARD_CHECKOUT');
      }
      return null;
    } finally {
      setPaypalConfigLoading(false);
    }
  }, [authLoading, user, buyNowProductId, buyNowQty]);

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      navigate('/');
      return;
    }
    authApi.getAddresses().then((list) => {
      setAddresses(list);
      if (list.length > 0) {
        setSelectedAddress(list.find((a) => a.is_default) || list[0]);
      } else {
        setShowNewAddress(true);
      }
    });

    if (buyNowProductId) {
      productsApi.get(buyNowProductId).then(setBuyNowProduct);
    }
  }, [user, authLoading, buyNowProductId, navigate]);

  const cartRefreshKey = buyNowProductId
    ? `buy-now-${buyNowProductId}-${buyNowQty}`
    : `${cart.total_items}-${cart.final_amount}`;

  useEffect(() => {
    fetchPayPalConfig();
  }, [fetchPayPalConfig, cartRefreshKey]);

  const handleSelectPaymentMethod = (method) => {
    userSelectedMethodRef.current = true;
    setPaymentMethod(method);
  };

  const handleOrderCaptured = useCallback(
    async (capturedOrder) => {
      setCompletedSplitOrders((prev) => {
        if (prev.some((o) => o.id === capturedOrder.id)) return prev;
        return [...prev, capturedOrder];
      });

      await refreshCart();
      const refreshedConfig = await fetchPayPalConfig();

      const remainingGroups = Array.isArray(refreshedConfig?.groups)
        ? refreshedConfig.groups
        : [];

      if (buyNowProductId || (refreshedConfig && remainingGroups.length === 0)) {
        navigate(`/orders/${capturedOrder.id}/track`);
        return;
      }

      if (remainingGroups.length > 0) {
        const nextEligible =
          remainingGroups.find((g) => g.configured && g.eligible) || remainingGroups[0];
        setActiveMerchantKey(getMerchantGroupKey(nextEligible));
      }
    },
    [buyNowProductId, fetchPayPalConfig, navigate, refreshCart]
  );

  const handleSaveAddress = async (e) => {
    e.preventDefault();
    try {
      const saved = await authApi.addAddress(newAddr);
      setAddresses((prev) => [...prev, saved]);
      setSelectedAddress(saved);
      setShowNewAddress(false);
      setStep(3);
    } catch (err) {
      alert(err.message || 'Failed saving address');
    }
  };

  const handlePlaceOrder = async () => {
    if (!selectedAddress) {
      alert('Please select a delivery address');
      return;
    }
    setPlacingOrder(true);
    try {
      const payload = {
        shipping_address: selectedAddress,
        payment_method: 'STANDARD_CHECKOUT',
        ...(buyNowProductId
          ? { buy_now_product_id: Number(buyNowProductId), buy_now_quantity: buyNowQty }
          : {}),
      };
      const createdOrder = await ordersApi.create(payload);
      await refreshCart();
      navigate(`/orders/${createdOrder.id}/track`);
    } catch (err) {
      alert(err.message || 'Order placement failed');
    } finally {
      setPlacingOrder(false);
    }
  };

  // Compute summary metrics
  const orderItems = buyNowProduct
    ? [{ product: buyNowProduct, quantity: buyNowQty }]
    : cart.items;
  const totalMrp = buyNowProduct ? buyNowProduct.mrp * buyNowQty : cart.total_mrp;
  const totalAmount = buyNowProduct ? buyNowProduct.price * buyNowQty : cart.final_amount;
  const totalDiscount = totalMrp - totalAmount;

  const paypalGroups = Array.isArray(paypalConfig?.groups) ? paypalConfig.groups : [];
  const isSplitCheckout =
    !buyNowProductId &&
    (Boolean(paypalConfig?.requires_split_checkout) || paypalGroups.length > 1);
  const singleGroup = paypalGroups.length === 1 ? paypalGroups[0] : null;
  const activeMerchantGroup = isSplitCheckout
    ? paypalGroups.find((g) => getMerchantGroupKey(g) === activeMerchantKey) ||
      paypalGroups.find((g) => g.configured && g.eligible) ||
      paypalGroups[0] ||
      null
    : singleGroup;
  const resolvedActiveKey = activeMerchantGroup
    ? getMerchantGroupKey(activeMerchantGroup)
    : 'default-paypal';
  const eligibleGroupsCount = paypalGroups.filter((g) => g.configured && g.eligible).length;
  const hasAnyEligibleGroup = eligibleGroupsCount > 0;

  return (
    <div className="min-h-screen flex flex-col">
      <Navbar />

      <main className="flex-1 max-w-[1240px] w-full mx-auto px-4 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
          {/* Left Accordion Steps (8 cols) */}
          <div className="lg:col-span-8 space-y-4">
            {/* STEP 1: LOGIN */}
            <div className="bg-white rounded-sm shadow-sm p-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="bg-gray-100 text-fk-blue font-bold text-xs px-2 py-0.5 rounded">1</span>
                <div>
                  <div className="flex items-center gap-2 text-xs font-bold text-gray-500 uppercase">
                    <span>Login</span>
                    <Check className="w-4 h-4 text-fk-blue" />
                  </div>
                  <p className="text-sm font-semibold text-fk-dark mt-0.5">
                    {user?.full_name} <span className="text-gray-500 font-normal ml-2">{user?.email}</span>
                  </p>
                </div>
              </div>
            </div>

            {/* STEP 2: DELIVERY ADDRESS */}
            <div className="bg-white rounded-sm shadow-sm overflow-hidden">
              <div
                className={`p-4 flex items-center justify-between ${
                  step === 2 ? 'bg-fk-blue text-white' : 'bg-white text-fk-dark'
                }`}
              >
                <div className="flex items-center gap-3">
                  <span
                    className={`font-bold text-xs px-2 py-0.5 rounded ${
                      step === 2 ? 'bg-white text-fk-blue' : 'bg-gray-100 text-fk-blue'
                    }`}
                  >
                    2
                  </span>
                  <span className="font-bold text-sm uppercase">Delivery Address</span>
                  {step > 2 && selectedAddress && <Check className="w-4 h-4 text-fk-blue" />}
                </div>
                {step > 2 && (
                  <button
                    onClick={() => setStep(2)}
                    className="text-xs font-bold text-fk-blue border border-gray-200 px-3 py-1 rounded-sm hover:bg-gray-50"
                  >
                    CHANGE
                  </button>
                )}
              </div>

              {step === 2 && (
                <div className="p-5 space-y-4">
                  {addresses.map((addr) => (
                    <label
                      key={addr.id}
                      className={`block border rounded p-4 cursor-pointer transition ${
                        selectedAddress?.id === addr.id ? 'border-fk-blue bg-blue-50/40' : 'border-gray-200'
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <input
                          type="radio"
                          name="address"
                          checked={selectedAddress?.id === addr.id}
                          onChange={() => setSelectedAddress(addr)}
                          className="mt-1 accent-fk-blue"
                        />
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-sm text-fk-dark">{addr.full_name}</span>
                            <span className="text-[10px] bg-gray-200 text-gray-700 font-bold px-1.5 py-0.5 rounded uppercase">
                              {addr.address_type}
                            </span>
                            <span className="text-sm font-semibold text-gray-700 ml-2">{addr.phone}</span>
                          </div>
                          <p className="text-xs text-gray-600 mt-1">
                            {addr.street_address}, {addr.locality}, {addr.city}, {addr.state} -{' '}
                            <strong className="text-gray-900">{addr.pincode}</strong>
                          </p>
                          {selectedAddress?.id === addr.id && (
                            <button
                              onClick={() => setStep(3)}
                              className="mt-3 bg-fk-orange hover:bg-orange-600 text-white font-bold text-xs px-6 py-2.5 rounded-sm shadow uppercase"
                            >
                              Deliver Here
                            </button>
                          )}
                        </div>
                      </div>
                    </label>
                  ))}

                  {/* Add New Address Toggle */}
                  {!showNewAddress ? (
                    <button
                      onClick={() => setShowNewAddress(true)}
                      className="flex items-center gap-2 text-fk-blue font-bold text-xs hover:underline pt-2"
                    >
                      <Plus className="w-4 h-4" /> Add a new address
                    </button>
                  ) : (
                    <form onSubmit={handleSaveAddress} className="bg-blue-50/30 border border-blue-100 p-4 rounded space-y-3">
                      <h4 className="text-xs font-bold text-fk-blue uppercase">Add New Address</h4>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <input
                          type="text"
                          required
                          placeholder="Full Name"
                          value={newAddr.full_name}
                          onChange={(e) => setNewAddr({ ...newAddr, full_name: e.target.value })}
                          className="border p-2 rounded text-xs bg-white"
                        />
                        <input
                          type="tel"
                          required
                          placeholder="10-digit mobile number"
                          value={newAddr.phone}
                          onChange={(e) => setNewAddr({ ...newAddr, phone: e.target.value })}
                          className="border p-2 rounded text-xs bg-white"
                        />
                        <input
                          type="text"
                          required
                          placeholder="Pincode"
                          value={newAddr.pincode}
                          onChange={(e) => setNewAddr({ ...newAddr, pincode: e.target.value })}
                          className="border p-2 rounded text-xs bg-white"
                        />
                        <input
                          type="text"
                          required
                          placeholder="Locality"
                          value={newAddr.locality}
                          onChange={(e) => setNewAddr({ ...newAddr, locality: e.target.value })}
                          className="border p-2 rounded text-xs bg-white"
                        />
                      </div>
                      <textarea
                        required
                        placeholder="Address (Area and Street)"
                        value={newAddr.street_address}
                        onChange={(e) => setNewAddr({ ...newAddr, street_address: e.target.value })}
                        className="w-full border p-2 rounded text-xs bg-white"
                        rows={2}
                      />
                      <div className="grid grid-cols-2 gap-3">
                        <input
                          type="text"
                          required
                          placeholder="City / District"
                          value={newAddr.city}
                          onChange={(e) => setNewAddr({ ...newAddr, city: e.target.value })}
                          className="border p-2 rounded text-xs bg-white"
                        />
                        <input
                          type="text"
                          required
                          placeholder="State"
                          value={newAddr.state}
                          onChange={(e) => setNewAddr({ ...newAddr, state: e.target.value })}
                          className="border p-2 rounded text-xs bg-white"
                        />
                      </div>
                      <div className="flex gap-3 pt-1">
                        <button
                          type="submit"
                          className="bg-fk-orange text-white font-bold text-xs px-5 py-2 rounded-sm uppercase"
                        >
                          Save and Deliver Here
                        </button>
                        {addresses.length > 0 && (
                          <button
                            type="button"
                            onClick={() => setShowNewAddress(false)}
                            className="text-xs text-gray-500 font-semibold px-3"
                          >
                            Cancel
                          </button>
                        )}
                      </div>
                    </form>
                  )}
                </div>
              )}

              {step > 2 && selectedAddress && (
                <div className="px-11 pb-4 text-xs text-gray-600">
                  <strong>{selectedAddress.full_name}</strong> — {selectedAddress.street_address},{' '}
                  {selectedAddress.city}, {selectedAddress.state} - {selectedAddress.pincode}
                </div>
              )}
            </div>

            {/* STEP 3: ORDER SUMMARY */}
            <div className="bg-white rounded-sm shadow-sm overflow-hidden">
              <div
                className={`p-4 flex items-center justify-between ${
                  step === 3 ? 'bg-fk-blue text-white' : 'bg-white text-fk-dark'
                }`}
              >
                <div className="flex items-center gap-3">
                  <span
                    className={`font-bold text-xs px-2 py-0.5 rounded ${
                      step === 3 ? 'bg-white text-fk-blue' : 'bg-gray-100 text-fk-blue'
                    }`}
                  >
                    3
                  </span>
                  <span className="font-bold text-sm uppercase">Order Summary</span>
                  {step > 3 && <Check className="w-4 h-4 text-fk-blue" />}
                </div>
                {step > 3 && (
                  <button
                    type="button"
                    onClick={() => setStep(3)}
                    className="text-xs font-bold text-fk-blue border border-gray-200 px-3 py-1 rounded-sm hover:bg-gray-50"
                  >
                    CHANGE
                  </button>
                )}
              </div>

              {step === 3 && (
                <div className="p-5 space-y-4 apple-panel-enter">
                  {orderItems.length === 0 ? (
                    <div className="text-center py-6 text-xs text-gray-500">
                      Your checkout has no items. Please add products to your cart first.
                    </div>
                  ) : (
                    <div className="divide-y divide-gray-100">
                      {orderItems.map((item, idx) => (
                        <div key={idx} className="py-3 flex gap-4">
                          <img
                            src={resolveMediaUrl(item.product.image_url)}
                            alt={item.product.title}
                            className="w-16 h-16 object-contain border rounded p-1"
                          />
                          <div className="flex-1">
                            <h4 className="text-sm font-medium text-fk-dark">{item.product.title}</h4>
                            <p className="text-xs text-gray-500 mt-0.5">Qty: {item.quantity}</p>
                            <div className="flex items-baseline gap-2 mt-1">
                              <span className="text-sm font-bold">
                                ₹{(item.product.price * item.quantity).toLocaleString('en-IN')}
                              </span>
                              <span className="text-xs text-gray-400 line-through">
                                ₹{(item.product.mrp * item.quantity).toLocaleString('en-IN')}
                              </span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-3 border-t pt-4">
                    <span className="text-xs text-gray-500">
                      Order confirmation email & GST PDF Invoice will be sent to <strong>{user?.email}</strong>
                    </span>
                    <button
                      type="button"
                      disabled={orderItems.length === 0}
                      onClick={() => setStep(4)}
                      className="bg-fk-orange hover:bg-orange-600 disabled:opacity-50 text-white font-bold text-xs px-8 py-3 rounded-sm shadow uppercase"
                    >
                      Continue to Checkout
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* STEP 4: PAYMENT OPTIONS */}
            <div className="bg-white rounded-sm shadow-sm overflow-hidden">
              <div
                className={`p-4 flex items-center gap-3 ${
                  step === 4 ? 'bg-fk-blue text-white' : 'bg-white text-gray-500'
                }`}
              >
                <span
                  className={`font-bold text-xs px-2 py-0.5 rounded ${
                    step === 4 ? 'bg-white text-fk-blue' : 'bg-gray-100 text-fk-blue'
                  }`}
                >
                  4
                </span>
                <span className="font-bold text-sm uppercase">Payment & Order Confirmation</span>
              </div>

              {step === 4 && (
                <div className="p-5 space-y-4 apple-panel-enter">
                  {completedSplitOrders.length > 0 && (
                    <div className="space-y-2">
                      {completedSplitOrders.map((ord) => {
                        const orderLabel = String(ord.order_number || ord.id).replace(/^#/, '');
                        return (
                          <div
                            key={ord.id}
                            className="flex flex-wrap items-center justify-between gap-2 rounded-full sm:rounded-lg border border-green-200 bg-green-50 px-4 py-2.5 text-xs text-green-900 apple-panel-enter"
                          >
                            <div className="flex items-center gap-2 font-semibold">
                              <CheckCircle2 className="w-4 h-4 text-green-600 flex-shrink-0" />
                              <span>
                                Paid &amp; Confirmed: <strong className="font-bold">#{orderLabel}</strong>
                              </span>
                              {ord.total_amount != null && (
                                <span className="text-green-800 font-normal">
                                  (₹{Number(ord.total_amount).toLocaleString('en-IN')}
                                  {ord.paypal_amount != null
                                    ? ` / $${Number(ord.paypal_amount).toFixed(2)} USD`
                                    : ''}
                                  )
                                </span>
                              )}
                            </div>
                            <Link
                              to={`/orders/${ord.id}/track`}
                              className="inline-flex items-center gap-1 font-bold text-green-800 hover:text-green-950 underline underline-offset-2"
                            >
                              <span>Track Order</span>
                              <ArrowRight className="w-3.5 h-3.5" />
                            </Link>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {/* Option 1: PayPal Sandbox (USD Test Checkout) */}
                  <div
                    className={`border rounded p-4 space-y-3 apple-card-hover ${
                      paymentMethod === 'PAYPAL_SANDBOX'
                        ? 'border-fk-blue bg-blue-50/20 shadow-sm'
                        : 'border-gray-200 bg-white'
                    }`}
                  >
                    <label className="flex items-start sm:items-center justify-between gap-3 cursor-pointer">
                      <div className="flex items-start sm:items-center gap-2.5">
                        <input
                          type="radio"
                          name="paymentMethod"
                          value="PAYPAL_SANDBOX"
                          checked={paymentMethod === 'PAYPAL_SANDBOX'}
                          onChange={() => handleSelectPaymentMethod('PAYPAL_SANDBOX')}
                          className="mt-1 sm:mt-0 accent-fk-blue"
                        />
                        <Globe className="w-4 h-4 text-fk-blue flex-shrink-0 mt-0.5 sm:mt-0" />
                        <div>
                          <span className="font-bold text-sm text-fk-dark block">
                            Pay with PayPal Sandbox (USD Test Checkout)
                          </span>
                          <span className="text-xs text-gray-500 block mt-0.5">
                            Checkout with a PayPal Sandbox test account with transparent USD settlement.
                          </span>
                        </div>
                      </div>
                      {paypalConfig?.configured && paypalConfig?.eligible ? (
                        <span className="text-xs font-bold px-2.5 py-1 rounded bg-blue-100 text-fk-blue flex-shrink-0">
                          ${Number(paypalConfig.paypal_amount).toFixed(2)}{' '}
                          {paypalConfig.paypal_currency || 'USD'}
                        </span>
                      ) : hasAnyEligibleGroup ? (
                        <span className="text-xs font-bold px-2.5 py-1 rounded bg-blue-100 text-fk-blue flex-shrink-0">
                          {eligibleGroupsCount}/{paypalGroups.length} Sellers Ready
                        </span>
                      ) : (
                        <span className="text-[11px] font-bold px-2 py-0.5 rounded bg-gray-100 text-gray-600 flex-shrink-0">
                          {paypalConfigLoading
                            ? 'Checking...'
                            : paypalConfig && !paypalConfig.configured
                            ? singleGroup?.is_platform_catalog || paypalConfig?.is_platform_catalog
                              ? 'Standard Checkout Only'
                              : 'PayPal Not Activated'
                            : 'Unavailable'}
                        </span>
                      )}
                    </label>

                    {paymentMethod === 'PAYPAL_SANDBOX' && (
                      <div className="pt-2 sm:pl-6 space-y-4">
                        {isSplitCheckout ? (
                          <div className="space-y-3">
                            <div className="rounded border border-blue-200 bg-blue-50/70 p-3 text-xs text-fk-dark flex items-start gap-2">
                              <Info className="w-4 h-4 text-fk-blue flex-shrink-0 mt-0.5" />
                              <p className="leading-relaxed">
                                Your cart contains items from multiple independent merchants. Because each merchant receives funds directly into their own PayPal account, please complete PayPal payment one seller at a time.
                              </p>
                            </div>

                            <div className="grid grid-cols-1 gap-2.5">
                              {paypalGroups.map((group) => {
                                const groupKey = getMerchantGroupKey(group);
                                const isActive = groupKey === resolvedActiveKey;
                                const isReady = Boolean(group.configured && group.eligible);
                                const sellerName =
                                  group.merchant_name ||
                                  (group.is_platform_catalog
                                    ? 'Shipkart Platform Catalog'
                                    : 'Independent Merchant');
                                const groupItems = Array.isArray(group.items) ? group.items : [];
                                const itemCount = group.items_count ?? groupItems.length;
                                const itemTitles = groupItems
                                  .map((item) =>
                                    item.quantity > 1
                                      ? `${item.title} × ${item.quantity}`
                                      : item.title
                                  )
                                  .join(', ');

                                return (
                                  <button
                                    key={groupKey}
                                    type="button"
                                    onClick={() => setActiveMerchantKey(groupKey)}
                                    className={`w-full text-left rounded border p-3.5 transition flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
                                      isActive
                                        ? 'border-fk-blue bg-blue-50/50 ring-1 ring-fk-blue shadow-sm'
                                        : 'border-gray-200 bg-white hover:border-blue-300'
                                    }`}
                                  >
                                    <div className="space-y-1 min-w-0 flex-1">
                                      <div className="flex flex-wrap items-center gap-2">
                                        <Store className="w-3.5 h-3.5 text-fk-blue flex-shrink-0" />
                                        <span className="font-bold text-xs sm:text-sm text-fk-dark">
                                          {sellerName}
                                        </span>
                                        <span
                                          className={`text-[10px] font-bold px-2 py-0.5 rounded uppercase ${
                                            isReady
                                              ? 'bg-green-100 text-green-800 border border-green-200'
                                              : 'bg-amber-100 text-amber-900 border border-amber-200'
                                          }`}
                                        >
                                          {isReady
                                            ? 'PayPal Ready'
                                            : !group.configured
                                            ? group.is_platform_catalog
                                              ? 'Unclaimed Catalog Item'
                                              : 'Seller PayPal Not Configured'
                                            : 'PayPal Unavailable'}
                                        </span>
                                        {isActive && (
                                          <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-fk-blue text-white uppercase">
                                            Active Checkout
                                          </span>
                                        )}
                                      </div>

                                      <p className="text-xs text-gray-600 truncate">
                                        <span className="font-semibold text-gray-700">
                                          {itemCount} {itemCount === 1 ? 'item' : 'items'}
                                        </span>
                                        {itemTitles ? `: ${itemTitles}` : ''}
                                      </p>
                                    </div>

                                    <div className="flex sm:flex-col items-baseline sm:items-end justify-between gap-1 flex-shrink-0 border-t sm:border-t-0 pt-2 sm:pt-0 border-gray-100">
                                      <span className="text-xs font-bold text-fk-dark">
                                        ₹
                                        {Number(group.original_amount || 0).toLocaleString(
                                          'en-IN',
                                          {
                                            minimumFractionDigits: 2,
                                            maximumFractionDigits: 2,
                                          }
                                        )}
                                      </span>
                                      <span className="text-xs font-extrabold text-fk-blue">
                                        ${Number(group.paypal_amount || 0).toFixed(2)}{' '}
                                        {group.paypal_currency || 'USD'}
                                      </span>
                                    </div>
                                  </button>
                                );
                              })}
                            </div>
                          </div>
                        ) : (
                          singleGroup?.merchant_name && (
                            <div className="flex items-center gap-2 text-xs text-gray-700 bg-white border border-blue-100 rounded px-3 py-2">
                              <Store className="w-3.5 h-3.5 text-fk-blue flex-shrink-0" />
                              <span>
                                Direct PayPal checkout to{' '}
                                <strong className="text-fk-dark">{singleGroup.merchant_name}</strong>
                              </span>
                            </div>
                          )
                        )}

                        <PayPalCheckoutButton
                          key={resolvedActiveKey}
                          clientConfig={paypalConfig}
                          merchantGroup={activeMerchantGroup}
                          loadingConfig={paypalConfigLoading}
                          configError={paypalConfigError}
                          selectedAddress={selectedAddress}
                          buyNowProductId={buyNowProductId}
                          buyNowQty={buyNowQty}
                          onRefreshConfig={fetchPayPalConfig}
                          onOrderCaptured={handleOrderCaptured}
                          onSwitchToStandard={() => handleSelectPaymentMethod('STANDARD_CHECKOUT')}
                        />
                      </div>
                    )}
                  </div>

                  {/* Option 2: Standard Shipkart Checkout */}
                  <div
                    className={`border rounded p-4 space-y-3 apple-card-hover ${
                      paymentMethod === 'STANDARD_CHECKOUT'
                        ? 'border-fk-blue bg-blue-50/20 shadow-sm'
                        : 'border-gray-200 bg-white'
                    }`}
                  >
                    <label className="flex items-start sm:items-center gap-2.5 cursor-pointer">
                      <input
                        type="radio"
                        name="paymentMethod"
                        value="STANDARD_CHECKOUT"
                        checked={paymentMethod === 'STANDARD_CHECKOUT'}
                        onChange={() => handleSelectPaymentMethod('STANDARD_CHECKOUT')}
                        className="mt-1 sm:mt-0 accent-fk-blue"
                      />
                      <CreditCard className="w-4 h-4 text-fk-blue flex-shrink-0 mt-0.5 sm:mt-0" />
                      <div>
                        <span className="font-bold text-sm text-fk-dark block">
                          Standard Shipkart Checkout (Instant Confirmation)
                        </span>
                        <span className="text-xs text-gray-500 block mt-0.5">
                          Confirming your order immediately generates your digital tax invoice and enables live delivery & return tracking.
                        </span>
                      </div>
                    </label>

                    {paymentMethod === 'STANDARD_CHECKOUT' && (
                      <div className="pl-6 apple-panel-enter">
                        <button
                          type="button"
                          onClick={handlePlaceOrder}
                          disabled={placingOrder || orderItems.length === 0}
                          className="bg-fk-orange hover:bg-orange-600 disabled:opacity-50 text-white font-bold px-8 py-3 rounded-sm shadow-md text-sm uppercase tracking-wide transition"
                        >
                          {placingOrder
                            ? 'Confirming Order...'
                            : `Confirm Order (₹${totalAmount.toLocaleString('en-IN')})`}
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Right Price Summary (4 cols) */}
          <div className="lg:col-span-4 bg-white rounded-sm shadow-sm p-5 sticky top-20 space-y-4">
            <h2 className="text-sm font-bold text-gray-500 uppercase border-b pb-3">Price Details</h2>
            <div className="space-y-3 text-sm">
              <div className="flex justify-between">
                <span>Price ({orderItems.length} item{orderItems.length > 1 ? 's' : ''})</span>
                <span>₹{totalMrp.toLocaleString('en-IN')}</span>
              </div>
              <div className="flex justify-between">
                <span>Discount</span>
                <span className="text-fk-green font-medium">- ₹{totalDiscount.toLocaleString('en-IN')}</span>
              </div>
              <div className="flex justify-between">
                <span>Delivery Charges</span>
                <span className="text-fk-green font-medium">FREE</span>
              </div>
            </div>
            <div className="border-t border-dashed pt-3 flex justify-between text-base font-bold text-fk-dark">
              <span>Total Payable</span>
              <span>₹{totalAmount.toLocaleString('en-IN')}</span>
            </div>
            {paypalConfig?.paypal_amount != null && Number(paypalConfig.paypal_amount) > 0 && (
              <div className="bg-blue-50/70 border border-blue-100 rounded p-3 space-y-1">
                <div className="flex justify-between items-center text-xs font-bold text-fk-dark">
                  <span>PayPal Sandbox Settlement</span>
                  <span className="text-fk-blue">
                    ${Number(paypalConfig.paypal_amount).toFixed(2)}{' '}
                    {paypalConfig.paypal_currency || 'USD'}
                  </span>
                </div>
                <p className="text-[11px] text-gray-500">
                  Explicit {paypalConfig.paypal_currency || 'USD'} Sandbox pricing when paying via PayPal Sandbox.
                </p>
              </div>
            )}
            <p className="text-xs text-fk-green font-bold border-t pt-3">
              Your Total Savings on this order ₹{totalDiscount.toLocaleString('en-IN')}
            </p>
            <div className="flex items-center gap-2 text-xs text-gray-500 pt-2">
              <ShieldCheck className="w-5 h-5 text-gray-400 flex-shrink-0" />
              <span>Safe and Secure Payments. Easy returns. 100% Authentic products.</span>
            </div>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}

