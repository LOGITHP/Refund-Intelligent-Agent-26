import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { Link } from 'react-router-dom';
import {
  ShieldCheck,
  Zap,
  RefreshCw,
  Star,
  ArrowRight,
  ChevronDown,
} from 'lucide-react';
import { useScrollProgress } from '../motion/useScrollProgress';
import { usePrefersReducedMotion } from '../motion/usePrefersReducedMotion';
import { lerp } from '../motion/math';
import { resolveMediaUrl } from '../services/api';

const CHAPTERS = [
  {
    step: '01',
    eyebrow: 'Shipkart Studio Spotlight',
    title: 'Discover Genuine Hardware',
    desc: '100% verified authentic consumer electronics from certified partners, backed by strict multi-point hardware audits.',
    calloutBadge: 'Shipkart Assured',
  },
  {
    step: '02',
    eyebrow: 'Real-Time Logistics',
    title: 'Live 5-Stage Order Telemetry',
    desc: 'Track your package in real time from merchant packing to doorstep delivery with automated milestone notifications.',
    calloutBadge: 'Live 5-Stage Tracking',
  },
  {
    step: '03',
    eyebrow: 'Buyer Protection',
    title: 'Instant Invoices & 7-Day Returns',
    desc: 'Downloadable GST tax invoices at dispatch, with automated doorstep pickup and instant refund turnaround.',
    calloutBadge: '7-Day Instant Return',
  },
];

const FALLBACK_PRODUCTS = [
  {
    id: 'spotlight-1',
    title: 'Apple MacBook Pro M3 Max (16-inch, 36GB Unified Memory)',
    brand: 'Apple',
    price: 249900,
    mrp: 299900,
    rating: 4.9,
    reviews_count: 1420,
    is_assured: true,
    image_url: 'https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=800&auto=format&fit=crop&q=80',
  },
  {
    id: 'spotlight-2',
    title: 'Sony WH-1000XM5 Wireless Noise Cancelling Studio Headphones',
    brand: 'Sony',
    price: 29990,
    mrp: 34990,
    rating: 4.8,
    reviews_count: 3840,
    is_assured: true,
    image_url: 'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=800&auto=format&fit=crop&q=80',
  },
  {
    id: 'spotlight-3',
    title: 'UltraVision Pro 34-inch Curved QD-OLED Studio Display',
    brand: 'UltraVision',
    price: 68999,
    mrp: 89999,
    rating: 4.7,
    reviews_count: 890,
    is_assured: true,
    image_url: 'https://images.unsplash.com/photo-1527443224154-c4a3942d3acf?w=800&auto=format&fit=crop&q=80',
  },
  {
    id: 'spotlight-4',
    title: 'Keychron Q1 Pro Wireless Custom Mechanical Keyboard',
    brand: 'Keychron',
    price: 18499,
    mrp: 22999,
    rating: 4.9,
    reviews_count: 2150,
    is_assured: true,
    image_url: 'https://images.unsplash.com/photo-1587829741301-dc798b83add3?w=800&auto=format&fit=crop&q=80',
  },
];

const PARTICLES = Array.from({ length: 24 }, (_, i) => ({
  xRatio: ((i * 37 + 13) % 100) / 100,
  yRatio: ((i * 47 + 29) % 100) / 100,
  radius: (i % 3) + 1,
  baseAlpha: 0.12 + (i % 5) * 0.06,
  parallaxFactor: 0.3 + (i % 4) * 0.25,
}));

