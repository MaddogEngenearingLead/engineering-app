import { useCallback, useEffect, useRef } from 'react';
import { useScanContext } from '../context/ScanContext.js';
import { scanPid, errorMessage } from '../services/api.js';

const STATUS_MESSAGES = ['Detecting pages...', 'Extracting legend...', 'Comparing content...', 'Detecting colour scheme...', 'Building BOM...'];

export default function useScan() {
  const { state, dispatch } = useScanContext();
  const timer = useRef(null);

  const stopTicker = () => timer.current && clearInterval(timer.current);
  useEffect(() => stopTicker, []);

  const submit = useCallback(
    async (inputs, overrides = {}) => {
      dispatch({ type: 'start', inputs, overrides });
      let i = 0;
      dispatch({ type: 'status', message: STATUS_MESSAGES[0] });
      stopTicker();
      timer.current = setInterval(() => {
        i = Math.min(i + 1, STATUS_MESSAGES.length - 1);
        dispatch({ type: 'status', message: STATUS_MESSAGES[i] });
      }, 1500);
      try {
        const result = await scanPid({ ...inputs, overrides });
        dispatch({ type: 'success', result });
      } catch (err) {
        dispatch({ type: 'failure', error: errorMessage(err) });
      } finally {
        stopTicker();
      }
    },
    [dispatch]
  );

  const resubmit = useCallback((overrides) => submit(state.inputs, { ...state.overrides, ...overrides }), [state.inputs, state.overrides, submit]);

  return { state, dispatch, submit, resubmit };
}
