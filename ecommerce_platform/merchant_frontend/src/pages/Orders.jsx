import React, { useEffect, useState, useRef } from 'react';
import { Truck, CheckCircle, PackageCheck, ArrowRight } from 'lucide-react';
import { merchantOrdersApi, merchantPaymentsApi, resolveMediaUrl } from '../services/api';
import { useStaggeredReveal } from '../motion/useStaggeredReveal';

const ORDER_STAGES = ['ORDERED', 'PACKED', 'SHIPPED', 'OUT_FOR_DELIVERY', 'DELIVERED'];

const NEXT_STAGE = {
  ORDERED: { next: 'PACKED', label: 'Pack Item', color: 'bg-blue-600 hover:bg-blue-700' },
  PACKED: { next: 'SHIPPED', label: 'Dispatch / Ship', color: 'bg-indigo-600 hover:bg-indigo-700' },
  SHIPPED: { next: 'OUT_FOR_DELIVERY', label: 'Out for Delivery', color: 'bg-amber-600 hover:bg-amber-700' },
  OUT_FOR_DELIVERY: { next: 'DELIVERED', label: 'Mark Delivered', color: 'bg-green-600 hover:bg-green-700' },
};

function paymentBadgeClass(paymentStatus) {
  if (paymentStatus === 'PAID') return 'bg-emerald-50 text-emerald-700 border-emerald-200';
  if (
    paymentStatus?.startsWith('CAPTURE_EXCEPTION') ||
    paymentStatus === 'DENIED' ||
    paymentStatus === 'REVERSED' ||
    paymentStatus === 'PAYPAL_CREATE_FAILED'
  ) {
    return 'bg-red-50 text-red-700 border-red-200';
  }
  if (paymentStatus === 'REFUNDED') return 'bg-purple-50 text-purple-700 border-purple-200';
  return 'bg-gray-100 text-gray-700 border-gray-200';
}

function settlementBadgeClass(settlementStatus) {
  switch (settlementStatus) {
    case 'CAPTURED':
    case 'SETTLED':
    case 'STANDARD_CONFIRMED':
      return 'bg-blue-50 text-seller-blue border-blue-200';
    case 'REFUNDED':
    case 'PARTIALLY_REFUNDED':
      return 'bg-purple-50 text-purple-700 border-purple-200';
    case 'EXCEPTION_REVIEW':
    case 'FAILED':
      return 'bg-amber-50 text-amber-800 border-amber-200';
    case 'CANCELLED':
      return 'bg-gray-100 text-gray-600 border-gray-200';
    default:
      return 'bg-gray-50 text-gray-700 border-gray-200';
  }
}

