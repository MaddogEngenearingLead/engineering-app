import React from 'react';
import Button from './common/Button.jsx';
import Card from './common/Card.jsx';
import useFormState from '../hooks/useFormState.js';

export default function Upload({ onSubmit, error }) {
  const [form, setField] = useFormState({ pidFile: null, scopeFile: null, reviewNotes: '' });

  const submit = (e) => {
    e.preventDefault();
    if (form.pidFile) onSubmit(form);
  };

  return (
    <Card title="Upload P&ID">
      <form onSubmit={submit} className="space-y-4">
        <label className="block">
          <span className="text-sm font-medium">P&amp;ID PDF (required)</span>
          <input type="file" accept="application/pdf,.pdf" required className="mt-1 block w-full"
            onChange={(e) => setField('pidFile', e.target.files[0] || null)} />
        </label>
        <label className="block">
          <span className="text-sm font-medium">Scope document (optional — auto-detected if omitted)</span>
          <input type="file" accept=".doc,.docx,.pdf,.txt" className="mt-1 block w-full"
            onChange={(e) => setField('scopeFile', e.target.files[0] || null)} />
        </label>
        <label className="block">
          <span className="text-sm font-medium">Review notes (optional)</span>
          <textarea rows={3} className="mt-1 block w-full rounded border border-slate-300 p-2"
            value={form.reviewNotes} onChange={(e) => setField('reviewNotes', e.target.value)} />
        </label>
        {error && <p className="text-sm text-red-600" role="alert">{error}</p>}
        <Button type="submit" disabled={!form.pidFile}>Scan P&amp;ID</Button>
      </form>
    </Card>
  );
}