export default function StickyShowcase({
  products = [],
  loading = false,
  onExploreCatalog,
}) {
  const trackRef = useRef(null);
  const stageRef = useRef(null);
  const canvasRef = useRef(null);

  const prefersReducedMotion = usePrefersReducedMotion();
  const scrollProgress = useScrollProgress(trackRef, { reducedMotion: prefersReducedMotion });

  const [cachedProducts, setCachedProducts] = useState([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [isPaused, setIsPaused] = useState(false);
  const [mouseOffset, setMouseOffset] = useState({ x: 0, y: 0 });

  // Cache initial catalog spotlight items so filtering doesn't empty the showcase
  useEffect(() => {
    if (Array.isArray(products) && products.length > 0) {
      setCachedProducts((prev) => (prev.length === 0 ? products.slice(0, 4) : prev));
    }
  }, [products]);

  const spotlightItems = useMemo(() => {
    if (cachedProducts.length > 0) return cachedProducts;
    if (Array.isArray(products) && products.length > 0) return products.slice(0, 4);
    return FALLBACK_PRODUCTS;
  }, [cachedProducts, products]);

  const safeIndex = activeIndex < spotlightItems.length ? activeIndex : 0;
  const activeProduct = spotlightItems[safeIndex] || FALLBACK_PRODUCTS[0];

  // Auto-advance timer: 5000ms, paused on hover/focus, disabled on prefersReducedMotion
  useEffect(() => {
    if (prefersReducedMotion || isPaused || spotlightItems.length <= 1) return;

    const timer = setInterval(() => {
      setActiveIndex((prev) => (prev + 1) % spotlightItems.length);
    }, 5000);

    return () => clearInterval(timer);
  }, [prefersReducedMotion, isPaused, spotlightItems.length]);

  // Narrative chapter index based on scrollProgress [0..0.33], [0.33..0.66], [0.66..1.0]
  const currentChapterIndex =
    scrollProgress < 0.33 ? 0 : scrollProgress < 0.66 ? 1 : 2;
  const activeChapter = CHAPTERS[currentChapterIndex];

  // Keep scrollProgress accessible to the stable resize handler without re-subscribing
  const scrollProgressRef = useRef(scrollProgress);
  useEffect(() => {
    scrollProgressRef.current = scrollProgress;
  }, [scrollProgress]);

  // Pure canvas renderer accepting progress value
  const renderCanvas = useCallback((progress) => {
    const stage = stageRef.current;
    const canvas = canvasRef.current;
    if (!stage || !canvas) return;

    const rect = stage.getBoundingClientRect();
    const width = Math.max(Math.floor(rect.width), 1);
    const height = Math.max(Math.floor(rect.height), 1);
    const dpr = Math.min(window.devicePixelRatio || 1, 2);

    const targetWidth = Math.round(width * dpr);
    const targetHeight = Math.round(height * dpr);

    if (canvas.width !== targetWidth || canvas.height !== targetHeight) {
      canvas.width = targetWidth;
      canvas.height = targetHeight;
    }

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.save();
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, width, height);

    // 1. Studio background gradient
    const bgGrad = ctx.createLinearGradient(0, 0, width, height);
    bgGrad.addColorStop(0, '#0b1524');
    bgGrad.addColorStop(0.5, '#101c2e');
    bgGrad.addColorStop(1, '#172337');
    ctx.fillStyle = bgGrad;
    ctx.fillRect(0, 0, width, height);

    // 2. Depth grid
    ctx.strokeStyle = 'rgba(56, 189, 248, 0.05)';
    ctx.lineWidth = 1;
    const gridSpacing = 44;
    const gridOffset = (progress * 88) % gridSpacing;
    for (let x = -gridSpacing + gridOffset; x < width + gridSpacing; x += gridSpacing) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }
    for (let y = -gridSpacing + gridOffset; y < height + gridSpacing; y += gridSpacing) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }

    // 3. Diagonal sweeping radial spotlight
    const spotX = lerp(width * 0.25, width * 0.75, progress);
    const spotY = lerp(height * 0.2, height * 0.65, progress);
    const spotRadius = Math.max(width, height) * 0.68;
    const spotGrad = ctx.createRadialGradient(spotX, spotY, 20, spotX, spotY, spotRadius);
    spotGrad.addColorStop(0, 'rgba(56, 189, 248, 0.18)');
    spotGrad.addColorStop(0.35, 'rgba(37, 99, 235, 0.12)');
    spotGrad.addColorStop(0.7, 'rgba(30, 58, 138, 0.04)');
    spotGrad.addColorStop(1, 'rgba(11, 21, 36, 0)');
    ctx.fillStyle = spotGrad;
    ctx.fillRect(0, 0, width, height);

    // 4. Orbital measurement arcs
    const isDesktop = width >= 768;
    const cx = isDesktop ? width * 0.72 : width * 0.5;
    const cy = isDesktop ? height * 0.5 : height * 0.45;
    const baseRadius = Math.min(width, height) * (isDesktop ? 0.36 : 0.26);

    // Arc 1 - Main sweep
    const rot1 = progress * Math.PI * 1.5;
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = 'rgba(56, 189, 248, 0.22)';
    ctx.beginPath();
    ctx.arc(cx, cy, baseRadius, rot1, rot1 + Math.PI * 0.85);
    ctx.stroke();

    // Arc 2 - Counter-rotating inner dashed arc
    ctx.save();
    ctx.setLineDash([4, 8]);
    ctx.strokeStyle = 'rgba(147, 197, 253, 0.16)';
    ctx.beginPath();
    ctx.arc(cx, cy, baseRadius * 0.75, -rot1 * 0.7, -rot1 * 0.7 + Math.PI * 1.1);
    ctx.stroke();
    ctx.restore();

    // Arc 3 - Outer thin tracking ring
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.06)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(cx, cy, baseRadius * 1.2, 0, Math.PI * 2);
    ctx.stroke();

    // Orbital dot indicator
    const dotAngle = rot1 + Math.PI * 0.42;
    const dotX = cx + Math.cos(dotAngle) * baseRadius;
    const dotY = cy + Math.sin(dotAngle) * baseRadius;
    ctx.fillStyle = '#38bdf8';
    ctx.beginPath();
    ctx.arc(dotX, dotY, 3, 0, Math.PI * 2);
    ctx.fill();

    // 5. Parallax light particles
    PARTICLES.forEach((p) => {
      const px = (p.xRatio * width + Math.sin(progress * 4 + p.yRatio * 8) * 14) % width;
      const py = (p.yRatio * height - progress * height * p.parallaxFactor * 0.35 + height) % height;
      ctx.fillStyle = `rgba(186, 230, 253, ${p.baseAlpha})`;
      ctx.beginPath();
      ctx.arc(px, py, p.radius, 0, Math.PI * 2);
      ctx.fill();
    });

    ctx.restore();
  }, []);

  // Stable stage resize observation effect (ResizeObserver + window resize listener)
  // Decoupled from scrollProgress so observers are NEVER recreated on scroll
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;

    const handleResize = () => {
      renderCanvas(scrollProgressRef.current);
    };

    handleResize();

    let ro = null;
    if (typeof ResizeObserver !== 'undefined') {
      ro = new ResizeObserver(handleResize);
      ro.observe(stage);
    }

    window.addEventListener('resize', handleResize);

    return () => {
      if (ro) ro.disconnect();
      window.removeEventListener('resize', handleResize);
    };
  }, [renderCanvas]);

  // Lightweight redraw effect triggered whenever scrollProgress changes
  useEffect(() => {
    renderCanvas(scrollProgress);
  }, [scrollProgress, renderCanvas]);

  // Mouse parallax
  const handleMouseMove = (e) => {
    if (prefersReducedMotion) return;
    const stage = stageRef.current;
    if (!stage) return;
    const rect = stage.getBoundingClientRect();
    if (rect.width < 768) return;
    const nx = ((e.clientX - rect.left) / rect.width - 0.5) * 2;
    const ny = ((e.clientY - rect.top) / rect.height - 0.5) * 2;
    setMouseOffset({
      x: Math.min(Math.max(nx, -1), 1),
      y: Math.min(Math.max(ny, -1), 1),
    });
  };

  const handleMouseLeave = () => {
    setIsPaused(false);
    setMouseOffset({ x: 0, y: 0 });
  };

  const handleBrowseCatalog = (e) => {
    if (e) e.preventDefault();
    if (typeof onExploreCatalog === 'function') {
      onExploreCatalog();
    } else {
      const el = document.getElementById('catalog-grid');
      if (el) {
        el.scrollIntoView({ behavior: prefersReducedMotion ? 'auto' : 'smooth' });
      }
    }
  };

  const hardwareTransforms = useMemo(() => {
    if (prefersReducedMotion) {
      return {
        transform: 'perspective(1000px) translate3d(0, 0, 0) rotateY(0deg) scale(1)',
      };
    }

    let scaleVal;
    let translateYVal;
    let rotateYVal;

    if (scrollProgress <= 0.5) {
      const t = scrollProgress / 0.5;
      scaleVal = lerp(0.92, 1.04, t);
      translateYVal = lerp(12, -8, t);
      rotateYVal = lerp(-8, 0, t);
    } else {
      const t = (scrollProgress - 0.5) / 0.5;
      scaleVal = lerp(1.04, 0.98, t);
      translateYVal = lerp(-8, 6, t);
      rotateYVal = lerp(0, 8, t);
    }

    // Damped mouse parallax
    const mouseRotY = mouseOffset.x * 6;
    const mouseRotX = -mouseOffset.y * 5;
    const mouseTransX = mouseOffset.x * 8;
    const totalRotY = rotateYVal + mouseRotY;
    const totalTransY = translateYVal + mouseOffset.y * 6;

    return {
      transform: `perspective(1000px) translate3d(${mouseTransX.toFixed(2)}px, ${totalTransY.toFixed(2)}px, 0px) rotateX(${mouseRotX.toFixed(2)}deg) rotateY(${totalRotY.toFixed(2)}deg) scale(${scaleVal.toFixed(3)})`,
      transition: isPaused ? 'transform 260ms cubic-bezier(0.33, 1, 0.68, 1)' : 'none',
    };
  }, [scrollProgress, mouseOffset, prefersReducedMotion, isPaused]);

  return (
    <div
      ref={trackRef}
      className="relative w-full mb-6 md:min-h-[1240px] md:h-[205vh]"
    >
      <div
        ref={stageRef}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        onMouseEnter={() => setIsPaused(true)}
        onFocus={() => setIsPaused(true)}
        onBlur={() => setIsPaused(false)}
        className="relative w-full overflow-hidden rounded-2xl md:sticky md:top-16 md:h-[calc(100vh-88px)] md:max-h-[580px] bg-gradient-to-br from-[#0b1524] via-[#101c2d] to-[#172337] text-white shadow-2xl border border-slate-800/80 p-5 sm:p-6 md:p-8 flex flex-col justify-between"
      >
        {/* Hardware-accelerated background canvas */}
        <canvas
          ref={canvasRef}
          className="absolute inset-0 w-full h-full pointer-events-none z-0"
          aria-hidden="true"
        />

        {/* Content & 3D Stage Grid */}
        <div className="relative z-10 grid grid-cols-1 md:grid-cols-12 gap-6 lg:gap-8 items-center h-full">
          {/* Left Column: Narrative Copy, Product Details, CTAs, DotNav */}
          <div className="md:col-span-7 flex flex-col justify-between h-full space-y-4">
            <div>
              {/* Narrative Chapter Indicators */}
              <div className="flex items-center gap-2 mb-3">
                {CHAPTERS.map((chap, idx) => {
                  const isCurrent = idx === currentChapterIndex;
                  return (
                    <span
                      key={chap.step}
                      className={`text-[11px] font-semibold px-2.5 py-0.5 rounded-full transition-colors duration-300 ${
                        isCurrent
                          ? 'bg-sky-500/20 text-sky-300 border border-sky-400/40 shadow-sm shadow-sky-500/10'
                          : 'bg-white/5 text-slate-400 border border-transparent'
                      }`}
                    >
                      {chap.step} {chap.calloutBadge}
                    </span>
                  );
                })}
              </div>

              {/* TextOverMedia Narrative Copy */}
              <div className="space-y-1.5 min-h-[88px]">
                <p className="text-xs uppercase tracking-wider font-bold text-sky-400">
                  {activeChapter.eyebrow}
                </p>
                <h2 className="text-2xl sm:text-3xl lg:text-4xl font-extrabold tracking-tight text-white line-clamp-1">
                  {activeChapter.title}
                </h2>
                <p className="text-slate-300 text-xs sm:text-sm max-w-lg line-clamp-2">
                  {activeChapter.desc}
                </p>
              </div>

              {/* Active Spotlight Product Card Snippet */}
              <div className="bg-white/5 backdrop-blur-md border border-white/10 rounded-xl p-3 sm:p-4 mt-3 max-w-lg">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <span className="text-[10px] font-bold tracking-widest text-sky-400 uppercase">
                      {activeProduct.brand || 'Shipkart Studio'}
                    </span>
                    <h3 className="text-sm sm:text-base font-semibold text-white truncate mt-0.5">
                      {activeProduct.title}
                    </h3>
                    <div className="flex items-center gap-2 mt-1.5">
                      <span className="bg-emerald-500/90 text-white text-[11px] font-bold px-1.5 py-0.5 rounded flex items-center gap-0.5">
                        {activeProduct.rating || 4.8} <Star className="w-3 h-3 fill-current" />
                      </span>
                      <span className="text-xs text-slate-400">
                        ({(activeProduct.reviews_count || 1200).toLocaleString()})
                      </span>
                      {activeProduct.is_assured && (
                        <span className="inline-flex items-center gap-1 text-[10px] bg-sky-400/20 text-sky-300 border border-sky-400/30 font-bold px-1.5 py-0.5 rounded uppercase tracking-wider">
                          <ShieldCheck className="w-3 h-3" /> Assured
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="text-right flex-shrink-0">
                    <div className="text-base sm:text-lg font-bold text-white">
                      ₹{Number(activeProduct.price || 0).toLocaleString('en-IN')}
                    </div>
                    {activeProduct.mrp && activeProduct.mrp > activeProduct.price && (
                      <div className="text-[11px] text-slate-400 line-through">
                        ₹{Number(activeProduct.mrp).toLocaleString('en-IN')}
                      </div>
                    )}
                    <div className="text-[10px] font-bold text-emerald-400">Free delivery</div>
                  </div>
                </div>
              </div>
            </div>

            {/* Action Buttons & DotNav */}
            <div className="space-y-4 pt-2">
              <div className="flex flex-wrap items-center gap-3">
                <Link
                  to={`/product/${activeProduct.id}`}
                  className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg bg-sky-500 hover:bg-sky-400 text-slate-950 font-bold text-sm shadow-lg shadow-sky-500/25 transition-all duration-200 hover:scale-[1.02] active:scale-[0.98]"
                >
                  <span>Explore Product</span>
                  <ArrowRight className="w-4 h-4" />
                </Link>
                <button
                  type="button"
                  onClick={handleBrowseCatalog}
                  className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg bg-white/10 hover:bg-white/15 text-white font-semibold text-sm border border-white/15 backdrop-blur transition-all duration-200 hover:scale-[1.02] active:scale-[0.98]"
                >
                  <span>Browse All Products</span>
                  <ChevronDown className="w-4 h-4" />
                </button>
              </div>

              {/* Apple DotNav Capsule Pill Switcher */}
              <div
                className="flex items-center gap-2 pt-1"
                role="tablist"
                aria-label="Spotlight Products"
              >
                {spotlightItems.map((item, idx) => {
                  const isActive = idx === safeIndex;
                  return (
                    <button
                      key={item.id || idx}
                      type="button"
                      role="tab"
                      aria-selected={isActive}
                      aria-label={`Spotlight slide ${idx + 1}: ${item.title}`}
                      onClick={() => setActiveIndex(idx)}
                      className={`relative h-2 rounded-full overflow-hidden transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-sky-400 focus:ring-offset-1 focus:ring-offset-slate-900 ${
                        isActive ? 'w-8 bg-white/30' : 'w-2 bg-white/20 hover:bg-white/40'
                      }`}
                    >
                      {isActive && (
                        <span
                          key={`fill-${safeIndex}-${isPaused}`}
                          className="dotnav-pill-fill absolute inset-0 bg-white rounded-full"
                          style={{
                            animation:
                              !prefersReducedMotion && !isPaused
                                ? 'apple-dotnav-fill 5000ms linear forwards'
                                : 'none',
                            transform:
                              !prefersReducedMotion && !isPaused ? undefined : 'scaleX(1)',
                          }}
                        />
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Right Column: Layered 3D Perspective Hardware Stage */}
          <div className="md:col-span-5 flex items-center justify-center">
            <div className="relative flex items-center justify-center w-full h-[240px] sm:h-[280px] md:h-[360px] lg:h-[400px]">
              {/* Specular halo behind product */}
              <div className="absolute w-56 h-56 sm:w-64 sm:h-64 rounded-full bg-sky-500/15 blur-3xl pointer-events-none" />

              {/* 3D Hardware Perspective Stage */}
              <div
                style={hardwareTransforms}
                className="relative z-10 w-full max-w-[280px] sm:max-w-[320px] md:max-w-[340px] aspect-square flex items-center justify-center p-4 select-none"
              >
                <div className="relative w-full h-full flex items-center justify-center bg-slate-900/60 backdrop-blur-xl border border-white/10 rounded-2xl p-5 shadow-2xl overflow-hidden group">
                  {/* Subtle specular sheen */}
                  <div className="absolute inset-0 bg-gradient-to-tr from-sky-500/10 via-transparent to-white/10 opacity-60 pointer-events-none" />

                  {/* Spotlight Product Image */}
                  <img
                    src={resolveMediaUrl(activeProduct.image_url)}
                    alt={activeProduct.title}
                    className="max-h-full max-w-full object-contain filter drop-shadow-[0_16px_24px_rgba(0,0,0,0.5)] transition-transform duration-500 group-hover:scale-105"
                    onError={(e) => {
                      e.target.src = 'https://placehold.co/400x400/101c2e/38bdf8?text=Shipkart+Spotlight';
                    }}
                  />
                </div>

                {/* Floating Feature Callout Chips */}
                {/* 1. Shipkart Assured Chip (Top-Right) */}
                <div
                  className={`absolute -top-2 -right-2 sm:-top-3 sm:-right-3 z-20 flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold backdrop-blur-md border shadow-xl transition-all duration-300 ${
                    currentChapterIndex === 0
                      ? 'bg-sky-500/90 text-slate-950 border-sky-300 scale-105 shadow-sky-500/30'
                      : 'bg-slate-900/80 text-slate-300 border-white/15'
                  }`}
                >
                  <ShieldCheck className="w-3.5 h-3.5" />
                  <span>Shipkart Assured</span>
                </div>

                {/* 2. Live 5-Stage Tracking Chip (Bottom-Left) */}
                <div
                  className={`absolute -bottom-2 -left-2 sm:-bottom-3 sm:-left-3 z-20 flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold backdrop-blur-md border shadow-xl transition-all duration-300 ${
                    currentChapterIndex === 1
                      ? 'bg-sky-500/90 text-slate-950 border-sky-300 scale-105 shadow-sky-500/30'
                      : 'bg-slate-900/80 text-slate-300 border-white/15'
                  }`}
                >
                  <Zap className="w-3.5 h-3.5" />
                  <span>Live 5-Stage Tracking</span>
                </div>

                {/* 3. 7-Day Instant Return Chip (Bottom-Right) */}
                <div
                  className={`absolute -bottom-2 -right-2 sm:-bottom-3 sm:-right-3 z-20 flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold backdrop-blur-md border shadow-xl transition-all duration-300 ${
                    currentChapterIndex === 2
                      ? 'bg-sky-500/90 text-slate-950 border-sky-300 scale-105 shadow-sky-500/30'
                      : 'bg-slate-900/80 text-slate-300 border-white/15'
                  }`}
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  <span>7-Day Instant Return</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
