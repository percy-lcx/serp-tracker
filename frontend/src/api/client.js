const API_BASE = import.meta.env.VITE_API_URL || '';

async function request(method, path, body = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(`${API_BASE}${path}`, opts);
  if (res.status === 204) return null;
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Request failed');
  }
  return res.json();
}

export const api = {
  // Jobs
  getJobs: () => request('GET', '/api/jobs'),
  createJob: (data) => request('POST', '/api/jobs', data),
  updateJob: (id, data) => request('PUT', `/api/jobs/${id}`, data),
  deleteJob: (id) => request('DELETE', `/api/jobs/${id}`),
  importJobs: async (file) => {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(`${API_BASE}/api/jobs/import`, { method: 'POST', body: form });
    if (!res.ok) throw new Error('Import failed');
    return res.json();
  },
  getJobResults: (id, limit = 50, offset = 0) =>
    request('GET', `/api/jobs/${id}/results?limit=${limit}&offset=${offset}`),

  // Runs
  getRuns: (limit = 20, offset = 0) => request('GET', `/api/runs?limit=${limit}&offset=${offset}`),
  getRun: (id) => request('GET', `/api/runs/${id}`),
  triggerRun: (data) => request('POST', '/api/runs', data),
  abortRun: (id) => request('POST', `/api/runs/${id}/abort`),

  // Results
  getResult: (id) => request('GET', `/api/results/${id}`),
  getScreenshotUrl: (resultId, type) => `${API_BASE}/api/results/${resultId}/screenshots/${type}`,

  // Stats
  getStats: () => request('GET', '/api/stats'),

  // Site profiles
  getProfiles: () => request('GET', '/api/profiles'),
  updateProfile: (domain, data) => request('PUT', `/api/profiles/${encodeURIComponent(domain)}`, data),
};
