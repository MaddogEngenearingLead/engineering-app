import React from 'react';
import ReviewBOM from '../components/ReviewBOM.jsx';

export default function ReviewPage({ state, dispatch }) {
  return (
    <ReviewBOM result={state.result} flagStatus={state.flagStatus}
      onFlag={(id, value) => dispatch({ type: 'flag', id, value })}
      onBack={() => dispatch({ type: 'goto', step: 'results' })} />
  );
}
