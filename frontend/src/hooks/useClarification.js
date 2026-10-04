import { useState } from 'react';

/** Collects answers to clarification questions and converts them to API overrides. */
export default function useClarification(questions = []) {
  const [answers, setAnswers] = useState({});
  const answer = (id, value) => setAnswers((a) => ({ ...a, [id]: value }));

  const complete = questions.every((q) => answers[q.id] !== undefined && answers[q.id] !== '');

  const toOverrides = () => {
    const out = {};
    questions.forEach((q) => {
      const a = answers[q.id];
      if (a === undefined) return;
      if (q.type === 'legend_not_identified') out.legend_page = a;
      else if (q.type === 'demo_work_pages_ambiguous') {
        const pairs = a; // array of {demo,new_work}
        out.demo_pages = pairs.map((p) => p.demo);
        out.new_work_pages = pairs.map((p) => p.new_work);
      } else if (q.type === 'out_of_scheme_colour') out.highlight_mapping = { ...(out.highlight_mapping || {}), ...a };
    });
    return out;
  };

  return { answers, answer, complete, toOverrides };
}
