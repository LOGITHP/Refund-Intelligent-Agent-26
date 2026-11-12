import React, { useEffect, useState, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { SlidersHorizontal, ShieldCheck, Zap } from 'lucide-react';
import Navbar from '../components/Navbar';
import CategoryBar from '../components/CategoryBar';
import ProductCard from '../components/ProductCard';
import StickyShowcase from '../components/StickyShowcase';
import Footer from '../components/Footer';
import { productsApi } from '../services/api';
import { useStaggeredReveal } from '../motion/useStaggeredReveal';

export default function Home() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedCategory, setSelectedCategory] = useState(searchParams.get('category') || 'all');
  const [searchQuery, setSearchQuery] = useState(searchParams.get('search') || '');
  const [onlyAssured, setOnlyAssured] = useState(false);
  const [maxPrice, setMaxPrice] = useState(200000);

  const gridRef = useRef(null);
  useStaggeredReveal(gridRef, {
    triggerKey: `${loading}-${products.map((p) => p.id).join(',')}`,
    delayMs: 65,
  });

  const fetchProducts = async () => {
    setLoading(true);
    try {
      const data = await productsApi.list({
        category: selectedCategory !== 'all' ? selectedCategory : undefined,
        search: searchQuery || undefined,
        only_assured: onlyAssured ? 'true' : undefined,
        max_price: maxPrice < 200000 ? maxPrice : undefined,
      });
      setProducts(data);
    } catch (err) {
      console.error('Failed loading products:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProducts();
  }, [selectedCategory, searchQuery, onlyAssured, maxPrice]);

  const handleCategoryChange = (cat) => {
    setSelectedCategory(cat);
    if (cat === 'all') {
      searchParams.delete('category');
    } else {
      searchParams.set('category', cat);
    }
    setSearchParams(searchParams);
  };

  const handleSearch = (term) => {
    setSearchQuery(term);
  };

  return (
    <div className="min-h-screen flex flex-col">
      <Navbar onSearch={handleSearch} />
      <CategoryBar selectedCategory={selectedCategory} onSelectCategory={handleCategoryChange} />

      <main className="flex-1 max-w-[1240px] w-full mx-auto px-4 py-4 space-y-4">
        {/* Apple-inspired Sticky Canvas Hardware Showcase */}
        <StickyShowcase products={products} loading={loading} />

        {/* Main Content Grid: Filter Sidebar + Product Grid */}
        <div className="flex flex-col md:flex-row gap-4">
          {/* Left Filter Panel */}
          <aside className="w-full md:w-64 flex-shrink-0 bg-white rounded-sm shadow-sm p-4 h-fit space-y-6">
            <div className="flex items-center justify-between border-b pb-3">
              <h2 className="font-bold text-base flex items-center gap-2">
                <SlidersHorizontal className="w-4 h-4 text-fk-blue" />
                Filters
              </h2>
              <button
                onClick={() => {
                  setSelectedCategory('all');
                  setSearchQuery('');
                  setOnlyAssured(false);
                  setMaxPrice(200000);
                }}
                className="text-xs text-fk-blue font-semibold hover:underline"
              >
                CLEAR ALL
              </button>
            </div>

            {/* Max Price Filter */}
            <div className="space-y-2 border-b pb-4">
              <div className="flex justify-between text-xs font-bold uppercase text-gray-600">
                <span>Max Price</span>
                <span className="text-fk-blue">
                  {maxPrice >= 200000 ? 'Any' : `₹${maxPrice.toLocaleString('en-IN')}`}
                </span>
              </div>
              <input
                type="range"
                min="5000"
                max="200000"
                step="5000"
                value={maxPrice}
                onChange={(e) => setMaxPrice(Number(e.target.value))}
                className="w-full accent-fk-blue cursor-pointer"
              />
              <div className="flex justify-between text-[11px] text-gray-400">
                <span>₹5k</span>
                <span>₹100k</span>
                <span>₹200k+</span>
              </div>
            </div>

            {/* Assured Toggle */}
            <div className="space-y-2">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={onlyAssured}
                  onChange={(e) => setOnlyAssured(e.target.checked)}
                  className="w-4 h-4 accent-fk-blue rounded"
                />
                <span className="text-sm font-medium flex items-center gap-1">
                  <ShieldCheck className="w-4 h-4 text-fk-blue" />
                  Shipkart Assured
                </span>
              </label>
            </div>
          </aside>

          {/* Product Grid */}
          <section className="flex-1 bg-white rounded-sm shadow-sm p-4">
            <div className="flex items-center justify-between border-b pb-3 mb-4">
              <div>
                <h2 className="font-bold text-lg text-fk-dark">
                  {selectedCategory === 'all' ? 'Featured Products' : `${selectedCategory} Showcase`}
                </h2>
                <p className="text-xs text-gray-500">
                  Showing {products.length} {products.length === 1 ? 'result' : 'results'}
                  {searchQuery && ` for "${searchQuery}"`}
                </p>
              </div>
            </div>

            {loading ? (
              <div id="catalog-grid" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {[1, 2, 3, 4, 5, 6].map((n) => (
                  <div key={n} className="h-72 bg-gray-100 animate-pulse rounded" />
                ))}
              </div>
            ) : products.length === 0 ? (
              <div id="catalog-grid" className="text-center py-16 text-gray-500">
                <p className="text-base font-medium">No products found matching your criteria.</p>
                <button
                  onClick={() => {
                    setSelectedCategory('all');
                    setSearchQuery('');
                  }}
                  className="mt-3 text-sm text-fk-blue font-semibold hover:underline"
                >
                  Reset Filters
                </button>
              </div>
            ) : (
              <div
                id="catalog-grid"
                ref={gridRef}
                className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"
              >
                {products.map((product) => (
                  <div key={product.id} data-staggered-item className="h-full">
                    <ProductCard product={product} />
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      </main>

      <Footer />
    </div>
  );
}

