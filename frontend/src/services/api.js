import axios from 'axios';

const client = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL || '/api' });

/**
 * POST /api/scan. `overrides` may hold legend_page, demo_pages, new_work_pages,
 * highlight_mapping (object) and colour_meanings (object).
 */
export async function scanPid({ pidFile, scopeFile, reviewNotes, overrides = {} }) {
  const form = new FormData();
  form.append('file', pidFile);
  if (scopeFile) form.append('scope_document', scopeFile);
  if (reviewNotes) form.append('review_notes', reviewNotes);
  Object.entries(overrides).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return;
    if (Array.isArray(value) && value.length === 0) return;
    if (typeof value === 'object' && !Array.isArray(value) && Object.keys(value).length === 0) return;
    form.append(key, typeof value === 'object' ? JSON.stringify(value) : String(value));
  });
  const { data } = await client.post('/scan', form);
  return data;
}

export function errorMessage(err) {
  return err?.response?.data?.detail || err?.message || 'Scan failed';
}

export const bomPdfUrl = (path) => (path ? `${client.defaults.baseURL}/bom-pdf?path=${encodeURIComponent(path)}` : null);
