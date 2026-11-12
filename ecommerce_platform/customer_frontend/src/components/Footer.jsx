import React from 'react';
import { Link } from 'react-router-dom';
import { ShieldCheck, Truck, RefreshCw } from 'lucide-react';
import { ABOUT_NAV_ITEMS, POLICY_NAV_ITEMS } from '../data/infoPages';

export default function Footer() {
  return (
    <footer className="bg-[#172337] text-white mt-12">
      <div className="max-w-[1240px] mx-auto px-4 py-10 grid grid-cols-1 md:grid-cols-3 gap-8 text-xs">
        <div>
          <h4 className="text-gray-400 font-semibold uppercase mb-3 tracking-wider">About</h4>
          <ul className="space-y-1.5 text-gray-200">
            {ABOUT_NAV_ITEMS.map((item) => (
              <li key={item.key}>
                <Link to={item.to} className="hover:underline hover:text-fk-yellow transition">
                  {item.label}
                </Link>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h4 className="text-gray-400 font-semibold uppercase mb-3 tracking-wider">Consumer Policy</h4>
          <ul className="space-y-1.5 text-gray-200">
            {POLICY_NAV_ITEMS.map((item) => (
              <li key={item.key}>
                <Link to={item.to} className="hover:underline hover:text-fk-yellow transition">
                  {item.label}
                </Link>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h4 className="text-gray-400 font-semibold uppercase mb-3 tracking-wider">Trust Guarantees</h4>
          <div className="space-y-3 text-gray-200">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-fk-yellow" />
              <span>Shipkart Assured Quality</span>
            </div>
            <div className="flex items-center gap-2">
              <Truck className="w-4 h-4 text-fk-yellow" />
              <span>Real-Time Delivery Tracking</span>
            </div>
            <div className="flex items-center gap-2">
              <RefreshCw className="w-4 h-4 text-fk-yellow" />
              <span>Fast & Transparent Returns</span>
            </div>
          </div>
        </div>
      </div>
      <div className="border-t border-gray-700 py-4 text-center text-xs text-gray-400">
        © 2026 Shipkart E-Commerce — All Rights Reserved
      </div>
    </footer>
  );
}
