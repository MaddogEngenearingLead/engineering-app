import React from 'react';
import Button from './common/Button.jsx';
import Card from './common/Card.jsx';
import useClarification from '../hooks/useClarification.js';

// Backend emits one question type: demo_work_pages_ambiguous with candidate_pairs [{pages:[a,b], similarity}].
// Direction is unknown, so offer both for each pair.
function PairQuestion({ q, value, onChange }) {
  const options = (q.candidate_pairs || []).flatMap((p) => {
    const [a, b] = p.pages;
    const sim = typeof p.similarity === 'number' ? ` (similarity ${Math.round(p.similarity * 100)}%)` : '';
    return [
      { label: `Page ${a} = demo, page ${b} = new work${sim}`, pairs: [{ demo: a, new_work: b }] },
      { label: `Page ${b} = demo, page ${a} = new work${sim}`, pairs: [{ demo: b, new_work: a }] },
    ];
  });
  if (options.length === 0) {
    return <p className="text-sm text-slate-500">No candidate pairs were found. Use Edit and Resubmit to enter page numbers (document has pages {(q.pages || []).join(', ')}).</p>;
  }
  return (
    <div className="space-y-1">
      {options.map((o) => (
        <label key={o.label} className="block text-sm">
          <input type="radio" name={q.id} checked={value === o.pairs} onChange={() => onChange(o.pairs)} /> {o.label}
        </label>
      ))}
    </div>
  );
}

export default function Clarification({ result, onSubmit }) {
  const questions = result.questions || [];
  const { answers, answer, toOverrides } = useClarification(questions);
  const ready = questions.length > 0 && questions.every((q) => answers[q.id] !== undefined);

  return (
    <div className="space-y-4">
      <Card title="Clarification needed">
        <p className="text-sm text-slate-600">The scan could not decide everything automatically. Please confirm below.</p>
      </Card>
      {questions.map((q) => (
        <Card key={q.id} title={q.message}>
          <PairQuestion q={q} value={answers[q.id]} onChange={(v) => answer(q.id, v)} />
        </Card>
      ))}
      <Button disabled={!ready} onClick={() => onSubmit(toOverrides())}>Resubmit with clarifications</Button>
    </div>
  );
}
