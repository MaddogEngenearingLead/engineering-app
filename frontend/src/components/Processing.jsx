import React from 'react';
import Card from './common/Card.jsx';
import Spinner from './common/Spinner.jsx';

export default function Processing({ message }) {
  return (
    <Card>
      <Spinner label="Scanning P&ID..." />
      {message && <p className="mt-3 text-sm text-slate-600" aria-live="polite">{message}</p>}
    </Card>
  );
}
