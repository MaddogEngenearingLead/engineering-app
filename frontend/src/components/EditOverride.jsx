import React from 'react';
import Button from './common/Button.jsx';
import Card from './common/Card.jsx';
import useFormState, { parsePageList } from '../hooks/useFormState.js';

const MEANINGS = ['', 'new_work', 'demo'];

export default function EditOverride({ result, onSubmit, onCancel }) {
  const colours = Object.keys(result?.colour_scheme?.colours_detected || {});
  const [form, setField] = useFormState({
    legend: result?.legend_detected?.page ?? '',
    demo: (result?.page_classification?.demo_pages || []).join(', '),
    newWork: (result?.page_classification?.new_work_pages || []).join(', '),
    meanings: Object.fromEntries(colours.map((c) => [c, ''])),
  });

  const build = () => ({
    legend_page: form.legend ? parseInt(form.legend, 10) : undefined,
    demo_pages: parsePageList(form.demo),
    new_work_pages: parsePageList(form.newWork),
    highlight_mapping: Object.fromEntries(Object.entries(form.meanings).filter(([, v]) => v)),
  });
  const preview = build();

  return (
    <Card title="Edit and resubmit">
      <div className="space-y-4 text-sm">
        <label className="block">Legend page
          <input type="number" min="1" className="ml-2 w-24 rounded border border-slate-300 p-1" value={form.legend} onChange={(e) => setField('legend', e.target.value)} />
        </label>
        <label className="block">Demo pages (comma separated)
          <input className="ml-2 rounded border border-slate-300 p-1" value={form.demo} onChange={(e) => setField('demo', e.target.value)} />
        </label>
        <label className="block">New-work pages (comma separated)
          <input className="ml-2 rounded border border-slate-300 p-1" value={form.newWork} onChange={(e) => setField('newWork', e.target.value)} />
        </label>
        <fieldset>
          <legend className="font-medium">Colour meanings (override)</legend>
          {colours.map((c) => (
            <label key={c} className="mt-1 flex items-center gap-2">
              <code className="w-32">{c}</code>
              <select className="rounded border border-slate-300 p-1" value={form.meanings[c]}
                onChange={(e) => setField('meanings', { ...form.meanings, [c]: e.target.value })}>
                {MEANINGS.map((m) => <option key={m} value={m}>{m || '(auto)'}</option>)}
              </select>
            </label>
          ))}
        </fieldset>
        <div>
          <h3 className="font-medium">Preview</h3>
          <pre className="overflow-auto rounded bg-slate-100 p-2 text-xs">{JSON.stringify(preview, null, 2)}</pre>
        </div>
        <div className="flex gap-3">
          <Button onClick={() => onSubmit(preview)}>Resubmit</Button>
          <Button variant="secondary" onClick={onCancel}>Cancel</Button>
        </div>
      </div>
    </Card>
  );
}