export default function Orders() {
  const [orders, setOrders] = useState([]);
  const [allocationsMap, setAllocationsMap] = useState({});
  const [loading, setLoading] = useState(true);
  const [updatingId, setUpdatingId] = useState(null);
  const listRef = useRef(null);

  useStaggeredReveal(listRef, {
    triggerKey: `${loading}-${orders.map((o) => o.id).join(',')}`,
  });

  const loadOrders = async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const [ordersRes, allocRes] = await Promise.allSettled([
        merchantOrdersApi.myOrders(),
        merchantPaymentsApi.getAllocations(),
      ]);
      if (ordersRes.status === 'fulfilled') {
        setOrders(ordersRes.value);
      }
      if (allocRes.status === 'fulfilled' && Array.isArray(allocRes.value)) {
        const nextMap = {};
        for (const alloc of allocRes.value) {
          nextMap[alloc.order_id] = alloc;
        }
        setAllocationsMap(nextMap);
      }
    } finally {
      if (!silent) setLoading(false);
    }
  };

  useEffect(() => {
    loadOrders();
  }, []);

  const advanceOrder = async (orderId, nextStatus) => {
    setUpdatingId(orderId);
    try {
      await merchantOrdersApi.updateStatus(orderId, nextStatus);
      await loadOrders(true);
    } catch (err) {
      alert(err.message || 'Status update failed');
    } finally {
      setUpdatingId(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="bg-white p-4 rounded shadow-sm border border-gray-100 flex items-center justify-between">
        <div>
          <h2 className="font-bold text-base text-gray-800">Customer Order Fulfillment Pipeline</h2>
          <p className="text-xs text-gray-500">
            Progress customer orders from Ordered ➔ Packed ➔ Shipped ➔ Delivered (unlocking Return flows)
          </p>
        </div>
      </div>

      {loading ? (
        <div className="bg-white p-8 text-center text-xs text-gray-500 rounded shadow-sm">
          Loading incoming orders...
        </div>
      ) : orders.length === 0 ? (
        <div className="bg-white p-12 text-center text-xs text-gray-500 rounded shadow-sm">
          <PackageCheck className="w-10 h-10 text-gray-300 mx-auto mb-2" />
          No orders placed yet. Incoming customer orders will appear here.
        </div>
      ) : (
        <div ref={listRef} className="space-y-4">
          {orders.map((order) => {
            const transition = NEXT_STAGE[order.status];
            const addr = order.shipping_address || {};
            const stageIdx = ORDER_STAGES.indexOf(order.status);
            const isCancelled = order.status === 'CANCELLED';
            const isCaptureException = order.status === 'CAPTURE_EXCEPTION';
            const isDelivered = order.status === 'DELIVERED';
            const allocation = allocationsMap[order.id];
            const isPayPal = order.payment_method === 'PAYPAL_SANDBOX';
            const hasPaypalAmount = order.paypal_amount != null && Number(order.paypal_amount) > 0;
            const progressPct =
              isCancelled || isCaptureException
                ? 100
                : stageIdx >= 0
                ? Math.round(((stageIdx + 1) / ORDER_STAGES.length) * 100)
                : 0;

            return (
              <div key={order.id} data-staggered-item>
                <div className="bg-white rounded shadow-sm border border-gray-100 p-5 space-y-4 apple-card-hover hover:shadow-md">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b pb-3 gap-3">
                    <div className="space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-bold text-seller-blue">{order.order_number}</span>
                        <span
                          className={`text-[10px] font-bold px-2 py-0.5 rounded border uppercase ${paymentBadgeClass(
                            order.payment_status
                          )}`}
                        >
                          {isPayPal ? 'PayPal' : 'Standard'}: {order.payment_status || 'PENDING'}
                        </span>
                        {allocation && (
                          <span
                            className={`text-[10px] font-bold px-2 py-0.5 rounded border uppercase ${settlementBadgeClass(
                              allocation.settlement_status
                            )}`}
                          >
                            Settlement: {allocation.settlement_status}
                            {Number(allocation.net_merchant_usd) > 0
                              ? ` ($${Number(allocation.net_merchant_usd).toFixed(2)} USD)`
                              : ''}
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-gray-500">
                        Customer: <strong>{addr.full_name}</strong> ({addr.city}, {addr.state} - {addr.pincode})
                      </p>
                      {order.paypal_capture_id && (
                        <p className="text-[11px] text-gray-500 font-mono">
                          Capture ID: {order.paypal_capture_id}
                        </p>
                      )}
                    </div>

                    <div className="flex flex-wrap items-center gap-3">
                      <div className="text-right">
                        <span className="text-sm font-bold text-gray-900 block">
                          ₹{order.total_amount.toLocaleString('en-IN')}{' '}
                          <span className="text-[10px] font-semibold text-gray-400">
                            {order.original_currency || 'INR'}
                          </span>
                        </span>
                        {hasPaypalAmount && (
                          <span className="inline-block text-[11px] font-bold text-seller-blue bg-blue-50 border border-blue-100 px-2 py-0.5 rounded mt-0.5">
                            ${Number(order.paypal_amount).toFixed(2)} {order.paypal_currency || 'USD'}
                          </span>
                        )}
                      </div>
                      <span
                        key={order.status}
                        className={`apple-badge-pop text-xs font-bold px-2.5 py-1 rounded ${
                          isDelivered
                            ? 'bg-green-100 text-green-700'
                            : isCancelled
                            ? 'bg-red-100 text-red-700'
                            : isCaptureException
                            ? 'bg-amber-100 text-amber-800'
                            : 'bg-blue-50 text-seller-blue'
                        }`}
                      >
                        {order.status}
                      </span>

                      {transition && (
                        <button
                          onClick={() => advanceOrder(order.id, transition.next)}
                          disabled={updatingId === order.id}
                          className={`${transition.color} text-white text-xs font-bold px-4 py-1.5 rounded flex items-center gap-1.5 shadow transition`}
                        >
                          <Truck className="w-3.5 h-3.5" />
                          <span>{updatingId === order.id ? 'Updating...' : transition.label}</span>
                          <ArrowRight className="w-3.5 h-3.5" />
                        </button>
                      )}
                      {isDelivered && (
                        <span className="text-xs text-green-600 font-bold flex items-center gap-1">
                          <CheckCircle className="w-4 h-4" /> Completed
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Compact horizontal mini-pipeline progress bar */}
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-[11px] font-semibold text-gray-500">
                      <span className="uppercase tracking-wider text-[10px]">Fulfillment Progress</span>
                      <span
                        className={
                          isDelivered
                            ? 'text-green-600 font-bold'
                            : isCancelled
                            ? 'text-red-600 font-bold'
                            : isCaptureException
                            ? 'text-amber-700 font-bold'
                            : 'text-seller-blue font-bold'
                        }
                      >
                        {isCancelled
                          ? 'Cancelled'
                          : isCaptureException
                          ? 'Exception Review — Fulfillment Paused'
                          : isDelivered
                          ? 'Delivered (100%)'
                          : `${order.status.replace(/_/g, ' ')} (${progressPct}%)`}
                      </span>
                    </div>
                    <div className="h-2 w-full bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-[width] duration-[550ms] motion-reduce:transition-none ${
                          isDelivered
                            ? 'bg-green-600'
                            : isCancelled
                            ? 'bg-red-500'
                            : isCaptureException
                            ? 'bg-amber-500'
                            : 'bg-gradient-to-r from-blue-600 via-indigo-500 to-blue-600 apple-gradient-track'
                        }`}
                        style={{
                          width: `${progressPct}%`,
                          transitionTimingFunction: 'var(--ease-apple-decel)',
                        }}
                      />
                    </div>
                    {!isCancelled && !isCaptureException && (
                      <div className="flex justify-between text-[10px] text-gray-400">
                        {ORDER_STAGES.map((stg, idx) => {
                          const isPassed = stageIdx >= idx;
                          const isCurrent = stageIdx === idx;
                          return (
                            <span
                              key={stg}
                              className={`${
                                isCurrent
                                  ? 'text-seller-blue font-bold'
                                  : isPassed
                                  ? 'text-gray-700 font-medium'
                                  : 'text-gray-400'
                              }`}
                            >
                              {stg === 'OUT_FOR_DELIVERY' ? 'Out for Delivery' : stg.charAt(0) + stg.slice(1).toLowerCase()}
                            </span>
                          );
                        })}
                      </div>
                    )}
                    {isCancelled && (
                      <p className="text-[10px] text-red-500 font-medium">
                        This order was cancelled and removed from the active fulfillment pipeline.
                      </p>
                    )}
                    {isCaptureException && (
                      <p className="text-[10px] text-amber-700 font-medium">
                        Payment capture reconciliation requires exception review before fulfillment can proceed.
                      </p>
                    )}
                  </div>

                  {/* Items */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {order.items?.map((item) => (
                      <div key={item.id} className="flex items-center gap-3 p-2.5 bg-gray-50 rounded border">
                        <img
                          src={resolveMediaUrl(item.image_url)}
                          alt={item.title}
                          className="w-12 h-12 object-contain bg-white border rounded p-0.5"
                        />
                        <div className="text-xs">
                          <p className="font-semibold text-gray-800 line-clamp-1">{item.title}</p>
                          <p className="text-gray-500">
                            Qty: {item.quantity} | ₹{item.price.toLocaleString('en-IN')}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
