import React from 'react';

export default function Spinner({ label }) {
  return (
    <div className="flex items-center gap-3" role="status">
      <div className="h-6 w-6 animate-spin rounded-full border-4 border-slate-300 border-t-blue-600" />
      {label && <span>{label}</span>}
    </div>
  );
}
