import React, { createContext, useContext, useMemo, useReducer } from 'react';

const initial = {
  step: 'upload', // upload | processing | results | clarification | edit | review
  inputs: null, // { pidFile, scopeFile, reviewNotes }
  overrides: {},
  result: null,
  error: null,
  statusMessage: '',
  flagStatus: {}, // flag id -> reviewed | needs_action | resolved
};

function reducer(state, action) {
  switch (action.type) {
    case 'start':
      return { ...state, step: 'processing', inputs: action.inputs, overrides: action.overrides ?? state.overrides, error: null, statusMessage: '' };
    case 'status':
      return { ...state, statusMessage: action.message };
    case 'success':
      return { ...state, step: action.result.status === 'needs_clarification' ? 'clarification' : 'results', result: action.result };
    case 'failure':
      return { ...state, step: state.result ? 'results' : 'upload', error: action.error };
    case 'goto':
      return { ...state, step: action.step };
    case 'flag':
      return { ...state, flagStatus: { ...state.flagStatus, [action.id]: action.value } };
    case 'reset':
      return initial;
    default:
      return state;
  }
}

const ScanContext = createContext(null);

export function ScanProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, initial);
  const value = useMemo(() => ({ state, dispatch }), [state]);
  return React.createElement(ScanContext.Provider, { value }, children);
}

export const useScanContext = () => useContext(ScanContext);
