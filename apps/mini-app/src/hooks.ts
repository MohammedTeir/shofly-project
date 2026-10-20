import { DependencyList, useCallback, useEffect, useState } from "react";

export function useAsync<T>(fn: () => Promise<T>, deps: DependencyList) {
  const [s, setS] = useState<{ data?: T; error?: unknown; loading: boolean }>({ loading: true });
  const run = useCallback(() => {
    let live = true;
    setS((p) => ({ ...p, loading: true, error: undefined }));
    fn().then((data) => live && setS({ data, loading: false }), (error) => live && setS({ error, loading: false }));
    return () => { live = false; };
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(run, [run]);
  return { ...s, reload: run };
}

export function useDebounced<T>(value: T, ms = 300) {
  const [v, setV] = useState(value);
  useEffect(() => { const id = setTimeout(() => setV(value), ms); return () => clearTimeout(id); }, [value, ms]);
  return v;
}
