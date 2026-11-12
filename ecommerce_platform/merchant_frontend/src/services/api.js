const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const AGENT_API_BASE = import.meta.env.VITE_AGENT_API_URL || 'http://localhost:8100';

export function resolveMediaUrl(path) {
  if (!path) return '';
  if (path.startsWith('http://') || path.startsWith('https://')) return path;
  return `${API_BASE}${path}`;
}

export async function apiRequest(endpoint, options = {}) {
  const token = localStorage.getItem('fk_merchant_token');
  const headers = {
    ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  };

  const response = await fetch(`${API_BASE}/api/v1${endpoint}`, {
    ...options,
    headers,
  });

  if (response.status === 204) return null;

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const errMsg = Array.isArray(data.detail)
      ? data.detail.map((d) => d.msg || JSON.stringify(d)).join(', ')
      : data.detail || 'API request failed';
    throw new Error(errMsg);
  }
  return data;
}

export const sellerAuthApi = {
  login: (email, password) =>
    apiRequest('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  register: (payload) =>
    apiRequest('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ ...payload, role: 'merchant' }),
    }),
  me: () => apiRequest('/auth/me'),
};

export const merchantProductsApi = {
  myProducts: () => apiRequest('/products/merchant/my'),
  create: (payload) =>
    apiRequest('/products/', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  update: (id, payload) =>
    apiRequest(`/products/${id}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  delete: (id) =>
    apiRequest(`/products/${id}`, {
      method: 'DELETE',
    }),
  claim: (id) =>
    apiRequest('/products/' + id + '/claim', {
      method: 'POST',
    }),
  claimStarter: () =>
    apiRequest('/products/claim-starter', {
      method: 'POST',
    }),
  uploadImage: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return apiRequest('/media/upload?bucket=product-images', {
      method: 'POST',
      body: formData,
    });
  },
};

export const merchantOrdersApi = {
  myOrders: () => apiRequest('/orders/merchant'),
  updateStatus: (orderId, newStatus) =>
    apiRequest(`/orders/${orderId}/status?new_status=${newStatus}`, {
      method: 'PATCH',
    }),
};

export const merchantReturnsApi = {
  myReturns: () => apiRequest('/returns/merchant'),
  syncAgent: (returnId) =>
    apiRequest(`/returns/${returnId}/sync-agent`, {
      method: 'POST',
    }),
  decide: (returnId, payload) =>
    apiRequest(`/returns/${returnId}/decision`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  executeApprovedRefund: (returnId, payload) =>
    apiRequest(`/returns/${returnId}/execute-approved-refund`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
};

export const merchantPaymentsApi = {
  getSettings: () => apiRequest('/merchant/payment-settings'),
  updateSettings: (payload) =>
    apiRequest('/merchant/payment-settings', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  verifyPayPal: (payload = {}) =>
    apiRequest('/merchant/payment-settings/verify-paypal', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  clearPayPalCredentials: () =>
    apiRequest('/merchant/payment-settings/credentials', {
      method: 'DELETE',
    }),
  getAllocations: () => apiRequest('/merchant/allocations'),
};

export async function agentMerchantApiRequest(endpoint, options = {}) {
  const token = localStorage.getItem('fk_merchant_token');
  const headers = {
    ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  };

  let response;
  try {
    response = await fetch(`${AGENT_API_BASE}/api/v1${endpoint}`, {
      ...options,
      headers,
    });
  } catch {
    const err = new Error('Refund Intelligence service is unreachable');
    err.isOffline = true;
    throw err;
  }

  if (response.status === 204) return null;

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const errMsg = Array.isArray(data.detail)
      ? data.detail.map((d) => d.msg || JSON.stringify(d)).join(', ')
      : data.detail || `Agent API request failed (${response.status})`;
    const err = new Error(errMsg);
    err.status = response.status;
    throw err;
  }
  return data;
}

export const agentMerchantApi = {
  findRefundByReturnId: (shipkartReturnId) =>
    agentMerchantApiRequest(`/merchant/refunds?shipkart_return_id=${encodeURIComponent(shipkartReturnId)}`),
  getInvestigation: (refundId) => agentMerchantApiRequest(`/merchant/refunds/${refundId}/investigation`),
  runInvestigation: (refundId, customerQuery = null) =>
    agentMerchantApiRequest(`/agents/investigate/${refundId}`, {
      method: 'POST',
      body: JSON.stringify(customerQuery ? { customer_query: customerQuery } : {}),
    }),
  inspectReturn: (returnId, payload) =>
    agentMerchantApiRequest(`/merchant/returns/${returnId}/inspect`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  transitionReturnStatus: (returnId, status, reason = null) =>
    agentMerchantApiRequest(`/merchant/returns/${returnId}/transition`, {
      method: 'POST',
      body: JSON.stringify({ status, reason }),
    }),
  approveRefund: (refundId, payload) =>
    agentMerchantApiRequest(`/merchant/refunds/${refundId}/approve`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  rejectRefund: (refundId, payload) =>
    agentMerchantApiRequest(`/merchant/refunds/${refundId}/reject`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
};

