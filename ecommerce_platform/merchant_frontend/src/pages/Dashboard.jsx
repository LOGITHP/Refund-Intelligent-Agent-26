import React, { useEffect, useState, useRef } from 'react';
import { Link } from 'react-router-dom';
import { IndianRupee, Package, ShoppingBag, RefreshCw, ArrowRight, Store } from 'lucide-react';
import {
  merchantOrdersApi,
  merchantPaymentsApi,
  merchantProductsApi,
  merchantReturnsApi,
} from '../services/api';
import { useStaggeredReveal } from '../motion/useStaggeredReveal';
import { useCountUp } from '../motion/useCountUp';

export default function Dashboard() {
  const [stats, setStats] = useState({
    revenue: 0,
    totalOrders: 0,
    pendingOrders: 0,
    totalProducts: 0,
    ownedProducts: 0,
    unclaimedStarterProducts: 0,
    paypalConfigured: false,
    pendingReturns: 0,
    recentOrders: [],
    recentReturns: [],
  });
  const [loading, setLoading] = useState(true);

  const containerRef = useRef(null);

  // Animate 4 KPI metrics using easeOutCubic count-up
  const animatedRevenue = useCountUp(loading ? 0 : stats.revenue, { durationMs: 700 });
  const animatedPendingOrders = useCountUp(loading ? 0 : stats.pendingOrders, { durationMs: 700 });
  const animatedPendingReturns = useCountUp(loading ? 0 : stats.pendingReturns, { durationMs: 700 });
  const animatedTotalProducts = useCountUp(loading ? 0 : stats.totalProducts, { durationMs: 700 });

  // Cascade entrance animations across KPI cards and Recent Activity panels
  useStaggeredReveal(containerRef, {
    triggerKey: `${loading}-${stats.totalOrders}-${stats.totalProducts}-${stats.pendingReturns}`,
  });

  useEffect(() => {
    Promise.all([
      merchantProductsApi.myProducts(),
      merchantOrdersApi.myOrders(),
      merchantReturnsApi.myReturns(),
      merchantPaymentsApi.getSettings().catch(() => null),
    ])
      .then(([products, orders, returns, paymentSettings]) => {
        const productList = Array.isArray(products) ? products : [];
        const orderList = Array.isArray(orders) ? orders : [];
        const returnList = Array.isArray(returns) ? returns : [];
        const rev = orderList.reduce((acc, o) => acc + o.total_amount, 0);
        const pendingOrd = orderList.filter((o) => o.status !== 'DELIVERED' && o.status !== 'CANCELLED').length;
        const pendingRet = returnList.filter((r) => r.status === 'REQUESTED' || r.status === 'UNDER_REVIEW').length;
        const ownedCount = productList.filter((p) =>
          paymentSettings?.merchant_id != null
            ? p.merchant_id === paymentSettings.merchant_id
            : p.merchant_id != null
        ).length;
        const unclaimedCount = productList.filter((p) => p.merchant_id == null).length;

        setStats({
          revenue: rev,
          totalOrders: orderList.length,
          pendingOrders: pendingOrd,
          totalProducts: productList.length,
          ownedProducts: ownedCount,
          unclaimedStarterProducts: unclaimedCount,
          paypalConfigured: Boolean(paymentSettings?.paypal_configured),
          pendingReturns: pendingRet,
          recentOrders: orderList.slice(0, 5),
          recentReturns: returnList.slice(0, 5),
        });
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div className="text-sm text-gray-500">Loading Merchant Analytics...</div>;
  }

  return (
    <div ref={containerRef} className="space-y-6">
      {stats.paypalConfigured && stats.ownedProducts === 0 && (
        <div
          data-staggered-item
          className="bg-amber-50 border border-amber-200 text-amber-900 rounded shadow-sm p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
        >
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-full bg-amber-100 text-amber-700 flex-shrink-0">
              <Store className="w-4 h-4" />
            </div>
            <div className="space-y-0.5 text-xs">
              <p className="font-bold text-amber-950">
                Direct PayPal is configured, but your store owns 0 listings yet
              </p>
              <p className="text-amber-800 leading-relaxed">
                Your Direct PayPal keys are active, but starter catalog items are still unclaimed.
                Claim starter items or publish a product in My Listings so customers can check out
                with your PayPal account.
              </p>
            </div>
          </div>
          <Link
            to="/listings"
            className="inline-flex items-center justify-center gap-1.5 bg-seller-blue hover:bg-blue-700 text-white text-xs font-bold px-4 py-2 rounded shadow transition flex-shrink-0"
          >
            <span>Claim in My Listings</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      )}
      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* KPI 1: Gross Order Value */}
        <div data-staggered-item>
          <div className="bg-white rounded p-5 shadow-sm border border-gray-100 apple-card-hover hover:shadow-md hover:-translate-y-0.5">
            <div className="flex items-center justify-between text-gray-500 text-xs font-bold uppercase">
              <span>Gross Order Value</span>
              <IndianRupee className="w-4 h-4 text-green-600" />
            </div>
            <p className="text-2xl font-extrabold text-gray-900 mt-2">
              ₹{animatedRevenue.toLocaleString('en-IN')}
            </p>
            <p className="text-[11px] text-green-600 font-semibold mt-1">
              Across {stats.totalOrders} orders
            </p>
          </div>
        </div>

        {/* KPI 2: Pending Fulfillments */}
        <div data-staggered-item>
          <div className="bg-white rounded p-5 shadow-sm border border-gray-100 apple-card-hover hover:shadow-md hover:-translate-y-0.5">
            <div className="flex items-center justify-between text-gray-500 text-xs font-bold uppercase">
              <span>Pending Fulfillments</span>
              <ShoppingBag className="w-4 h-4 text-seller-blue" />
            </div>
            <p className="text-2xl font-extrabold text-gray-900 mt-2">
              {animatedPendingOrders}
            </p>
            <Link
              to="/orders"
              className="text-[11px] text-seller-blue font-semibold mt-1 inline-flex items-center gap-1 hover:underline"
            >
              Process Orders <ArrowRight className="w-3 h-3" />
            </Link>
          </div>
        </div>

        {/* KPI 3: Open Return Requests */}
        <div data-staggered-item>
          <div className="bg-white rounded p-5 shadow-sm border border-gray-100 apple-card-hover hover:shadow-md hover:-translate-y-0.5">
            <div className="flex items-center justify-between text-gray-500 text-xs font-bold uppercase">
              <span>Open Return Requests</span>
              <RefreshCw className="w-4 h-4 text-orange-500" />
            </div>
            <p className="text-2xl font-extrabold text-gray-900 mt-2">
              {animatedPendingReturns}
            </p>
            <Link
              to="/returns"
              className="text-[11px] text-orange-600 font-semibold mt-1 inline-flex items-center gap-1 hover:underline"
            >
              Inspect Evidence <ArrowRight className="w-3 h-3" />
            </Link>
          </div>
        </div>

        {/* KPI 4: Active Catalog */}
        <div data-staggered-item>
          <div className="bg-white rounded p-5 shadow-sm border border-gray-100 apple-card-hover hover:shadow-md hover:-translate-y-0.5">
            <div className="flex items-center justify-between text-gray-500 text-xs font-bold uppercase">
              <span>Active Catalog</span>
              <Package className="w-4 h-4 text-purple-600" />
            </div>
            <p className="text-2xl font-extrabold text-gray-900 mt-2">
              {animatedTotalProducts}
            </p>
            <div className="mt-1 flex flex-wrap items-center justify-between gap-1">
              <Link
                to="/listings"
                className="text-[11px] text-purple-600 font-semibold inline-flex items-center gap-1 hover:underline"
              >
                Manage Inventory <ArrowRight className="w-3 h-3" />
              </Link>
              {stats.unclaimedStarterProducts > 0 && (
                <span className="text-[10px] font-bold text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded border border-amber-200">
                  {stats.ownedProducts} owned · {stats.unclaimedStarterProducts} starter
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Recent Activity Panels */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Orders */}
        <div data-staggered-item>
          <div className="bg-white rounded shadow-sm border border-gray-100 overflow-hidden apple-card-hover hover:shadow-md">
            <div className="px-5 py-3.5 border-b flex justify-between items-center bg-gray-50">
              <h3 className="font-bold text-sm text-gray-800">Recent Incoming Orders</h3>
              <Link to="/orders" className="text-xs font-bold text-seller-blue hover:underline">
                View All
              </Link>
            </div>
            <div className="divide-y divide-gray-100">
              {stats.recentOrders.length === 0 ? (
                <p className="p-6 text-xs text-gray-400 text-center">No orders placed yet.</p>
              ) : (
                stats.recentOrders.map((ord) => (
                  <div key={ord.id} className="p-4 flex items-center justify-between text-xs">
                    <div>
                      <p className="font-bold text-gray-800">{ord.order_number}</p>
                      <p className="text-gray-500">{ord.items?.length} item(s)</p>
                    </div>
                    <div className="text-right">
                      <p className="font-bold text-gray-900">₹{ord.total_amount.toLocaleString('en-IN')}</p>
                      <span className="inline-block px-2 py-0.5 rounded bg-blue-50 text-seller-blue font-bold mt-0.5">
                        {ord.status}
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Recent Returns */}
        <div data-staggered-item>
          <div className="bg-white rounded shadow-sm border border-gray-100 overflow-hidden apple-card-hover hover:shadow-md">
            <div className="px-5 py-3.5 border-b flex justify-between items-center bg-gray-50">
              <h3 className="font-bold text-sm text-gray-800">Recent Return Claims</h3>
              <Link to="/returns" className="text-xs font-bold text-seller-blue hover:underline">
                View Console
              </Link>
            </div>
            <div className="divide-y divide-gray-100">
              {stats.recentReturns.length === 0 ? (
                <p className="p-6 text-xs text-gray-400 text-center">No return requests yet.</p>
              ) : (
                stats.recentReturns.map((ret) => (
                  <div key={ret.id} className="p-4 flex items-center justify-between text-xs">
                    <div>
                      <p className="font-bold text-gray-800">{ret.return_number}</p>
                      <p className="text-gray-500 line-clamp-1">{ret.reason}</p>
                    </div>
                    <div className="text-right">
                      <p className="font-bold text-red-600">₹{ret.refund_amount.toLocaleString('en-IN')}</p>
                      <span className="inline-block px-2 py-0.5 rounded bg-amber-50 text-amber-800 font-bold mt-0.5">
                        {ret.status}
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
