import { useCallback, useState } from 'react';

export default function useFormState(initial) {
  const [values, setValues] = useState(initial);
  const setField = useCallback((name, value) => setValues((v) => ({ ...v, [name]: value })), []);
  return [values, setField, setValues];
}

export const parsePageList = (text) =>
  String(text || '')
    .split(/[,\s]+/)
    .map((s) => parseInt(s, 10))
    .filter((n) => Number.isInteger(n) && n > 0);
