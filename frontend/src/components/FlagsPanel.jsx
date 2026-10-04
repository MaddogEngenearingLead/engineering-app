import React from 'react';

const STATUSES = [
  ['', 'Open'],
  ['reviewed', 'Reviewed'],
  ['needs_action', 'Needs action'],
  ['resolved', 'Resolved'],
];

export default function FlagsPanel({ flags = [], flagStatus = {}, onChange }) {
  if (flags.length === 0) return <p className="text-sm text-slate-500">No flags.</p>;
  return (
    <ul className="space-y-2">
      {flags.map((f) => (
        <li key={f.id} className="rounded border border-slate-200 p-3 text-sm">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-medium">{String(f.type).replace(/_/g, ' ')}</span>
            <span className="text-slate-500">Page {f.page ?? '?'} · {f.location ?? 'n/a'}</span>
          </div>
          <p className="my-1">{f.message}</p>
          <label className="text-xs">
            Status{' '}
            <select className="rounded border border-slate-300 p-1" value={flagStatus[f.id] || ''}
              onChange={(e) => onChange(f.id, e.target.value)}>
              {STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
        </li>
      ))}
    </ul>
  );
}
