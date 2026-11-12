import React, { useEffect, useState, useRef } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Package, RefreshCw, CheckCircle2, ChevronRight, XCircle, Image as ImageIcon } from 'lucide-react';
import Navbar from '../components/Navbar';
import Footer from '../components/Footer';
import RefundIntelligencePanel from '../components/RefundIntelligencePanel';
import { ordersApi, resolveMediaUrl, returnsApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { useStaggeredReveal } from '../motion/useStaggeredReveal';

export default function Orders() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTab = searchParams.get('tab') === 'returns' ? 'returns' : 'orders';
  const [activeTab, setActiveTab] = useState(initialTab);
  const [orders, setOrders] = useState([]);
  const [returns, setReturns] = useState([]);
  const [loading, setLoading] = useState(true);

  const { user, loading: authLoading } = useAuth();
  const navigate = useNavigate();

  // Container ref for staggered cascade on cards
  const listContainerRef = useRef(null);
  useStaggeredReveal(listContainerRef, {
    triggerKey: `${loading}-${activeTab}-${orders.map((o) => o.id).join(',')}-${returns.map((r) => r.id).join(',')}`,
    delayMs: 65,
  });

  const loadHistory = async () => {
    try {
      const [ordList, retList] = await Promise.all([ordersApi.myOrders(), returnsApi.myReturns()]);
      setOrders(ordList);
      setReturns(retList);
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
    loadHistory();
    const interval = setInterval(loadHistory, 3000);
    return () => clearInterval(interval);
  }, [user, authLoading]);

  const switchTab = (tab) => {
    setActiveTab(tab);
    setSearchParams(tab === 'returns' ? { tab: 'returns' } : {});
  };

  return (
    <div className="min-h-screen flex flex-col">
      <Navbar />

      <main className="flex-1 max-w-[1240px] w-full mx-auto px-4 py-6 space-y-4">
        {/* Tab Bar */}
        <div className="bg-white rounded-sm shadow-sm flex border-b">
          <button
            onClick={() => switchTab('orders')}
            className={`flex items-center gap-2 px-6 py-3.5 text-sm font-bold border-b-2 transition ${
              activeTab === 'orders'
                ? 'border-fk-blue text-fk-blue bg-blue-50/30'
                : 'border-transparent text-gray-600 hover:text-fk-dark'
            }`}
          >
            <Package className="w-4 h-4" /> My Orders ({orders.length})
          </button>
          <button
            onClick={() => switchTab('returns')}
            className={`flex items-center gap-2 px-6 py-3.5 text-sm font-bold border-b-2 transition ${
              activeTab === 'returns'
                ? 'border-fk-blue text-fk-blue bg-blue-50/30'
                : 'border-transparent text-gray-600 hover:text-fk-dark'
            }`}
          >
            <RefreshCw className="w-4 h-4" /> Returns & Refund Tracking ({returns.length})
          </button>
        </div>

        {loading ? (
          <div className="bg-white p-12 text-center text-sm text-gray-500 rounded-sm shadow-sm">
            Loading your history...
          </div>
        ) : (
          <div ref={listContainerRef}>
            {activeTab === 'orders' ? (
              /* ORDERS LIST */
              orders.length === 0 ? (
                <div className="bg-white p-12 text-center rounded-sm shadow-sm">
                  <Package className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                  <p className="text-base font-bold text-fk-dark">No orders placed yet</p>
                  <Link to="/" className="mt-3 inline-block text-sm text-fk-blue font-bold hover:underline">
                    Start Shopping
                  </Link>
                </div>
              ) : (
                <div className="space-y-3">
                  {orders.map((order) => (
                    <div key={order.id} data-staggered-item>
                      <Link
                        to={`/orders/${order.id}/track`}
                        className="block bg-white rounded-sm shadow-sm hover:shadow-md transition p-5 border border-transparent hover:border-blue-100"
                      >
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b pb-3 mb-3">
                          <div>
                            <span className="text-xs font-bold text-fk-blue">{order.order_number}</span>
                            <p className="text-[11px] text-gray-400">
                              Placed on {new Date(order.created_at).toLocaleString()}
                            </p>
                          </div>
                          <div className="flex items-center gap-4">
                            <span className="text-sm font-bold text-fk-dark">
                              ₹{order.total_amount.toLocaleString('en-IN')}
                            </span>
                            <span
                              className={`text-xs font-bold px-2.5 py-0.5 rounded ${
                                order.status === 'DELIVERED'
                                  ? 'bg-green-100 text-fk-green'
                                  : order.status === 'CANCELLED'
                                  ? 'bg-red-100 text-red-600'
                                  : 'bg-blue-100 text-fk-blue'
                              }`}
                            >
                              {order.status}
                            </span>
                            <ChevronRight className="w-4 h-4 text-gray-400" />
                          </div>
                        </div>

                        <div className="space-y-2">
                          {order.items?.map((item) => (
                            <div key={item.id} className="flex items-center gap-3">
                              <img
                                src={resolveMediaUrl(item.image_url)}
                                alt={item.title}
                                className="w-12 h-12 object-contain border rounded p-0.5"
                              />
                              <div>
                                <p className="text-xs font-medium text-fk-dark">{item.title}</p>
                                <p className="text-[11px] text-gray-500">
                                  Qty: {item.quantity} | ₹{item.price.toLocaleString('en-IN')}
                                </p>
                              </div>
                            </div>
                          ))}
                        </div>
                      </Link>
                    </div>
                  ))}
                </div>
              )
            ) : /* RETURNS & REFUND TRACKING LIST */
            returns.length === 0 ? (
              <div className="bg-white p-12 text-center rounded-sm shadow-sm">
                <RefreshCw className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                <p className="text-base font-bold text-fk-dark">No return requests found</p>
                <p className="text-xs text-gray-500 mt-1">
                  Delivered items can be returned directly from the Order Tracking screen.
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                {returns.map((ret) => {
                  const totalSteps = ret.tracking_history?.length || 0;
                  const isRejected =
                    ret.status === 'REJECTED' ||
                    ret.tracking_history?.some(
                      (s) => s.step === 'REJECTED' || s.step === 'AGENT_REJECTED'
                    );
                  const rejectedIndex = ret.tracking_history?.findIndex(
                    (s) => s.step === 'REJECTED' || s.step === 'AGENT_REJECTED'
                  );

                  let progressWidth = 0;
                  if (totalSteps > 1) {
                    if (isRejected && rejectedIndex >= 0) {
                      progressWidth = (rejectedIndex / (totalSteps - 1)) * 100;
                    } else {
                      const completedCount =
                        ret.tracking_history?.filter((s) => s.completed).length || 0;
                      progressWidth = (Math.max(completedCount - 1, 0) / (totalSteps - 1)) * 100;
                    }
                  }
                  progressWidth = Math.min(Math.max(progressWidth, 0), 100);

                  return (
                    <div key={ret.id} data-staggered-item>
                      <div className="bg-white rounded-sm shadow-sm p-6 space-y-5">
                        {/* Header */}
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b pb-4 gap-3">
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-bold text-fk-dark">{ret.return_number}</span>
                              <span
                                className={`text-xs font-bold px-2.5 py-0.5 rounded ${
                                  ret.status === 'REFUNDED' || ret.status === 'APPROVED'
                                    ? 'bg-green-100 text-fk-green'
                                    : ret.status === 'REJECTED'
                                    ? 'bg-red-100 text-red-600'
                                    : 'bg-amber-100 text-amber-800'
                                }`}
                              >
                                {ret.status}
                              </span>
                            </div>
                            <p className="text-xs text-gray-500 mt-1">Reason: {ret.reason}</p>
                          </div>
                          <div className="sm:text-right">
                            <p className="text-xs text-gray-400">Refund Amount</p>
                            <p className="text-lg font-bold text-fk-green">
                              ₹{ret.refund_amount.toLocaleString('en-IN')}
                            </p>
                            {ret.refund_transaction_id && (
                              <p className="text-[11px] text-gray-500 font-mono">
                                TXN: {ret.refund_transaction_id}
                              </p>
                            )}
                          </div>
                        </div>

                        {/* Live Refund Tracking Stepper with Animated Progress Rail */}
                        <div>
                          <h4 className="text-xs font-bold text-gray-500 uppercase mb-4">
                            Live Refund Progress
                          </h4>
                          <div className="grid grid-cols-1 md:grid-cols-6 gap-3 relative">
                            {/* Horizontal progress rail behind circles (desktop) */}
                            <div
                              className="hidden md:block absolute top-3.5 left-[8.333%] right-[8.333%] h-0.5 bg-gray-200 z-0"
                              aria-hidden="true"
                            >
                              <div
                                className={`h-full ${
                                  isRejected ? 'bg-red-500' : 'bg-fk-green apple-gradient-track'
                                } transition-[width] duration-[650ms] motion-reduce:transition-none`}
                                style={{
                                  width: `${progressWidth}%`,
                                  transitionTimingFunction: 'var(--ease-apple-decel)',
                                }}
                              />
                            </div>

                            {ret.tracking_history?.map((step, idx) => {
                              const isStepRejected =
                                step.step === 'REJECTED' || step.step === 'AGENT_REJECTED';
                              const isPop = isStepRejected || step.completed;

                              return (
                                <div
                                  key={idx}
                                  className="relative flex md:flex-col items-start md:items-center gap-2 md:text-center"
                                >
                                  <div
                                    className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 z-10 border-2 ${
                                      isStepRejected
                                        ? 'bg-red-600 border-red-600 text-white'
                                        : step.completed
                                        ? 'bg-fk-green border-fk-green text-white'
                                        : 'bg-white border-gray-300 text-gray-300'
                                    } ${isPop ? 'apple-badge-pop' : ''}`}
                                  >
                                    {isStepRejected ? (
                                      <XCircle className="w-4 h-4" />
                                    ) : (
                                      <CheckCircle2 className="w-4 h-4" />
                                    )}
                                  </div>
                                  <div>
                                    <p
                                      className={`text-xs font-bold ${
                                        step.completed || isStepRejected ? 'text-fk-dark' : 'text-gray-400'
                                      }`}
                                    >
                                      {step.title}
                                    </p>
                                    <p className="text-[10px] text-gray-500 mt-0.5">{step.detail}</p>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </div>

                        {/* Uploaded Evidence Preview */}
                        {ret.evidence_urls?.length > 0 && (
                          <div className="border-t pt-4">
                            <p className="text-xs font-bold text-gray-500 uppercase mb-2 flex items-center gap-1.5">
                              <ImageIcon className="w-3.5 h-3.5 text-fk-blue" /> Submitted Evidence Photos
                            </p>
                            <div className="flex flex-wrap gap-2">
                              {ret.evidence_urls.map((url, idx) => (
                                <a
                                  key={idx}
                                  href={resolveMediaUrl(url)}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="w-16 h-16 border rounded overflow-hidden hover:ring-2 ring-fk-blue transition"
                                >
                                  <img
                                    src={resolveMediaUrl(url)}
                                    alt="Evidence"
                                    className="w-full h-full object-cover"
                                  />
                                </a>
                              ))}
                            </div>
                          </div>
                        )}

                        {ret.merchant_notes && (
                          <div className="bg-gray-50 border p-3 rounded text-xs text-gray-700">
                            <strong>Resolution Note:</strong> {ret.merchant_notes}
                          </div>
                        )}

                        <RefundIntelligencePanel shipkartReturn={ret} />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </main>

      <Footer />
    </div>
  );
}
