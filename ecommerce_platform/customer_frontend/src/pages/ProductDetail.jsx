import React, { useEffect, useState, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ShoppingCart, Zap, Star, ShieldCheck, RefreshCw, Truck, Store } from 'lucide-react';
import Navbar from '../components/Navbar';
import Footer from '../components/Footer';
import { productsApi, resolveMediaUrl } from '../services/api';
import { useCart } from '../context/CartContext';
import { useAuth } from '../context/AuthContext';
import AuthModal from '../components/AuthModal';
import { usePrefersReducedMotion } from '../motion/usePrefersReducedMotion';
import { useStaggeredReveal } from '../motion/useStaggeredReveal';

export default function ProductDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { addToCart } = useCart();
  const { user } = useAuth();
  const prefersReducedMotion = usePrefersReducedMotion();

  const [product, setProduct] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [isAuthOpen, setIsAuthOpen] = useState(false);
  const [addingToCart, setAddingToCart] = useState(false);
  const [isHovered, setIsHovered] = useState(false);

  // Gallery stage 3D perspective & spotlight sheen refs
  const galleryBoxRef = useRef(null);
  const rafIdRef = useRef(null);
  const tiltCurrentRef = useRef({ rx: 0, ry: 0, mx: 50, my: 50 });
  const tiltTargetRef = useRef({ rx: 0, ry: 0, mx: 50, my: 50 });

  // Right details container stagger ref
  const detailsRef = useRef(null);
  useStaggeredReveal(detailsRef, {
    triggerKey: `${loading}-${product?.id ?? ''}`,
    delayMs: 60,
  });

  // Check if interactive tilt / spotlight sheen motion is disabled
  const isMotionDisabled = useCallback(() => {
    if (prefersReducedMotion) return true;
    if (typeof window === 'undefined') return true;
    if (window.innerWidth < 768) return true;
    if (
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(hover: none), (pointer: coarse)').matches
    ) {
      return true;
    }
    return false;
  }, [prefersReducedMotion]);

  // Smooth rAF damping loop for 3D card tilt & radial spotlight
  const stepTilt = useCallback(() => {
    const el = galleryBoxRef.current;
    if (!el) {
      rafIdRef.current = null;
      return;
    }

    const curr = tiltCurrentRef.current;
    const tgt = tiltTargetRef.current;

    // Smooth damping factor
    const damping = 0.15;
    curr.rx += (tgt.rx - curr.rx) * damping;
    curr.ry += (tgt.ry - curr.ry) * damping;
    curr.mx += (tgt.mx - curr.mx) * damping;
    curr.my += (tgt.my - curr.my) * damping;

    el.style.transform = `perspective(800px) rotateX(${curr.rx.toFixed(2)}deg) rotateY(${curr.ry.toFixed(2)}deg)`;
    el.style.setProperty('--mx', `${curr.mx.toFixed(2)}%`);
    el.style.setProperty('--my', `${curr.my.toFixed(2)}%`);

    const delta =
      Math.abs(tgt.rx - curr.rx) +
      Math.abs(tgt.ry - curr.ry) +
      Math.abs(tgt.mx - curr.mx) +
      Math.abs(tgt.my - curr.my);

    if (delta > 0.02) {
      rafIdRef.current = requestAnimationFrame(stepTilt);
    } else {
      curr.rx = tgt.rx;
      curr.ry = tgt.ry;
      curr.mx = tgt.mx;
      curr.my = tgt.my;
      el.style.transform = `perspective(800px) rotateX(${curr.rx.toFixed(2)}deg) rotateY(${curr.ry.toFixed(2)}deg)`;
      el.style.setProperty('--mx', `${curr.mx.toFixed(2)}%`);
      el.style.setProperty('--my', `${curr.my.toFixed(2)}%`);
      rafIdRef.current = null;
    }
  }, []);

  const handleMouseMove = useCallback(
    (e) => {
      if (isMotionDisabled()) return;

      const el = galleryBoxRef.current;
      if (!el) return;

      const rect = el.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) return;

      // Normalized coordinates within the element [0, 1]
      const relX = (e.clientX - rect.left) / rect.width;
      const relY = (e.clientY - rect.top) / rect.height;

      const clampedX = Math.min(Math.max(relX, 0), 1);
      const clampedY = Math.min(Math.max(relY, 0), 1);

      // Centered coordinate in [-1, 1]
      const normX = (clampedX - 0.5) * 2;
      const normY = (clampedY - 0.5) * 2;

      // Tilt angles clamped to ±6deg:
      const maxDeg = 6;
      const targetRx = Math.min(Math.max(-normY * maxDeg, -maxDeg), maxDeg);
      const targetRy = Math.min(Math.max(normX * maxDeg, -maxDeg), maxDeg);

      tiltTargetRef.current = {
        rx: targetRx,
        ry: targetRy,
        mx: clampedX * 100,
        my: clampedY * 100,
      };

      if (!isHovered) {
        setIsHovered(true);
      }

      if (!rafIdRef.current) {
        rafIdRef.current = requestAnimationFrame(stepTilt);
      }
    },
    [isMotionDisabled, isHovered, stepTilt]
  );

  const handleMouseLeave = useCallback(() => {
    if (rafIdRef.current) {
      cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = null;
    }
    setIsHovered(false);

    tiltCurrentRef.current = { rx: 0, ry: 0, mx: 50, my: 50 };
    tiltTargetRef.current = { rx: 0, ry: 0, mx: 50, my: 50 };

    const el = galleryBoxRef.current;
    if (el) {
      el.style.transform = '';
      el.style.removeProperty('--mx');
      el.style.removeProperty('--my');
    }
  }, []);

  // Cleanup pending rAF on unmount
  useEffect(() => {
    return () => {
      if (rafIdRef.current) {
        cancelAnimationFrame(rafIdRef.current);
        rafIdRef.current = null;
      }
    };
  }, []);

  // Reset tilt and spotlight if reduced motion is enabled or window resized below breakpoint
  useEffect(() => {
    if (isMotionDisabled()) {
      handleMouseLeave();
    }
  }, [isMotionDisabled, handleMouseLeave]);

  // Clean reload on product ID change
  useEffect(() => {
    setLoading(true);
    setError('');
    productsApi
      .get(id)
      .then((data) => setProduct(data))
      .catch((err) => setError(err.message || 'Product not found'))
      .finally(() => setLoading(false));
  }, [id]);

  const handleAddToCart = async () => {
    if (!user) {
      setIsAuthOpen(true);
      return;
    }
    setAddingToCart(true);
    try {
      await addToCart(product.id, 1);
      navigate('/cart');
    } catch (err) {
      alert(err.message || 'Failed adding to cart');
    } finally {
      setAddingToCart(false);
    }
  };

  const handleBuyNow = () => {
    if (!user) {
      setIsAuthOpen(true);
      return;
    }
    navigate(`/checkout?buy_now_product_id=${product.id}&quantity=1`);
  };

  if (loading) {
    return (
      <div className="min-h-screen flex flex-col">
        <Navbar />
        <div className="flex-1 max-w-[1240px] w-full mx-auto p-4 flex items-center justify-center">
          <div className="text-gray-500 text-sm">Loading product details...</div>
        </div>
        <Footer />
      </div>
    );
  }

  if (error || !product) {
    return (
      <div className="min-h-screen flex flex-col">
        <Navbar />
        <div className="flex-1 max-w-[1240px] w-full mx-auto p-8 text-center">
          <p className="text-red-600 font-semibold">{error || 'Product not found'}</p>
          <button onClick={() => navigate('/')} className="mt-4 text-fk-blue font-bold hover:underline">
            Back to Home
          </button>
        </div>
        <Footer />
      </div>
    );
  }

  const discountPercent = Math.round(((product.mrp - product.price) / product.mrp) * 100);

  return (
    <div className="min-h-screen flex flex-col">
      <Navbar />

      <main className="flex-1 max-w-[1240px] w-full mx-auto px-4 py-4">
        <div className="bg-white rounded-sm shadow-sm p-6 grid grid-cols-1 md:grid-cols-12 gap-8">
          {/* Left Column: Image Gallery Stage & Sticky CTA Buttons (5 cols) */}
          <div className="md:col-span-5 flex flex-col">
            <div
              ref={galleryBoxRef}
              onMouseMove={handleMouseMove}
              onMouseLeave={handleMouseLeave}
              className="relative border border-gray-200 rounded p-6 flex items-center justify-center h-96 bg-gray-50/50 overflow-hidden select-none will-change-transform"
              style={{
                transformStyle: 'preserve-3d',
              }}
            >
              {/* Radial Spotlight Sheen Overlay */}
              <div
                className="pointer-events-none absolute inset-0 transition-opacity duration-300"
                style={{
                  opacity: isHovered && !isMotionDisabled() ? 1 : 0,
                  background:
                    'radial-gradient(circle 260px at var(--mx, 50%) var(--my, 50%), rgba(255, 255, 255, 0.65), transparent 75%)',
                }}
                aria-hidden="true"
              />

              <img
                src={resolveMediaUrl(product.image_url)}
                alt={product.title}
                className="max-h-full max-w-full object-contain pointer-events-none select-none"
                onError={(e) => {
                  e.target.src = 'https://placehold.co/400x400?text=Product+Image';
                }}
              />
            </div>

            {/* Action Buttons with Spring Feedback */}
            <div className="grid grid-cols-2 gap-3 mt-6">
              <button
                onClick={handleAddToCart}
                disabled={addingToCart || product.stock <= 0}
                className="bg-[#ff9f00] hover:bg-[#f39700] active:scale-[0.98] motion-reduce:active:scale-100 text-white font-bold py-3 px-4 rounded-sm shadow flex items-center justify-center gap-2 transition duration-150 disabled:opacity-50 disabled:pointer-events-none"
                style={{ transitionTimingFunction: 'var(--ease-apple-spring)' }}
              >
                <ShoppingCart className="w-5 h-5" />
                <span>{addingToCart ? 'ADDING...' : 'ADD TO CART'}</span>
              </button>

              <button
                onClick={handleBuyNow}
                disabled={product.stock <= 0}
                className="bg-fk-orange hover:bg-orange-600 active:scale-[0.98] motion-reduce:active:scale-100 text-white font-bold py-3 px-4 rounded-sm shadow flex items-center justify-center gap-2 transition duration-150 disabled:opacity-50 disabled:pointer-events-none"
                style={{ transitionTimingFunction: 'var(--ease-apple-spring)' }}
              >
                <Zap className="w-5 h-5 fill-current" />
                <span>BUY NOW</span>
              </button>
            </div>
            {product.stock <= 0 && (
              <p className="text-red-600 font-semibold text-center text-xs mt-2">Currently Out of Stock</p>
            )}
          </div>

          {/* Right Column: Title, Ratings, Pricing, Specs (7 cols) with Staggered Entrance */}
          <div ref={detailsRef} className="md:col-span-7 space-y-4">
            <div data-staggered-item>
              <span className="text-xs text-gray-400 font-bold uppercase tracking-wider">{product.brand}</span>
              <h1 className="text-xl md:text-2xl font-medium text-fk-dark mt-1 leading-snug">
                {product.title}
              </h1>
            </div>

            {/* Rating pill */}
            <div data-staggered-item className="flex items-center gap-3">
              <span className="bg-fk-green text-white text-xs font-bold px-2 py-0.5 rounded flex items-center gap-1">
                {product.rating} <Star className="w-3.5 h-3.5 fill-current" />
              </span>
              <span className="text-sm text-gray-500 font-medium">
                {product.reviews_count.toLocaleString()} Ratings & Reviews
              </span>
              {product.is_assured && (
                <span className="text-xs bg-yellow-100 text-yellow-800 font-bold px-2 py-0.5 rounded uppercase tracking-wider">
                  Shipkart Assured
                </span>
              )}
            </div>

            {/* Seller & Checkout Rail Indicator */}
            <div
              data-staggered-item
              className="flex flex-wrap items-center gap-2.5 text-xs bg-gray-50/80 border border-gray-200/80 rounded px-3 py-2"
            >
              <span className="text-gray-600 flex items-center gap-1.5">
                <Store className="w-3.5 h-3.5 text-fk-blue flex-shrink-0" />
                <span>
                  Sold by:{' '}
                  <strong className="text-fk-dark font-semibold">
                    {product.seller_name || 'Shipkart Platform Catalog'}
                  </strong>
                </span>
              </span>
              <span className="text-gray-300 hidden sm:inline">|</span>
              {product.paypal_ready ? (
                <span className="inline-flex items-center text-[11px] font-bold px-2 py-0.5 rounded bg-blue-50 text-fk-blue border border-blue-200">
                  Direct PayPal + Standard Checkout
                </span>
              ) : (
                <span className="inline-flex items-center text-[11px] font-semibold px-2 py-0.5 rounded bg-gray-100 text-gray-600 border border-gray-200">
                  Standard Checkout
                </span>
              )}
            </div>

            {/* Special Price Tag */}
            <div data-staggered-item className="pt-2">
              <span className="text-xs text-fk-green font-bold">Special price</span>
              <div className="flex items-baseline gap-3 mt-0.5">
                <span className="text-3xl font-bold text-fk-dark">₹{product.price.toLocaleString('en-IN')}</span>
                <span className="text-base text-gray-400 line-through">₹{product.mrp.toLocaleString('en-IN')}</span>
                <span className="text-base text-fk-green font-bold">{discountPercent}% off</span>
              </div>
            </div>

            {/* Trust Badges */}
            <div data-staggered-item className="grid grid-cols-3 gap-3 border-y border-gray-100 py-3 text-xs text-gray-600">
              <div className="flex items-center gap-2">
                <Truck className="w-5 h-5 text-fk-blue" />
                <span>Free Express Delivery</span>
              </div>
              <div className="flex items-center gap-2">
                <RefreshCw className="w-5 h-5 text-fk-blue" />
                <span>7-Day Return / Refund Policy</span>
              </div>
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-fk-blue" />
                <span>100% Genuine Guarantee</span>
              </div>
            </div>

            {/* Highlights */}
            {product.highlights?.length > 0 && (
              <div data-staggered-item className="space-y-1.5 pt-2">
                <h3 className="text-sm font-bold text-gray-800">Highlights</h3>
                <ul className="list-disc list-inside text-xs text-gray-600 space-y-1">
                  {product.highlights.map((h, i) => (
                    <li key={i}>{h}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Description */}
            <div data-staggered-item className="space-y-1.5 pt-2">
              <h3 className="text-sm font-bold text-gray-800">Description</h3>
              <p className="text-xs text-gray-600 leading-relaxed">{product.description}</p>
            </div>

            {/* Specifications Table */}
            {product.specifications && Object.keys(product.specifications).length > 0 && (
              <div data-staggered-item className="space-y-2 pt-2">
                <h3 className="text-sm font-bold text-gray-800">Specifications</h3>
                <div className="border border-gray-200 rounded text-xs divide-y divide-gray-100">
                  {Object.entries(product.specifications).map(([key, value]) => (
                    <div key={key} className="grid grid-cols-3 p-2.5">
                      <span className="text-gray-500 font-medium">{key}</span>
                      <span className="col-span-2 text-gray-800">{value}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </main>

      <Footer />
      <AuthModal isOpen={isAuthOpen} onClose={() => setIsAuthOpen(false)} />
    </div>
  );
}
