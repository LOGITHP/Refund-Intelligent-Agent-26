import React, { useEffect, useState, useRef } from 'react';
import {
  Plus,
  UploadCloud,
  Trash2,
  X,
  CheckCircle,
  Pencil,
  Store,
  ShieldCheck,
  AlertTriangle,
  Loader2,
  CheckCircle2,
} from 'lucide-react';
import { merchantProductsApi, resolveMediaUrl } from '../services/api';
import { useStaggeredReveal } from '../motion/useStaggeredReveal';

const INITIAL_FORM = {
  title: '',
  brand: '',
  category: 'Electronics',
  description: '',
  price: '',
  mrp: '',
  sandbox_usd_price: '',
  stock: '20',
  image_url: '',
};

export default function Listings() {
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [editingProduct, setEditingProduct] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [claimingId, setClaimingId] = useState(null);
  const [claimingAll, setClaimingAll] = useState(false);
  const [actionError, setActionError] = useState('');
  const [actionSuccess, setActionSuccess] = useState('');
  const tbodyRef = useRef(null);

  useStaggeredReveal(tbodyRef, {
    triggerKey: `${loading}-${products.map((p) => `${p.id}-${p.merchant_id ?? 'starter'}`).join(',')}`,
  });

  const [form, setForm] = useState(INITIAL_FORM);

  const loadProducts = async () => {
    setLoading(true);
    try {
      const data = await merchantProductsApi.myProducts();
      setProducts(Array.isArray(data) ? data : []);
    } catch (err) {
      setActionError(err.message || 'Failed loading catalog listings.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProducts();
  }, []);

  const unclaimedStarterProducts = products.filter((p) => p.merchant_id == null);

  const handleClaimProduct = async (product) => {
    setActionError('');
    setActionSuccess('');
    setClaimingId(product.id);
    try {
      await merchantProductsApi.claim(product.id);
      await loadProducts();
      setActionSuccess(`Claimed "${product.title}" to your store.`);
    } catch (err) {
      setActionError(err.message || 'Failed claiming listing to your store.');
    } finally {
      setClaimingId(null);
    }
  };

  const handleClaimAllStarter = async () => {
    setActionError('');
    setActionSuccess('');
    setClaimingAll(true);
    try {
      const res = await merchantProductsApi.claimStarter();
      await loadProducts();
      const claimedCount =
        typeof res?.claimed_count === 'number'
          ? res.claimed_count
          : unclaimedStarterProducts.length;
      setActionSuccess(
        `Claimed ${claimedCount} starter catalog item${claimedCount === 1 ? '' : 's'} to your store. Direct PayPal checkout now applies to your store listings.`
      );
    } catch (err) {
      setActionError(err.message || 'Failed claiming starter catalog items.');
    } finally {
      setClaimingAll(false);
    }
  };

  const openCreateModal = () => {
    setEditingProduct(null);
    setForm(INITIAL_FORM);
    setIsAddOpen(true);
  };

  const openEditModal = (product) => {
    setEditingProduct(product);
    setForm({
      title: product.title || '',
      brand: product.brand || '',
      category: product.category || 'Electronics',
      description: product.description || '',
      price: product.price != null ? String(product.price) : '',
      mrp: product.mrp != null ? String(product.mrp) : '',
      sandbox_usd_price:
        product.sandbox_usd_price != null ? Number(product.sandbox_usd_price).toFixed(2) : '',
      stock: product.stock != null ? String(product.stock) : '0',
      image_url: product.image_url || '',
    });
    setIsAddOpen(true);
  };

  const closeModal = () => {
    setIsAddOpen(false);
    setEditingProduct(null);
  };

  const handleImageUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const res = await merchantProductsApi.uploadImage(file);
      setForm((prev) => ({ ...prev, image_url: res.url }));
    } catch (err) {
      alert(err.message || 'Image upload failed');
    } finally {
      setUploading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const rawUsd = form.sandbox_usd_price.trim();
    let parsedUsd;
    if (rawUsd !== '') {
      parsedUsd = Number(rawUsd);
      if (Number.isNaN(parsedUsd) || parsedUsd <= 0) {
        alert('PayPal Sandbox USD price must be greater than $0.00 (or leave blank to auto-calculate).');
        return;
      }
      parsedUsd = Number(parsedUsd.toFixed(2));
    }

    setSaving(true);
    try {
      if (editingProduct) {
        const updatePayload = {
          title: form.title,
          brand: form.brand,
          category: form.category,
          description: form.description,
          price: Number(form.price),
          mrp: Number(form.mrp),
          stock: Number(form.stock),
          ...(form.image_url ? { image_url: form.image_url } : {}),
          ...(parsedUsd !== undefined ? { sandbox_usd_price: parsedUsd } : {}),
        };
        await merchantProductsApi.update(editingProduct.id, updatePayload);
      } else {
        const createPayload = {
          title: form.title,
          brand: form.brand,
          category: form.category,
          description: form.description,
          price: Number(form.price),
          mrp: Number(form.mrp),
          stock: Number(form.stock),
          image_url: form.image_url || '/api/v1/media/files/product-images/sony_xm5.svg',
          highlights: ['Shipkart Assured Seller Quality', '7-Day Return Policy Supported'],
          specifications: { Category: form.category, Brand: form.brand },
          ...(parsedUsd !== undefined ? { sandbox_usd_price: parsedUsd } : {}),
        };
        await merchantProductsApi.create(createPayload);
      }
      closeModal();
      setForm(INITIAL_FORM);
      await loadProducts();
    } catch (err) {
      alert(err.message || (editingProduct ? 'Failed updating product' : 'Failed creating product'));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('Deactivate this listing?')) return;
    await merchantProductsApi.delete(id);
    loadProducts();
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between bg-white p-4 rounded shadow-sm border border-gray-100">
        <div>
          <h2 className="font-bold text-base text-gray-800">Catalog & Inventory Listings</h2>
          <p className="text-xs text-gray-500">Manage your active product catalog, pricing, and inventory levels</p>
        </div>
        <button
          onClick={openCreateModal}
          className="bg-seller-blue hover:bg-blue-700 text-white font-bold text-xs px-4 py-2.5 rounded flex items-center gap-1.5 shadow transition"
        >
          <Plus className="w-4 h-4" /> Add New Listing
        </button>
      </div>

      {actionError && (
        <div
          role="alert"
          className="bg-red-50 border border-red-200 text-red-800 rounded p-3.5 text-xs flex items-center justify-between gap-3"
        >
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-red-600 flex-shrink-0" />
            <span>{actionError}</span>
          </div>
          <button
            type="button"
            onClick={() => setActionError('')}
            className="text-red-700 hover:text-red-900 font-bold"
          >
            Dismiss
          </button>
        </div>
      )}

      {actionSuccess && (
        <div
          role="status"
          className="bg-emerald-50 border border-emerald-200 text-emerald-800 rounded p-3.5 text-xs flex items-center justify-between gap-3"
        >
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
            <span>{actionSuccess}</span>
          </div>
          <button
            type="button"
            onClick={() => setActionSuccess('')}
            className="text-emerald-700 hover:text-emerald-900 font-bold"
          >
            Dismiss
          </button>
        </div>
      )}

      {!loading && unclaimedStarterProducts.length > 0 && (
        <div className="bg-white rounded shadow-sm border border-blue-200 p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-full bg-blue-50 text-seller-blue flex-shrink-0">
              <Store className="w-5 h-5" />
            </div>
            <div className="space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-sm font-bold text-gray-900">
                  Unclaimed Starter Catalog Items Detected ({unclaimedStarterProducts.length})
                </h3>
                <span className="text-[11px] font-bold px-2 py-0.5 rounded bg-amber-100 text-amber-800 border border-amber-200">
                  Starter Catalog
                </span>
              </div>
              <p className="text-xs text-gray-600 leading-relaxed">
                Unclaimed starter catalog items do not route through your Direct PayPal keys until
                claimed to your store. Claim them individually below or move all starter items into
                your store with one click.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleClaimAllStarter}
            disabled={claimingAll || claimingId !== null}
            className="bg-seller-blue hover:bg-blue-700 disabled:opacity-60 text-white font-bold text-xs px-4 py-2.5 rounded shadow inline-flex items-center justify-center gap-2 transition flex-shrink-0"
          >
            {claimingAll ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Store className="w-4 h-4" />
            )}
            <span>
              {claimingAll ? 'Claiming Starter Items...' : 'Claim All Starter Items to My Store'}
            </span>
          </button>
        </div>
      )}

      {/* Product Table */}
      <div className="bg-white rounded shadow-sm border border-gray-100 overflow-x-auto">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="bg-gray-50 border-b text-gray-500 uppercase">
              <th className="p-3.5">Product</th>
              <th className="p-3.5">Category</th>
              <th className="p-3.5">Ownership / PayPal</th>
              <th className="p-3.5">Selling Price (₹)</th>
              <th className="p-3.5">PayPal Sandbox (USD)</th>
              <th className="p-3.5">MRP</th>
              <th className="p-3.5">Stock</th>
              <th className="p-3.5">Status</th>
              <th className="p-3.5 text-right">Actions</th>
            </tr>
          </thead>
          <tbody ref={tbodyRef} className="divide-y divide-gray-100">
            {loading ? (
              <tr>
                <td colSpan={9} className="p-8 text-center text-gray-400">
                  Loading catalog...
                </td>
              </tr>
            ) : products.length === 0 ? (
              <tr>
                <td colSpan={9} className="p-8 text-center text-gray-400">
                  No products in catalog. Add your first listing to begin.
                </td>
              </tr>
            ) : (
              products.map((p) => {
                const isOwned = p.merchant_id != null;
                const isClaimingThis = claimingId === p.id;
                return (
                  <tr
                    key={p.id}
                    data-staggered-item
                    className="hover:bg-gray-50/60 transition-colors duration-200"
                  >
                    <td className="p-3.5">
                      <div className="flex items-center gap-3">
                        <img
                          src={resolveMediaUrl(p.image_url)}
                          alt={p.title}
                          className="w-10 h-10 object-contain border rounded p-0.5 bg-white"
                        />
                        <div>
                          <p className="font-bold text-gray-800 line-clamp-1 max-w-xs">{p.title}</p>
                          <p className="text-[11px] text-gray-400">{p.brand}</p>
                        </div>
                      </div>
                    </td>
                    <td className="p-3.5 text-gray-600">{p.category}</td>
                    <td className="p-3.5 whitespace-nowrap">
                      {isOwned ? (
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded font-bold text-[11px] bg-blue-50 text-seller-blue border border-blue-200">
                            <Store className="w-3 h-3" />
                            <span>Your Store</span>
                          </span>
                          {p.paypal_ready && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded font-bold text-[11px] bg-emerald-100 text-emerald-800 border border-emerald-200">
                              <ShieldCheck className="w-3 h-3" />
                              <span>PayPal Direct</span>
                            </span>
                          )}
                        </div>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded font-bold text-[11px] bg-amber-100 text-amber-800 border border-amber-200">
                          Starter Catalog (Unclaimed)
                        </span>
                      )}
                    </td>
                    <td className="p-3.5 font-bold text-gray-900">₹{p.price.toLocaleString('en-IN')}</td>
                    <td className="p-3.5">
                      <span className="inline-flex items-center px-2 py-0.5 rounded bg-blue-50 text-seller-blue border border-blue-100 font-bold text-[11px]">
                        ${Number(p.sandbox_usd_price || 0).toFixed(2)} USD
                      </span>
                    </td>
                    <td className="p-3.5 text-gray-400 line-through">₹{p.mrp.toLocaleString('en-IN')}</td>
                    <td className="p-3.5 font-semibold">{p.stock} units</td>
                    <td className="p-3.5">
                      <span
                        className={`px-2 py-0.5 rounded font-bold text-[10px] uppercase ${
                          p.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
                        }`}
                      >
                        {p.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td className="p-3.5 text-right whitespace-nowrap">
                      <div className="inline-flex items-center gap-1.5">
                        {!isOwned && (
                          <button
                            type="button"
                            onClick={() => handleClaimProduct(p)}
                            disabled={claimingAll || isClaimingThis}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-seller-blue/10 hover:bg-seller-blue text-seller-blue hover:text-white font-bold text-[11px] transition disabled:opacity-60"
                            title="Claim starter product to your store"
                          >
                            {isClaimingThis ? (
                              <Loader2 className="w-3 h-3 animate-spin" />
                            ) : (
                              <Store className="w-3 h-3" />
                            )}
                            <span>{isClaimingThis ? 'Claiming...' : 'Claim to Store'}</span>
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => openEditModal(p)}
                          className="text-seller-blue hover:text-blue-800 p-1"
                          title="Edit Listing & USD Price"
                        >
                          <Pencil className="w-4 h-4" />
                        </button>
                        {p.is_active && (
                          <button
                            type="button"
                            onClick={() => handleDelete(p.id)}
                            className="text-red-500 hover:text-red-700 p-1"
                            title="Deactivate Listing"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Add / Edit Product Modal */}
      {isAddOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 apple-scrim-enter">
          <div className="bg-white rounded shadow-xl max-w-lg w-full overflow-hidden apple-panel-enter">
            <div className="bg-seller-navy text-white p-4 flex justify-between items-center">
              <h3 className="font-bold text-sm">
                {editingProduct ? 'Edit Shipkart Product Listing' : 'Create New Shipkart Product Listing'}
              </h3>
              <button type="button" onClick={closeModal}>
                <X className="w-5 h-5" />
              </button>
            </div>
            <form onSubmit={handleSubmit} className="p-5 space-y-3 text-xs">
              <div>
                <label className="font-bold text-gray-600 uppercase">Product Title</label>
                <input
                  required
                  type="text"
                  value={form.title}
                  onChange={(e) => setForm({ ...form, title: e.target.value })}
                  placeholder="e.g. Sony Bravia 55 inch 4K Google TV"
                  className="w-full mt-1 border p-2 rounded"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-bold text-gray-600 uppercase">Brand</label>
                  <input
                    required
                    type="text"
                    value={form.brand}
                    onChange={(e) => setForm({ ...form, brand: e.target.value })}
                    placeholder="e.g. Sony"
                    className="w-full mt-1 border p-2 rounded"
                  />
                </div>
                <div>
                  <label className="font-bold text-gray-600 uppercase">Category</label>
                  <select
                    value={form.category}
                    onChange={(e) => setForm({ ...form, category: e.target.value })}
                    className="w-full mt-1 border p-2 rounded bg-white"
                  >
                    <option value="Mobiles">Mobiles</option>
                    <option value="Electronics">Electronics</option>
                    <option value="Fashion">Fashion</option>
                    <option value="Appliances">Appliances</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div>
                  <label className="font-bold text-gray-600 uppercase">Selling Price (₹)</label>
                  <input
                    required
                    type="number"
                    min="1"
                    step="0.01"
                    value={form.price}
                    onChange={(e) => setForm({ ...form, price: e.target.value })}
                    className="w-full mt-1 border p-2 rounded"
                  />
                </div>
                <div>
                  <label className="font-bold text-gray-600 uppercase">MRP (₹)</label>
                  <input
                    required
                    type="number"
                    min="1"
                    step="0.01"
                    value={form.mrp}
                    onChange={(e) => setForm({ ...form, mrp: e.target.value })}
                    className="w-full mt-1 border p-2 rounded"
                  />
                </div>
                <div>
                  <label className="font-bold text-gray-600 uppercase">Sandbox USD ($)</label>
                  <input
                    type="number"
                    min="0.01"
                    step="0.01"
                    placeholder="Auto"
                    value={form.sandbox_usd_price}
                    onChange={(e) => setForm({ ...form, sandbox_usd_price: e.target.value })}
                    className="w-full mt-1 border p-2 rounded"
                  />
                </div>
                <div>
                  <label className="font-bold text-gray-600 uppercase">Stock Qty</label>
                  <input
                    required
                    type="number"
                    min="0"
                    value={form.stock}
                    onChange={(e) => setForm({ ...form, stock: e.target.value })}
                    className="w-full mt-1 border p-2 rounded"
                  />
                </div>
              </div>
              <p className="text-[11px] text-gray-400 -mt-1">
                Leave Sandbox USD ($) blank on creation to automatically assign explicit USD test pricing.
              </p>

              <div>
                <label className="font-bold text-gray-600 uppercase">Description</label>
                <textarea
                  required
                  rows={2}
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  className="w-full mt-1 border p-2 rounded"
                />
              </div>

              {/* Product Image Upload */}
              <div>
                <label className="font-bold text-gray-600 uppercase block mb-1">
                  Product Image
                </label>
                <div className="flex items-center gap-3">
                  <label className="flex-1 border-2 border-dashed border-gray-300 hover:border-seller-blue rounded p-3 flex items-center justify-center gap-2 cursor-pointer">
                    <UploadCloud className="w-5 h-5 text-seller-blue" />
                    <span>{uploading ? 'Uploading image...' : 'Select Image File'}</span>
                    <input type="file" accept="image/*" onChange={handleImageUpload} className="hidden" />
                  </label>
                  {form.image_url && (
                    <div className="w-12 h-12 border rounded overflow-hidden relative">
                      <img src={resolveMediaUrl(form.image_url)} alt="Preview" className="w-full h-full object-contain" />
                      <CheckCircle
                        key={form.image_url}
                        className="apple-badge-pop w-3.5 h-3.5 text-green-600 absolute top-0 right-0 bg-white rounded-full"
                      />
                    </div>
                  )}
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t">
                <button type="button" onClick={closeModal} className="px-4 py-2 text-gray-600">
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={uploading || saving}
                  className="bg-seller-blue text-white font-bold px-6 py-2 rounded shadow disabled:opacity-60"
                >
                  {saving ? 'Saving...' : editingProduct ? 'Save Changes' : 'Publish Product'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
