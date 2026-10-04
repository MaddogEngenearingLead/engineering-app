import React from 'react';

/** columns: [{ key, label, render?(row) }] */
export default function Table({ columns, rows, rowKey = (r, i) => i, empty = 'No data' }) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="bg-slate-200">
          <tr>
            {columns.map((c) => (
              <th key={c.key} className="px-3 py-2 font-semibold">{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr><td className="px-3 py-2 text-slate-500" colSpan={columns.length}>{empty}</td></tr>
          )}
          {rows.map((row, i) => (
            <tr key={rowKey(row, i)} className="border-t border-slate-200">
              {columns.map((c) => (
                <td key={c.key} className="px-3 py-2">{c.render ? c.render(row) : row[c.key] ?? ''}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
