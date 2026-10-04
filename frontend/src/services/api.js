import axios from 'axios';

const client = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL || '/api' });

/** Adapt the backend /api/scan response to the shape the UI components consume. */
export function normaliseResult(data) {
  if (!data) return data;
  if (data.status === 'needs_clarification') {
    return {
      ...data,
      questions: (data.questions || []).map((q, i) => ({
        ...q,
        id: q.id || `${q.type}-${i}`,
        candidate_pairs: (q.candidate_pairs || []).map((p) => ({ pages: p.pages, similarity: p.similarity })),
      })),
    };
  }
  const flags = (data.flags || []).map((f, i) => ({ ...f, id: f.id || `${f.type}-${f.tag || f.item || i}` }));
  const colours = data.colour_scheme || {};
  return {
    ...data,
    flags,
    total_items: (data.materials || []).length,
    total_flags: flags.length,
    legend_detected: data.legend?.found
      ? { page: data.legend.page, entries_found: data.legend.entries_found, method: 'keyword scoring', confidence: null, entry_sample: [] }
      : null,
    page_classification: {
      demo_pages: data.demo_pages || [],
      new_work_pages: data.new_work_pages || [],
      method: data.classification_method,
      confidence: data.classification_confidence,
    },
    colour_scheme: { colours_detected: Object.fromEntries(Object.entries(colours).map(([k, v]) => [k, { ...v, source: 'detected' }])) },
  };
}

/**
 * POST /api/scan (multipart). Backend fields: file, scope_of_work, review_notes,
 * legend_page, key_page, demo_pages, new_work_pages (comma separated), highlight_mapping (JSON object).
 */
export async function scanPid({ pidFile, scopeText, reviewNotes, overrides = {} }) {
  const form = new FormData();
  form.append('file', pidFile);
  if (scopeText) form.append('scope_of_work', scopeText);
  if (reviewNotes) form.append('review_notes', reviewNotes);
  const { legend_page, key_page, demo_pages, new_work_pages, highlight_mapping } = overrides;
  if (legend_page) form.append('legend_page', String(legend_page));
  if (key_page) form.append('key_page', String(key_page));
  if (demo_pages?.length) form.append('demo_pages', demo_pages.join(','));
  if (new_work_pages?.length) form.append('new_work_pages', new_work_pages.join(','));
  if (highlight_mapping && Object.keys(highlight_mapping).length) form.append('highlight_mapping', JSON.stringify(highlight_mapping));
  const { data } = await client.post('/scan', form);
  return normaliseResult(data);
}

export function errorMessage(err) {
  return err?.response?.data?.detail || err?.message || 'Scan failed';
}

// The backend does not yet expose a BOM download route, so downloads are disabled until it does.
export const bomPdfUrl = () => null;
