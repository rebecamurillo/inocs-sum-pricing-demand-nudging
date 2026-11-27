export interface LayoutPreferencesValue {
  readonly menuOpen: boolean;
  readonly mapShown: boolean;
  readonly advancedView: boolean;
  readonly largeText: boolean;
  /** The map's percentage of the work area, per view key. */
  readonly mapShare: Readonly<Record<string, number>>;
}

/** The empty Lab and L-1 share the key `instance` (UX-SPEC § Route: 50 %). */
export const EMPTY_LAB_VIEW = 'instance';
/** The result (L-3) keeps its own share under this key (UX-SPEC § Route: 36 %). */
export const RESULT_VIEW = 'result';
/** Compare versions (L-4) keeps its own share under this key (UX-SPEC § Route: 34 %). */
export const COMPARE_VIEW = 'compare';
/** The traveller view (L-5) keeps its own share under this key (UX-SPEC § Route: 44 %). */
export const TRAVELLER_VIEW = 'traveller';
const DEFAULT_MAP_SHARE = 50;
export const DEFAULT_MAP_SHARES: Readonly<Record<string, number>> = {
  [EMPTY_LAB_VIEW]: DEFAULT_MAP_SHARE,
  [RESULT_VIEW]: 36,
  [COMPARE_VIEW]: 34,
  [TRAVELLER_VIEW]: 44,
};
export const MIN_MAP_SHARE = 20;
export const MAX_MAP_SHARE = 80;
/** One arrow key moves the grip by 2 percentage points. */
export const GRIP_STEP = 2;

export const DEFAULT_LAYOUT: LayoutPreferencesValue = {
  menuOpen: true,
  mapShown: true,
  advancedView: false,
  largeText: false,
  mapShare: { [EMPTY_LAB_VIEW]: DEFAULT_MAP_SHARE },
};

/** Neither the card nor the map may fall below 20 % of the work area. */
export function clampMapShare(share: number): number {
  return Math.min(MAX_MAP_SHARE, Math.max(MIN_MAP_SHARE, share));
}

export function mapShareFor(preferences: LayoutPreferencesValue, viewKey: string): number {
  return preferences.mapShare[viewKey] ?? DEFAULT_MAP_SHARES[viewKey] ?? DEFAULT_MAP_SHARE;
}
