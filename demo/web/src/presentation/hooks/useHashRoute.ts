import { useCallback, useEffect, useState } from 'react';
import { parseRoute, serialiseAppRoute, type AppRoute, type LabRoute } from '../../domain/route';

const LAB = '#/lab';

/**
 * The route of the current hash. Home is every hash that is not a Lab link and is kept as typed;
 * a malformed Lab link is replaced by `#/lab` in place.
 */
function readRoute(): AppRoute {
  const parsed = parseRoute(window.location.hash);
  if (parsed.kind !== 'unparsable') return parsed;
  // replaceState, not an assignment: the bad link leaves no history entry to go back to.
  window.history.replaceState(
    null,
    '',
    `${window.location.pathname}${window.location.search}${LAB}`,
  );
  return { kind: 'lab', period: null };
}

export function useHashRoute(): {
  route: AppRoute;
  navigate: (route: AppRoute) => void;
  /** Rewrites the hash in place: no history entry, no reload. */
  replace: (route: AppRoute) => void;
} {
  const [route, setRoute] = useState<AppRoute>(readRoute);

  useEffect(() => {
    const onChange = () => {
      setRoute(readRoute());
    };
    window.addEventListener('hashchange', onChange);
    return () => {
      window.removeEventListener('hashchange', onChange);
    };
  }, []);

  const navigate = useCallback((next: AppRoute) => {
    window.location.hash = serialiseAppRoute(next);
  }, []);

  const replace = useCallback((next: AppRoute) => {
    window.history.replaceState(
      null,
      '',
      `${window.location.pathname}${window.location.search}${serialiseAppRoute(next)}`,
    );
    setRoute(readRoute());
  }, []);

  return { route, navigate, replace };
}

/** The same hook for the Lab, which renders only on Lab routes: Home reads as the Lab's own page. */
export function useLabRoute(): {
  route: LabRoute;
  navigate: (route: LabRoute) => void;
  replace: (route: LabRoute) => void;
} {
  const { route, navigate, replace } = useHashRoute();
  return {
    route: route.kind === 'home' ? { kind: 'lab', period: null } : route,
    navigate,
    replace,
  };
}
