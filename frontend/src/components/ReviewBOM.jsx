import React from 'react';
import Button from './common/Button.jsx';
import Card from './common/Card.jsx';
import BOMTable from './BOMTable.jsx';
import FlagsPanel from './FlagsPanel.jsx';
import { bomPdfUrl } from '../services/api.js';

const csvCell = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`;

function download(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export default function ReviewBOM({ result, flagStatus, onFlag, onBack }) {
  const items = result.materials || [];
  const flags = (result.flags || []).map((f) => ({ ...f, status: flagStatus[f.id] || '' }));
  const base = result.job_number || result.job_id || 'bom';
  const pdf = bomPdfUrl(result.bom_pdf);

  const exportCsv = () => {
    const cols = ['item_number', 'tag_id', 'description', 'type', 'quantity', 'page', 'location', 'colour_meaning', 'scope_source'];
    const text = [cols.join(','), ...items.map((r) => cols.map((c) => csvCell(r[c])).join(','))].join('\n');
    download(`${base}.csv`, text, 'text/csv');
  };
  const exportJson = () => download(`${base}.json`, JSON.stringify({ ...result, flags }, null, 2), 'application/json');

  return (
    <div className="space-y-4">
      <Card title="BOM"><BOMTable items={items} full /></Card>
      <Card title="Flags and review items"><FlagsPanel flags={result.flags || []} flagStatus={flagStatus} onChange={onFlag} /></Card>
      <div className="flex flex-wrap gap-3">
        {pdf ? <a href={pdf} download><Button>Export PDF</Button></a> : <Button disabled>Export PDF</Button>}
        <Button onClick={exportCsv}>Export CSV</Button>
        <Button onClick={exportJson}>Export JSON</Button>
        <Button variant="secondary" onClick={onBack}>Back</Button>
      </div>
    </div>
  );
}
