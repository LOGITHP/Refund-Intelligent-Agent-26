import React from 'react';
import { Link } from 'react-router-dom';
import { Star } from 'lucide-react';
import { resolveMediaUrl } from '../services/api';

export default function ProductCard({ product }) {
  const discountPercent = Math.round(((product.mrp - product.price) / product.mrp) * 100);

  return (
    <Link
      to={`/product/${product.id}`}
      className="apple-card-hover bg-white p-4 rounded-sm shadow-sm hover:shadow-lg hover:-translate-y-1 hover:border-gray-200/80 flex flex-col justify-between group border border-transparent h-full"
    >
      <div>
        {/* Product Image */}
        <div className="w-full h-48 flex items-center justify-center overflow-hidden mb-3 bg-gray-50 rounded">
          <img
            src={resolveMediaUrl(product.image_url)}
            alt={product.title}
            className="max-h-full max-w-full object-contain group-hover:scale-105 transition-transform duration-300"
            onError={(e) => {
              e.target.src = 'https://placehold.co/300x300?text=Product+Image';
            }}
          />
        </div>

        {/* Brand */}
        <span className="text-xs text-gray-400 uppercase font-bold tracking-wider">{product.brand}</span>

        {/* Title */}
        <h3 className="text-sm font-medium text-fk-dark line-clamp-2 mt-0.5 group-hover:text-fk-blue transition-colors">
          {product.title}
        </h3>

        {/* Ratings & Shipkart Assured */}
        <div className="flex items-center gap-2 mt-2">
          <span className="bg-fk-green text-white text-[11px] font-bold px-1.5 py-0.5 rounded flex items-center gap-0.5">
            {product.rating} <Star className="w-3 h-3 fill-current" />
          </span>
          <span className="text-xs text-gray-500">({product.reviews_count.toLocaleString()})</span>
          {product.is_assured && (
            <span className="text-[10px] bg-yellow-100 text-yellow-800 font-bold px-1.5 py-0.5 rounded uppercase tracking-wider ml-auto">
              Assured
            </span>
          )}
        </div>

        {/* Seller Attribution & PayPal Ready Pill */}
        <div className="flex items-center justify-between gap-2 mt-2 min-h-[20px]">
          <span className="text-[11px] text-gray-500 truncate">
            Sold by {product.seller_name || 'Shipkart Store'}
          </span>
          {product.paypal_ready && (
            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-blue-50 text-fk-blue border border-blue-200 flex-shrink-0">
              PayPal Ready
            </span>
          )}
        </div>
      </div>

      {/* Price block */}
      <div className="mt-3 pt-2 border-t border-gray-100">
        <div className="flex items-baseline gap-2">
          <span className="text-base font-bold text-fk-dark">₹{product.price.toLocaleString('en-IN')}</span>
          <span className="text-xs text-gray-400 line-through">₹{product.mrp.toLocaleString('en-IN')}</span>
          <span className="text-xs text-fk-green font-bold">{discountPercent}% off</span>
        </div>
        <p className="text-[11px] text-gray-500 mt-0.5">Free delivery</p>
      </div>
    </Link>
  );
}

