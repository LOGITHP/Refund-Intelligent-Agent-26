import React, { useState } from 'react';
import { X, UploadCloud, CheckCircle, AlertCircle } from 'lucide-react';
import { mediaApi, resolveMediaUrl, returnsApi } from '../services/api';

const RETURN_REASONS = [
  'Item is defective or not working',
  'Item arrived physically damaged',
  'Wrong / different item received',
  'Quality not as expected',
  'Missing accessories or parts',
];

export default function ReturnModal({ isOpen, onClose, order, orderItem, onSuccess }) {
  const [reason, setReason] = useState(RETURN_REASONS[0]);
  const [comments, setComments] = useState('');
  const [evidenceUrls, setEvidenceUrls] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  if (!isOpen || !order || !orderItem) return null;

  const handleFileChange = async (e) => {
    const files = Array.from(e.target.files);
    if (!files.length) return;
    setUploading(true);
    setError('');
    try {
      for (const file of files) {
        const res = await mediaApi.uploadEvidence(file);
        setEvidenceUrls((prev) => [...prev, res.url]);
      }
    } catch (err) {
      setError(err.message || 'Failed uploading evidence image');
    } finally {
      setUploading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError('');
    try {
      const createdReturn = await returnsApi.create({
        order_id: order.id,
        order_item_id: orderItem.id,
        reason,
        comments,
        evidence_urls: evidenceUrls,
      });
      onSuccess(createdReturn);
      onClose();
    } catch (err) {
      setError(err.message || 'Return request submission failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="apple-scrim-enter fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="apple-panel-enter bg-white rounded-sm shadow-2xl max-w-lg w-full overflow-hidden relative">
        <div className="bg-fk-blue text-white p-4 flex items-center justify-between">
          <div>
            <h3 className="font-bold text-base">Request Return & Refund</h3>
            <p className="text-xs text-blue-100">Order {order.order_number}</p>
          </div>
          <button onClick={onClose} className="text-white/80 hover:text-white p-1">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          {/* Item Preview */}
          <div className="flex gap-3 p-3 bg-gray-50 border rounded items-center">
            <img
              src={resolveMediaUrl(orderItem.image_url)}
              alt={orderItem.title}
              className="w-14 h-14 object-contain bg-white border rounded p-1"
            />
            <div className="flex-1">
              <p className="text-sm font-medium text-fk-dark line-clamp-1">{orderItem.title}</p>
              <p className="text-xs text-gray-500">
                Refund Amount: <strong className="text-fk-green">₹{(orderItem.price * orderItem.quantity).toLocaleString('en-IN')}</strong>
              </p>
            </div>
          </div>

          {error && (
            <div className="p-2.5 bg-red-50 border border-red-200 text-red-600 text-xs rounded flex items-center gap-2">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Reason Selection */}
          <div>
            <label className="text-xs font-bold text-gray-700 uppercase">Reason for Return</label>
            <select
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="w-full mt-1.5 border border-gray-300 rounded px-3 py-2 text-sm focus:border-fk-blue focus:outline-none bg-white"
            >
              {RETURN_REASONS.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </div>

          {/* Comments */}
          <div>
            <label className="text-xs font-bold text-gray-700 uppercase">Additional Details / Description</label>
            <textarea
              required
              rows={3}
              value={comments}
              onChange={(e) => setComments(e.target.value)}
              placeholder="Describe the defect, missing accessory, or issue in detail..."
              className="w-full mt-1.5 border border-gray-300 rounded p-2.5 text-sm focus:border-fk-blue focus:outline-none"
            />
          </div>

          {/* Evidence Image Upload */}
          <div>
            <label className="text-xs font-bold text-gray-700 uppercase block mb-1.5">
              Upload Defect / Condition Photos
            </label>
            <label className="border-2 border-dashed border-gray-300 hover:border-fk-blue rounded p-4 flex flex-col items-center justify-center cursor-pointer transition bg-gray-50/50">
              <UploadCloud className="w-7 h-7 text-fk-blue mb-1" />
              <span className="text-xs font-semibold text-gray-700">
                {uploading ? 'Uploading photo...' : 'Click to upload photos (JPG, PNG)'}
              </span>
              <span className="text-[11px] text-gray-400">Clear photos help verify and speed up your return approval</span>
              <input
                type="file"
                multiple
                accept="image/*"
                onChange={handleFileChange}
                className="hidden"
                disabled={uploading}
              />
            </label>

            {evidenceUrls.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-3">
                {evidenceUrls.map((url, idx) => (
                  <div key={idx} className="relative w-16 h-16 border rounded overflow-hidden">
                    <img src={resolveMediaUrl(url)} alt="Evidence" className="w-full h-full object-cover" />
                    <CheckCircle className="w-3.5 h-3.5 text-fk-green absolute top-0.5 right-0.5 bg-white rounded-full" />
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="flex justify-end gap-3 pt-2 border-t">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-xs font-bold text-gray-600 hover:bg-gray-100 rounded-sm"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting || uploading}
              className="bg-fk-orange hover:bg-orange-600 text-white font-bold px-6 py-2 rounded-sm text-xs shadow uppercase tracking-wide"
            >
              {submitting ? 'Submitting...' : 'Submit Return Request'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

