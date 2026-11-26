import { useCallback, useEffect, useState } from 'react';
import { useGateways } from './gateways';
import { clampMapShare, mapShareFor, type LayoutPreferencesValue } from '../../domain/layout';

const LARGE_TEXT_ROOT_SIZE = '130%';

export interface LayoutControls {
  readonly preferences: LayoutPreferencesValue;
  readonly setMenuOpen: (open: boolean) => void;
  readonly setMapShown: (shown: boolean) => void;
  readonly setAdvancedView: (on: boolean) => void;
  readonly setLargeText: (on: boolean) => void;
  readonly setMapShare: (viewKey: string, share: number) => void;
  readonly mapShare: (viewKey: string) => number;
}

/** The layout choices, loaded once and saved at every change; Aa sets the root font size. */
export function useLayoutPreferences(): LayoutControls {
  const { layoutPreferences } = useGateways();
  const [preferences, setPreferences] = useState<LayoutPreferencesValue>(() =>
    layoutPreferences.load(),
  );

  const change = useCallback(
    (patch: (current: LayoutPreferencesValue) => LayoutPreferencesValue) => {
      setPreferences((current) => {
        const next = patch(current);
        layoutPreferences.save(next);
        return next;
      });
    },
    [layoutPreferences],
  );

  useEffect(() => {
    const root = document.documentElement;
    if (preferences.largeText) root.style.fontSize = LARGE_TEXT_ROOT_SIZE;
    else root.style.removeProperty('font-size');
    return () => {
      root.style.removeProperty('font-size');
    };
  }, [preferences.largeText]);

  return {
    preferences,
    setMenuOpen: (menuOpen) => {
      change((current) => ({ ...current, menuOpen }));
    },
    setMapShown: (mapShown) => {
      change((current) => ({ ...current, mapShown }));
    },
    setAdvancedView: (advancedView) => {
      change((current) => ({ ...current, advancedView }));
    },
    setLargeText: (largeText) => {
      change((current) => ({ ...current, largeText }));
    },
    setMapShare: (viewKey, share) => {
      change((current) => ({
        ...current,
        mapShare: { ...current.mapShare, [viewKey]: clampMapShare(share) },
      }));
    },
    mapShare: (viewKey) => mapShareFor(preferences, viewKey),
  };
}
