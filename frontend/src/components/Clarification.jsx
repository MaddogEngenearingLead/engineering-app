import React from 'react';
import Button from './common/Button.jsx';
import Card from './common/Card.jsx';
import useClarification from '../hooks/useClarification.js';

const MEANINGS = ['new_work', 'demo', 'future_work', 'ignore'];

function LegendQuestion({ q, value, onChange }) {
  return (
    <div className="space-y-1">
      {q.candidate_pages.map((p) => (
        <label key={p} className="block text-sm">
          <input type="radio" name={q.id} checked={value === p} onChange={() => onChange(p)} /> Page {p}
          {q.scores?.[p] !== undefined && <span className="text-slate-500"> (score {q.scores[p]})</span>}
        </label>
      ))}
    </div>
  );
}

function PairQuestion({ q, value, onChange }) {
  const pairs = q.candidate_pairs || [];
  const options = [{ label: 'Use all pairs', pairs }, ...pairs.map((p) => ({ label: `Demo page ${p.demo} → new work page ${p.new_work}`, pairs: [p] }))];
  return (
    <div className="space-y-1">
      {options.map((o) => (
        <label key={o.label} className="block text-sm">
          <input type="radio" name={q.id} checked={value === o.pairs} onChange={() => onChange(o.pairs)} /> {o.label}
        </label>
      ))}
      <ul className="mt-2 text-xs text-slate-600">
        {pairs.map((p) => (
          <li key={`${p.demo}-${p.new_work}`}>
            {p.demo}/{p.new_work}: similarity {Math.round(p.similarity * 100)}%, overlap tags {(p.overlap_tags || []).join(', ') || 'none'}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ColourQuestion({ q, value = {}, onChange }) {
  const colours = Object.keys(q.detected || {});
  return (
    <div className="space-y-2">
      {colours.map((c) => (
        <label key={c} className="flex items-center gap-2 text-sm">
          <span className="w-56">{c}: {q.detected[c]}</span>
          <select className="rounded border border-slate-300 p-1" value={value[c] || ''}
            onChange={(e) => onChange({ ...value, [c]: e.target.value })}>
            <option value="">Select meaning…</option>
            {MEANINGS.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </label>
      ))}
    </div>
  );
}

const complete = (q, a) => (q.type === 'out_of_scheme_colour' ? Object.keys(q.detected || {}).every((c) => a?.[c]) : a !== undefined);

export default function Clarification({ result, onSubmit }) {
  const questions = result.questions || [];
  const { answers, answer, toOverrides } = useClarification(questions);
  const ready = questions.every((q) => complete(q, answers[q.id]));
  const summary = result.detected_summary;

  return (
    <div className="space-y-4">
      <Card title="Clarification needed">
        <p className="text-sm text-slate-600">The scan could not decide everything automatically. Please confirm below.</p>
      </Card>
      {questions.map((q) => (
        <Card key={q.id} title={q.message}>
          {q.type === 'legend_not_identified' && <LegendQuestion q={q} value={answers[q.id]} onChange={(v) => answer(q.id, v)} />}
          {q.type === 'demo_work_pages_ambiguous' && <PairQuestion q={q} value={answers[q.id]} onChange={(v) => answer(q.id, v)} />}
          {q.type === 'out_of_scheme_colour' && <ColourQuestion q={q} value={answers[q.id]} onChange={(v) => answer(q.id, v)} />}
        </Card>
      ))}
      {summary && (
        <Card title="Detected data">
          <div className="text-sm">
            {summary.legend_candidates && <p>Legend candidates: pages {summary.legend_candidates.join(', ')}</p>}
            {(summary.page_pairs || []).map((p) => <p key={p.pages.join('-')}>Pages {p.pages.join(' ↔ ')}: overlap {Math.round(p.overlap * 100)}%</p>)}
            {Object.entries(summary.colours || {}).map(([c, n]) => <p key={c}><code>{c}</code>: {n} marks</p>)}
          </div>
        </Card>
      )}
      <Button disabled={!ready} onClick={() => onSubmit(toOverrides())}>Resubmit with clarifications</Button>
    </div>
  );
}
