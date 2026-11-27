import { useCallback, useEffect, useState } from 'react';
import { parseRoute, serialiseRoute, type LabRoute } from '../../domain/route';

const HOME = '#/lab';

/** The route of the current hash; a hash that does not parse is replaced by `#/lab` in place. */
function readRoute(): LabRoute {
  const parsed = parseRoute(window.location.hash);
  if (parsed.kind !== 'unparsable') return parsed;
  // replaceState, not an assignment: the bad link leaves no history entry to go back to.
  window.history.replaceState(
    null,
    '',
    `${window.location.pathname}${window.location.search}${HOME}`,
  );
  return { kind: 'lab', period: null };
}

export function useHashRoute(): {
  route: LabRoute;
  navigate: (route: LabRoute) => void;
  /** Rewrites the hash in place: no history entry, no reload. */
  replace: (route: LabRoute) => void;
} {
  const [route, setRoute] = useState<LabRoute>(readRoute);

  useEffect(() => {
    const onChange = () => {
      setRoute(readRoute());
    };
    window.addEventListener('hashchange', onChange);
    return () => {
      window.removeEventListener('hashchange', onChange);
    };
  }, []);

  const navigate = useCallback((next: LabRoute) => {
    window.location.hash = serialiseRoute(next);
  }, []);

  const replace = useCallback((next: LabRoute) => {
    window.history.replaceState(
      null,
      '',
      `${window.location.pathname}${window.location.search}${serialiseRoute(next)}`,
    );
    setRoute(readRoute());
  }, []);

  return { route, navigate, replace };
}
