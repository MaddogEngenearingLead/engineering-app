import React from 'react';
import useScan from './hooks/useScan.js';
import ScanPage from './pages/ScanPage.jsx';
import ResultsPage from './pages/ResultsPage.jsx';
import ReviewPage from './pages/ReviewPage.jsx';

export default function App() {
  const { state, dispatch, submit, resubmit } = useScan();
  let page;
  if (['upload', 'processing'].includes(state.step)) page = <ScanPage state={state} onSubmit={(inputs) => submit(inputs)} />;
  else if (state.step === 'review') page = <ReviewPage state={state} dispatch={dispatch} />;
  else page = <ResultsPage state={state} dispatch={dispatch} resubmit={resubmit} />;

  return (
    <div className="mx-auto max-w-5xl p-6">
      <header className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">P&amp;ID Scan</h1>
        {state.step !== 'upload' && state.step !== 'processing' && (
          <button className="text-sm text-blue-600 underline" onClick={() => dispatch({ type: 'reset' })}>New scan</button>
        )}
      </header>
      {page}
    </div>
  );
}
