import React from 'react';
import Upload from '../components/Upload.jsx';
import Processing from '../components/Processing.jsx';

export default function ScanPage({ state, onSubmit }) {
  if (state.step === 'processing') return <Processing message={state.statusMessage} />;
  return <Upload onSubmit={onSubmit} error={state.error} />;
}
