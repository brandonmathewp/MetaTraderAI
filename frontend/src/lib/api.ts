const API_BASE = import.meta.env.VITE_API_URL || '';

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('access_token');
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...((options.headers as Record<string, string>) || {}),
  };

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (res.status === 401) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      const newToken = localStorage.getItem('access_token');
      headers.Authorization = `Bearer ${newToken}`;
      const retryRes = await fetch(`${API_BASE}${path}`, { ...options, headers });
      if (!retryRes.ok) throw new ApiError(retryRes.status, await retryRes.text());
      return retryRes.json();
    }
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    window.location.href = '/login';
    throw new ApiError(401, 'Session expired');
  }

  if (!res.ok) {
    const text = await res.text();
    throw new ApiError(res.status, text);
  }

  return res.status !== 204 ? res.json() : (undefined as T);
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

async function refreshAccessToken(): Promise<boolean> {
  const refreshToken = localStorage.getItem('refresh_token');
  if (!refreshToken) return false;
  try {
    const res = await fetch(`${API_BASE}/api/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!res.ok) return false;
    const data = await res.json();
    localStorage.setItem('access_token', data.access_token);
    localStorage.setItem('refresh_token', data.refresh_token);
    return true;
  } catch {
    return false;
  }
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PUT', body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
};

export const authApi = {
  register: (email: string, password: string) =>
    api.post<{ access_token: string; refresh_token: string }>('/api/auth/register', { email, password }),
  login: (email: string, password: string) =>
    api.post<{ access_token: string; refresh_token: string }>('/api/auth/login', { email, password }),
  me: () => api.get<{ id: number; email: string; is_active: boolean }>('/api/auth/me'),
};

export const marketApi = {
  getSymbols: () => api.get<{ symbols: { symbol: string; base_asset: string; quote_asset: string }[] }>('/api/market/symbols'),
  getPrice: (symbol: string) => api.get<{ symbol: string; price: number }>(`/api/market/price?symbol=${symbol}`),
  getKlines: (symbol: string, interval = '1m', limit = 200) =>
    api.get(`/api/market/klines?symbol=${symbol}&interval=${interval}&limit=${limit}`),
  getIndicators: (symbol: string, interval = '1m') =>
    api.get(`/api/market/indicators?symbol=${symbol}&interval=${interval}`),
  getTicker24h: (symbol?: string) =>
    api.get(symbol ? `/api/market/ticker24hr?symbol=${symbol}` : '/api/market/ticker24hr'),
  getOrderBook: (symbol: string, limit = 20) =>
    api.get(`/api/market/orderbook?symbol=${symbol}&limit=${limit}`),
};

export const tradingApi = {
  getPortfolios: () => api.get('/api/trading/portfolio'),
  createPortfolio: (name: string, balance: number) =>
    api.post('/api/trading/portfolio', { name, initial_balance: balance }),
  deletePortfolio: (id: number) => api.delete(`/api/trading/portfolio/${id}`),
  getSummary: (portfolioId: number) => api.get(`/api/trading/portfolio/${portfolioId}/summary`),
  getPositions: (portfolioId: number) => api.get(`/api/trading/portfolio/${portfolioId}/positions`),
  getTrades: (portfolioId: number, limit = 50) =>
    api.get(`/api/trading/portfolio/${portfolioId}/trades?limit=${limit}`),
  marketOrder: (data: { symbol: string; side: string; quantity: number; portfolio_id: number; strategy_id?: number; model_prediction?: string; confidence?: number }) =>
    api.post('/api/trading/market-order', data),
  limitOrder: (data: { symbol: string; side: string; quantity: number; limit_price: number; portfolio_id: number; strategy_id?: number }) =>
    api.post('/api/trading/limit-order', data),
  cancelOrder: (orderId: number) => api.post(`/api/trading/cancel-order/${orderId}`),
  getOpenOrders: (portfolioId?: number) =>
    api.get(`/api/trading/open-orders${portfolioId ? `?portfolio_id=${portfolioId}` : ''}`),
  getOrderHistory: (portfolioId?: number, limit = 50) =>
    api.get(`/api/trading/order-history${portfolioId ? `?portfolio_id=${portfolioId}&limit=${limit}` : `?limit=${limit}`}`),
  getRiskConfig: (portfolioId: number) => api.get(`/api/trading/risk-config/${portfolioId}`),
  updateRiskConfig: (portfolioId: number, data: Record<string, number>) =>
    api.put(`/api/trading/risk-config/${portfolioId}`, data),
};

export const strategiesApi = {
  list: () => api.get('/api/strategies'),
  create: (data: { name: string; description?: string; graph_json?: string }) =>
    api.post('/api/strategies', data),
  get: (id: number) => api.get(`/api/strategies/${id}`),
  update: (id: number, data: Record<string, unknown>) =>
    api.put(`/api/strategies/${id}`, data),
  delete: (id: number) => api.delete(`/api/strategies/${id}`),
  clone: (id: number) => api.post(`/api/strategies/${id}/clone`),
  getNodes: (strategyId: number) => api.get(`/api/strategies/${strategyId}/nodes`),
  createNode: (strategyId: number, data: { node_type: string; label: string; node_config_json?: string; position_x: number; position_y: number }) =>
    api.post(`/api/strategies/${strategyId}/nodes`, data),
  updateNode: (strategyId: number, nodeId: number, data: { node_type: string; label: string; node_config_json?: string; position_x: number; position_y: number }) =>
    api.put(`/api/strategies/${strategyId}/nodes/${nodeId}`, data),
  deleteNode: (strategyId: number, nodeId: number) =>
    api.delete(`/api/strategies/${strategyId}/nodes/${nodeId}`),
  getEdges: (strategyId: number) => api.get(`/api/strategies/${strategyId}/edges`),
  createEdge: (strategyId: number, data: { source_node_id: number; target_node_id: number; source_handle?: string; target_handle?: string }) =>
    api.post(`/api/strategies/${strategyId}/edges`, data),
  deleteEdge: (strategyId: number, edgeId: number) =>
    api.delete(`/api/strategies/${strategyId}/edges/${edgeId}`),
  execute: (strategyId: number, data?: { portfolio_id?: number }) =>
    api.post(`/api/strategies/${strategyId}/execute`, data || {}),
  start: (strategyId: number, data: { portfolio_id?: number | null; interval_seconds?: number }) => {
    const params = new URLSearchParams();
    if (data.interval_seconds) params.set('interval_seconds', data.interval_seconds.toString());
    return api.post(`/api/strategies/${strategyId}/start?${params.toString()}`, data);
  },
  stop: (strategyId: number) => api.post(`/api/strategies/${strategyId}/stop`),
  getStatus: (strategyId: number) => api.get(`/api/strategies/${strategyId}/status`),
  getRunning: () => api.get('/api/strategies/running'),
  getNodeTypes: () => api.get('/api/strategies/node-types'),
};

export const costsApi = {
  getLiveSummary: () => api.get('/api/costs/live-summary'),
  getToday: () => api.get('/api/costs/today'),
  getByStrategy: (days = 7) => api.get(`/api/costs/by-strategy?days=${days}`),
  getStrategyDetail: (strategyId: number, days = 7) => api.get(`/api/costs/by-strategy-detail/${strategyId}?days=${days}`),
  getPredictive: (days = 30) => api.get(`/api/costs/predictive?days_ahead=${days}`),
  getBudgets: () => api.get('/api/costs/budgets'),
  setBudget: (modelName: string, maxUsd: number) =>
    api.post('/api/costs/budgets', { model_name: modelName, max_usd_per_day: maxUsd }),
  deleteBudget: (budgetId: number) => api.delete(`/api/costs/budgets/${budgetId}`),
  checkBudget: (modelName: string) => api.get(`/api/costs/check?model_name=${encodeURIComponent(modelName)}`),
  getHistory: (days = 30) => api.get(`/api/costs/history?days=${days}`),
  getModelRates: () => api.get('/api/costs/models'),
  resetDaily: () => api.post('/api/costs/reset-daily'),
};

export const learningApi = {
  getMemoryStats: () => api.get('/api/learning/memory/stats'),
  searchMemory: (data: { symbol?: string; top_k?: number; only_successful?: boolean; query_text?: string }) =>
    api.post('/api/learning/memory/search', data),
  clearMemory: () => api.delete('/api/learning/memory'),
  getRagContext: (symbol?: string) =>
    api.get(`/api/learning/memory/context${symbol ? `?symbol=${symbol}` : ''}`),
  getStrategyPerformance: (strategyId: number, days = 7) =>
    api.get(`/api/learning/performance/strategy/${strategyId}?days=${days}`),
  getOverallPerformance: () => api.get('/api/learning/performance/overall'),
  getSnapshots: (strategyId: number, limit = 30) =>
    api.get(`/api/learning/performance/snapshots/${strategyId}?limit=${limit}`),
  runImprover: (strategyId: number, config?: { auto_apply?: boolean; aggressiveness?: string }) =>
    api.post(`/api/learning/improver/run/${strategyId}`, config || {}),
  getImproverHistory: (strategyId: number, limit = 20) =>
    api.get(`/api/learning/improver/history/${strategyId}?limit=${limit}`),
  revertMutation: (mutationId: number) =>
    api.post(`/api/learning/improver/revert/${mutationId}`),
};

export const scriptsApi = {
  list: () => api.get('/api/scripts'),
  create: (data: { name: string; python_code: string }) =>
    api.post('/api/scripts', data),
  get: (id: number) => api.get(`/api/scripts/${id}`),
  update: (id: number, data: { name?: string; python_code?: string }) =>
    api.put(`/api/scripts/${id}`, data),
  delete: (id: number) => api.delete(`/api/scripts/${id}`),
  execute: (data: { code: string; portfolio_id?: number; strategy_id?: number; input_data?: any }) =>
    api.post('/api/scripts/execute', data),
  validate: (code: string) => api.post('/api/scripts/validate', { code }),
  getTemplates: () => api.get('/api/scripts/templates'),
};