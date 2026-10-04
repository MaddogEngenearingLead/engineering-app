import React from 'react';
import Button from './common/Button.jsx';
import Card from './common/Card.jsx';
import BOMTable from './BOMTable.jsx';
import { bomPdfUrl } from '../services/api.js';

const FLAG_GROUPS = [
  ['Untagged items', (f) => /untagged/.test(f.type)],
  ['Scope mismatches', (f) => /scope/.test(f.type)],
  ['Out-of-scheme colours', (f) => /colour|color/.test(f.type)],
];

const pct = (n) => (typeof n === 'number' ? `${Math.round(n * 100)}%` : 'n/a');

export default function Results({ result, onEdit, onReview }) {
  const { legend_detected: legend, page_classification: pc, colour_scheme: cs, materials = [], flags = [] } = result;
  const pdf = bomPdfUrl(result.bom_pdf);
  return (
    <div className="space-y-4">
      <Card title={`Scan results — ${result.job_number || result.job_id || ''}`}>
        <p className="text-sm text-slate-600">{result.total_items ?? materials.length} items · {result.total_flags ?? flags.length} flags</p>
      </Card>

      <Card title="Legend">
        {legend ? (
          <div className="text-sm">
            <p>Page {legend.page} · {legend.entries_found} entries · {legend.method} ({pct(legend.confidence)})</p>
            <ul className="mt-2 list-inside list-disc">{(legend.entry_sample || []).map((e) => <li key={e}>{e}</li>)}</ul>
          </div>
        ) : <p className="text-sm text-slate-500">No legend detected.</p>}
      </Card>

      <Card title="Page classification">
        {pc ? (
          <div className="text-sm">
            <p>Demo pages: {(pc.demo_pages || []).join(', ') || 'none'}</p>
            <p>New-work pages: {(pc.new_work_pages || []).join(', ') || 'none'}</p>
            <p>Method: {pc.method} ({pct(pc.confidence)})</p>
            {pc.details && <p className="text-slate-600">{pc.details}</p>}
          </div>
        ) : <p className="text-sm text-slate-500">Not available.</p>}
      </Card>

      <Card title="Colour scheme">
        <ul className="space-y-1 text-sm">
          {Object.entries(cs?.colours_detected || {}).map(([rgb, c]) => (
            <li key={rgb}>
              <code>{rgb}</code> → {c.meaning || 'unknown'} ({pct(c.confidence)}, {c.source})
            </li>
          ))}
        </ul>
      </Card>

      <Card title="BOM preview (first 10)">
        <BOMTable items={materials} limit={10} />
      </Card>

      <Card title="Flags">
        <ul className="text-sm">
          {FLAG_GROUPS.map(([label, test]) => <li key={label}>{label}: {flags.filter(test).length}</li>)}
          <li>Total: {flags.length}</li>
        </ul>
      </Card>

      <div className="flex flex-wrap gap-3">
        {pdf ? <a href={pdf} download><Button>Download BOM PDF</Button></a> : <Button disabled>Download BOM PDF</Button>}
        <Button variant="secondary" onClick={onEdit}>Edit and Resubmit</Button>
        <Button variant="secondary" onClick={onReview}>Review BOM</Button>
      </div>
    </div>
  );
}
