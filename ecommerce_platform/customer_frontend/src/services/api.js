const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const AGENT_API_BASE = import.meta.env.VITE_AGENT_API_URL || 'http://localhost:8100';

export function resolveMediaUrl(path) {
  if (!path) return '';
  if (path.startsWith('http://') || path.startsWith('https://')) return path;
  return `${API_BASE}${path}`;
}

export async function apiRequest(endpoint, options = {}) {
  const token = localStorage.getItem('fk_customer_token');
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

export const authApi = {
  login: (email, password) =>
    apiRequest('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  register: (payload) =>
    apiRequest('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ ...payload, role: 'customer' }),
    }),
  me: () => apiRequest('/auth/me'),
  getAddresses: () => apiRequest('/auth/addresses'),
  addAddress: (payload) =>
    apiRequest('/auth/addresses', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
};

export const productsApi = {
  list: (params = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') query.append(k, v);
    });
    const qs = query.toString();
    return apiRequest(`/products/${qs ? `?${qs}` : ''}`);
  },
  get: (id) => apiRequest(`/products/${id}`),
};

export const cartApi = {
  get: () => apiRequest('/cart/'),
  add: (product_id, quantity = 1) =>
    apiRequest('/cart/items', {
      method: 'POST',
      body: JSON.stringify({ product_id, quantity }),
    }),
  update: (item_id, quantity) =>
    apiRequest(`/cart/items/${item_id}`, {
      method: 'PUT',
      body: JSON.stringify({ quantity }),
    }),
  remove: (item_id) =>
    apiRequest(`/cart/items/${item_id}`, {
      method: 'DELETE',
    }),
};

export const ordersApi = {
  create: (payload) =>
    apiRequest('/orders/', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  myOrders: () => apiRequest('/orders/my'),
  get: (id) => apiRequest(`/orders/${id}`),
  invoiceUrl: (id) => `${API_BASE}/api/v1/invoices/${id}`,
};

export const returnsApi = {
  create: (payload) =>
    apiRequest('/returns/', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  myReturns: () => apiRequest('/returns/my'),
  get: (id) => apiRequest(`/returns/${id}`),
};

export const mediaApi = {
  uploadEvidence: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return apiRequest('/media/upload?bucket=return-evidence', {
      method: 'POST',
      body: formData,
    });
  },
};

export const paymentsApi = {
  clientConfig: ({ buy_now_product_id, buy_now_quantity } = {}) => {
    const query = new URLSearchParams();
    if (buy_now_product_id !== undefined && buy_now_product_id !== null && buy_now_product_id !== '') {
      query.append('buy_now_product_id', String(buy_now_product_id));
      const qty = Math.max(1, Number(buy_now_quantity) || 1);
      query.append('buy_now_quantity', String(qty));
    }
    const qs = query.toString();
    return apiRequest(`/payments/paypal/client-config${qs ? `?${qs}` : ''}`);
  },
  createPayPalOrder: (payload) =>
    apiRequest('/payments/paypal/create-order', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  capturePayPalOrder: ({ local_order_id, paypal_order_id }) =>
    apiRequest('/payments/paypal/capture-order', {
      method: 'POST',
      body: JSON.stringify({ local_order_id, paypal_order_id }),
    }),
  cancelPayPalOrder: (local_order_id) => {
    const orderId =
      typeof local_order_id === 'object' && local_order_id !== null
        ? local_order_id.local_order_id
        : local_order_id;
    return apiRequest('/payments/paypal/cancel-order', {
      method: 'POST',
      body: JSON.stringify({ local_order_id: orderId }),
    });
  },
};

export async function agentApiRequest(endpoint, options = {}) {
  const token = localStorage.getItem('fk_customer_token');
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

export const agentCustomerApi = {
  findRefundByReturnId: (shipkartReturnId) =>
    agentApiRequest(`/refunds?shipkart_return_id=${encodeURIComponent(shipkartReturnId)}`),
  getIntelligence: (refundId) => agentApiRequest(`/refunds/${refundId}/intelligence`),
  getTimeline: (refundId) => agentApiRequest(`/refunds/${refundId}/timeline`),
  getEta: (refundId) => agentApiRequest(`/refunds/${refundId}/eta`),
  runInvestigation: (refundId, customerQuery = null) =>
    agentApiRequest(`/agents/investigate/${refundId}`, {
      method: 'POST',
      body: JSON.stringify(customerQuery ? { customer_query: customerQuery } : {}),
    }),
  askChat: (refundId, question) =>
    agentApiRequest(`/refunds/${refundId}/chat`, {
      method: 'POST',
      body: JSON.stringify({ question }),
    }),
  submitAppeal: (refundId, reason, evidenceIds = []) =>
    agentApiRequest(`/refunds/${refundId}/appeals`, {
      method: 'POST',
      body: JSON.stringify({ reason, evidence_ids: evidenceIds }),
    }),
  uploadVerifiedEvidence: async (returnCaseUuid, file, refundCaseUuid = null) => {
    const formData = new FormData();
    formData.append('file', file);
    if (refundCaseUuid) {
      formData.append('refund_case_id', refundCaseUuid);
    }
    return agentApiRequest(`/returns/${returnCaseUuid}/evidence`, {
      method: 'POST',
      body: formData,
    });
  },
};

