import React, { useEffect, useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import {
  Package,
  CheckCircle2,
  FileText,
  RefreshCw,
  ArrowLeft,
  MapPin,
  AlertTriangle,
  Clock,
  XCircle,
} from 'lucide-react';
import Navbar from '../components/Navbar';
import Footer from '../components/Footer';
import ReturnModal from '../components/ReturnModal';
import RefundIntelligencePanel from '../components/RefundIntelligencePanel';
import { ordersApi, resolveMediaUrl, returnsApi } from '../services/api';
import { useAuth } from '../context/AuthContext';

export default function OrderTrack() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuth();

  const [order, setOrder] = useState(null);
  const [returns, setReturns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [returnModalItem, setReturnModalItem] = useState(null);

  const loadOrderData = async () => {
    try {
      const [ordData, retData] = await Promise.all([ordersApi.get(id), returnsApi.myReturns()]);
      setOrder(ordData);
      setReturns(retData.filter((r) => r.order_id === Number(id)));
    } catch (err) {
      console.error('Error loading order:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      navigate('/');
      return;
    }
    loadOrderData();

    const interval = setInterval(loadOrderData, 3000);
    return () => clearInterval(interval);
  }, [id, user, authLoading]);

  const handleDownloadInvoice = async () => {
    const token = localStorage.getItem('fk_customer_token');
    const url = ordersApi.invoiceUrl(order.id);
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      alert('Failed downloading invoice');
      return;
    }
    const blob = await res.blob();
    const blobUrl = URL.createObjectURL(blob);
    window.open(blobUrl, '_blank');
  };

  if (loading) {
    return (
      <div className="min-h-screen flex flex-col">
        <Navbar />
        <div className="flex-1 flex items-center justify-center text-sm text-gray-500">
          Loading order tracking timeline...
        </div>
        <Footer />
      </div>
    );
  }

  if (!order) {
    return (
      <div className="min-h-screen flex flex-col">
        <Navbar />
        <div className="flex-1 max-w-[1240px] mx-auto p-8 text-center">
          <p className="text-red-600 font-bold">Order not found.</p>
          <Link to="/orders" className="text-fk-blue text-sm hover:underline mt-2 inline-block">
            Back to Orders
          </Link>
        </div>
        <Footer />
      </div>
    );
  }

  const addr = order.shipping_address || {};
  const isNonFulfillmentStatus = ['PENDING_PAYMENT', 'CANCELLED', 'CAPTURE_EXCEPTION'].includes(
    order.status
  );
  const invoiceUnavailable = order.status === 'PENDING_PAYMENT' || order.status === 'CANCELLED';

  // Milestone timeline connector rail calculation (active only for standard fulfillment pipeline)
  const totalSteps = order.tracking_history?.length || 0;
  const completedCount = order.tracking_history?.filter((s) => s.completed).length || 0;
  const progressWidth = isNonFulfillmentStatus
    ? 0
    : totalSteps > 1
    ? Math.min(Math.max((Math.max(completedCount - 1, 0) / (totalSteps - 1)) * 100, 0), 100)
    : 0;

  const statusBadgeClass =
    order.status === 'DELIVERED'
      ? 'bg-green-100 text-fk-green'
      : order.status === 'CAPTURE_EXCEPTION' || order.status === 'CANCELLED'
      ? 'bg-red-100 text-red-700'
      : order.status === 'PENDING_PAYMENT'
      ? 'bg-amber-100 text-amber-800'
      : 'bg-blue-50 text-fk-blue';

  return (
    <div className="min-h-screen flex flex-col">
      <Navbar />

      <main className="flex-1 max-w-[1240px] w-full mx-auto px-4 py-6 space-y-4">
        <div className="flex items-center justify-between">
          <Link to="/orders" className="flex items-center gap-1.5 text-xs font-bold text-fk-blue hover:underline">
            <ArrowLeft className="w-4 h-4" /> Back to My Orders
          </Link>
          <button
            onClick={handleDownloadInvoice}
            disabled={invoiceUnavailable}
            title={
              invoiceUnavailable
                ? 'Tax invoice becomes available once payment is captured'
                : 'Download Tax Invoice (PDF)'
            }
            className="flex items-center gap-1.5 bg-white border border-gray-300 hover:border-fk-blue disabled:opacity-50 disabled:cursor-not-allowed text-fk-dark text-xs font-bold px-4 py-2 rounded-sm shadow-sm transition"
          >
            <FileText className="w-4 h-4 text-fk-blue" /> Download Tax Invoice (PDF)
          </button>
        </div>

        {/* Capture Exception Warning Banner */}
        {order.status === 'CAPTURE_EXCEPTION' && (
          <div
            role="alert"
            className="bg-amber-50 border border-amber-300 rounded-sm shadow-sm p-4 flex items-start gap-3 text-xs text-amber-950 apple-panel-enter"
          >
            <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
            <div className="space-y-1">
              <p className="font-bold text-sm text-amber-900">
                Order Under Exception Review ({order.payment_status})
              </p>
              <p className="leading-relaxed text-amber-900">
                {order.payment_status === 'CAPTURE_EXCEPTION_OUT_OF_STOCK'
                  ? 'Your PayPal payment was authorized, but item availability changed before final inventory allocation. Inventory and payment reconciliation is under exception review — support will resolve this order or issue a refund cleanly.'
                  : order.payment_status === 'CAPTURE_AMOUNT_MISMATCH'
                  ? 'Payment verification flagged an amount or capture discrepancy during reconciliation. This order is under exception review and support will resolve or refund cleanly.'
                  : 'Inventory and payment reconciliation for this order is currently under exception review. Support will resolve this order or process a refund cleanly.'}
              </p>
            </div>
          </div>
        )}

        {/* Address & Summary Header */}
        <div className="bg-white rounded-sm shadow-sm p-6 grid grid-cols-1 md:grid-cols-3 gap-6">
          <div>
            <h3 className="text-xs font-bold text-gray-500 uppercase mb-2 flex items-center gap-1.5">
              <MapPin className="w-4 h-4 text-fk-blue" /> Delivery Address
            </h3>
            <p className="text-sm font-bold text-fk-dark">{addr.full_name}</p>
            <p className="text-xs text-gray-600 mt-1 leading-relaxed">
              {addr.street_address}, {addr.locality},<br />
              {addr.city}, {addr.state} - {addr.pincode}
            </p>
            <p className="text-xs font-semibold text-gray-700 mt-1">Phone: {addr.phone}</p>
          </div>

          <div>
            <h3 className="text-xs font-bold text-gray-500 uppercase mb-2">Order Info</h3>
            <p className="text-sm font-bold text-fk-dark">{order.order_number}</p>
            <p className="text-xs text-gray-500 mt-1">
              Placed: {new Date(order.created_at).toLocaleString()}
            </p>
            <p className="text-xs text-gray-500 mt-0.5">Payment: {order.payment_status}</p>
            {order.paypal_order_id && (
              <p className="text-[11px] text-gray-500 mt-1 font-mono break-all">
                PayPal Order ID: {order.paypal_order_id}
              </p>
            )}
            {order.paypal_capture_id && (
              <p className="text-[11px] text-gray-500 mt-0.5 font-mono break-all">
                PayPal Capture ID: {order.paypal_capture_id}
              </p>
            )}
          </div>

          <div className="md:text-right">
            <h3 className="text-xs font-bold text-gray-500 uppercase mb-2">Total Amount</h3>
            <p className="text-2xl font-bold text-fk-dark">₹{order.total_amount.toLocaleString('en-IN')}</p>
            {order.paypal_amount != null && Number(order.paypal_amount) > 0 && (
              <p className="text-xs font-semibold text-fk-blue mt-0.5">
                PayPal Sandbox: ${Number(order.paypal_amount).toFixed(2)} {order.paypal_currency || 'USD'}
              </p>
            )}
            <span className={`inline-block mt-1.5 text-xs font-bold px-2.5 py-0.5 rounded ${statusBadgeClass}`}>
              Status: {order.status}
            </span>
          </div>
        </div>

        {/* Live Tracking Stepper with Animated Progress Rail */}
        <div className="bg-white rounded-sm shadow-sm p-6">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-base font-bold text-fk-dark flex items-center gap-2">
              <Package className="w-5 h-5 text-fk-blue" /> Live Order Tracking
            </h2>
            <button
              onClick={loadOrderData}
              className="flex items-center gap-1.5 text-xs font-semibold text-fk-blue hover:underline"
            >
              <RefreshCw className="w-3.5 h-3.5" /> Refresh Status
            </button>
          </div>

          {isNonFulfillmentStatus ? (
            <div
              className={`rounded border p-4 flex items-start gap-3 text-xs ${
                order.status === 'PENDING_PAYMENT'
                  ? 'bg-blue-50/70 border-blue-200 text-blue-950'
                  : order.status === 'CAPTURE_EXCEPTION'
                  ? 'bg-amber-50 border-amber-200 text-amber-950'
                  : 'bg-gray-50 border-gray-200 text-gray-700'
              }`}
            >
              {order.status === 'PENDING_PAYMENT' ? (
                <Clock className="w-5 h-5 text-fk-blue flex-shrink-0 mt-0.5" />
              ) : order.status === 'CAPTURE_EXCEPTION' ? (
                <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
              ) : (
                <XCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
              )}
              <div>
                <p className="font-bold text-sm">
                  {order.status === 'PENDING_PAYMENT'
                    ? 'Awaiting PayPal Payment Authorization'
                    : order.status === 'CAPTURE_EXCEPTION'
                    ? 'Fulfillment Paused Pending Exception Review'
                    : 'Order Cancelled'}
                </p>
                <p className="mt-1 leading-relaxed text-gray-600">
                  {order.status === 'PENDING_PAYMENT'
                    ? 'Fulfillment milestones will activate once your PayPal Sandbox payment capture completes.'
                    : order.status === 'CAPTURE_EXCEPTION'
                    ? 'Shipment tracking is paused while inventory and payment reconciliation is reviewed by support.'
                    : `This order was cancelled (${order.payment_status}) and will not enter the delivery pipeline.`}
                </p>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-5 gap-4 relative">
              {/* Horizontal progress rail behind circles (desktop) */}
              <div
                className="hidden md:block absolute top-4 left-[10%] right-[10%] h-0.5 bg-gray-200 z-0"
                aria-hidden="true"
              >
                <div
                  className="h-full bg-fk-green apple-gradient-track transition-[width] duration-[650ms] motion-reduce:transition-none"
                  style={{
                    width: `${progressWidth}%`,
                    transitionTimingFunction: 'var(--ease-apple-decel)',
                  }}
                />
              </div>

              {order.tracking_history?.map((step, idx) => (
                <div key={idx} className="relative flex md:flex-col items-start md:items-center gap-3 md:text-center">
                  <div
                    className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 z-10 border-2 ${
                      step.completed
                        ? 'bg-fk-green border-fk-green text-white apple-badge-pop'
                        : 'bg-white border-gray-300 text-gray-300'
                    }`}
                  >
                    <CheckCircle2 className="w-5 h-5" />
                  </div>
                  <div>
                    <p className={`text-xs font-bold ${step.completed ? 'text-fk-dark' : 'text-gray-400'}`}>
                      {step.title}
                    </p>
                    <p className="text-[11px] text-gray-500 mt-0.5">{step.detail}</p>
                    {step.time && (
                      <p className="text-[10px] text-gray-400 mt-0.5">
                        {new Date(step.time).toLocaleDateString()}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Items in Order + Return Action */}
        <div className="bg-white rounded-sm shadow-sm divide-y divide-gray-100">
          <div className="p-4 bg-gray-50">
            <h3 className="font-bold text-sm text-fk-dark">Ordered Items</h3>
          </div>
          {order.items?.map((item) => {
            const activeReturn = returns.find((r) => r.order_item_id === item.id);
            return (
              <div key={item.id} className="p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div className="flex items-center gap-4">
                  <img
                    src={resolveMediaUrl(item.image_url)}
                    alt={item.title}
                    className="w-20 h-20 object-contain border rounded p-1"
                  />
                  <div>
                    <Link to={`/product/${item.product_id}`} className="text-sm font-medium text-fk-dark hover:text-fk-blue">
                      {item.title}
                    </Link>
                    <p className="text-xs text-gray-500 mt-1">
                      Qty: {item.quantity} | Price: ₹{item.price.toLocaleString('en-IN')}
                    </p>
                  </div>
                </div>

                {/* Return / Refund Action */}
                <div className="flex items-center gap-3">
                  {activeReturn ? (
                    <Link
                      to="/orders?tab=returns"
                      className="flex items-center gap-1.5 text-xs font-bold bg-blue-50 text-fk-blue border border-blue-200 px-4 py-2 rounded-sm"
                    >
                      <RefreshCw className="w-3.5 h-3.5" />
                      Return {activeReturn.status} ({activeReturn.return_number})
                    </Link>
                  ) : order.status === 'DELIVERED' ? (
                    <button
                      onClick={() => setReturnModalItem(item)}
                      className="flex items-center gap-1.5 text-xs font-bold bg-white border border-gray-300 hover:border-fk-orange hover:text-fk-orange text-gray-700 px-4 py-2 rounded-sm shadow-sm transition"
                    >
                      <RefreshCw className="w-3.5 h-3.5" /> Return / Refund Item
                    </button>
                  ) : (
                    <span className="text-xs text-gray-400 italic">Return opens upon Delivery</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Connected Refund Intelligence Dossier for Active Returns on this Order */}
        {returns.length > 0 && (
          <div className="space-y-3">
            {returns.map((ret) => (
              <div key={ret.id} className="bg-white rounded-sm shadow-sm p-4 space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-fk-dark">
                    Return {ret.return_number} ({ret.status}) — ₹{ret.refund_amount.toLocaleString('en-IN')}
                  </span>
                  <Link to="/orders?tab=returns" className="text-fk-blue font-semibold hover:underline">
                    View Full Returns Tab
                  </Link>
                </div>
                <RefundIntelligencePanel shipkartReturn={ret} />
              </div>
            ))}
          </div>
        )}
      </main>

      <Footer />

      <ReturnModal
        isOpen={!!returnModalItem}
        onClose={() => setReturnModalItem(null)}
        order={order}
        orderItem={returnModalItem}
        onSuccess={() => {
          loadOrderData();
          navigate('/orders?tab=returns');
        }}
      />
    </div>
  );
}
