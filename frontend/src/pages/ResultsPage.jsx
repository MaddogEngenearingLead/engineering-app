import React from 'react';
import Results from '../components/Results.jsx';
import Clarification from '../components/Clarification.jsx';
import EditOverride from '../components/EditOverride.jsx';

export default function ResultsPage({ state, dispatch, resubmit }) {
  const { step, result } = state;
  if (step === 'clarification') return <Clarification result={result} onSubmit={resubmit} />;
  if (step === 'edit') return <EditOverride result={result} onSubmit={resubmit} onCancel={() => dispatch({ type: 'goto', step: 'results' })} />;
  return (
    <>
      {state.error && <p className="mb-2 text-sm text-red-600" role="alert">{state.error}</p>}
      <Results result={result} onEdit={() => dispatch({ type: 'goto', step: 'edit' })} onReview={() => dispatch({ type: 'goto', step: 'review' })} />
    </>
  );
}
