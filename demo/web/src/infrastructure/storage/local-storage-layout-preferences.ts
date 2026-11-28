import type { LayoutPreferences } from '../../application/ports/layout-preferences';
import {
  DEFAULT_LAYOUT,
  MAX_MAP_SHARE,
  MIN_MAP_SHARE,
  type LayoutPreferencesValue,
} from '../../domain/layout';

export const LAYOUT_STORAGE_KEY = 'pricing-demo.layout';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function flag(value: unknown, fallback: boolean): boolean {
  return typeof value === 'boolean' ? value : fallback;
}

function shares(value: unknown): Readonly<Record<string, number>> {
  if (!isRecord(value)) return DEFAULT_LAYOUT.mapShare;
  const valid = Object.entries(value).filter(
    (entry): entry is [string, number] =>
      typeof entry[1] === 'number' && entry[1] >= MIN_MAP_SHARE && entry[1] <= MAX_MAP_SHARE,
  );
  return { ...DEFAULT_LAYOUT.mapShare, ...Object.fromEntries(valid) };
}

/** The only code that touches the browser's storage; the composition root hands it the Storage. */
export class LocalStorageLayoutPreferences implements LayoutPreferences {
  private readonly storage: Storage | null;

  /** `null` when the browser refuses site storage: the defaults then hold for the visit. */
  constructor(storage: Storage | null) {
    this.storage = storage;
  }

  load(): LayoutPreferencesValue {
    let stored: unknown;
    if (this.storage === null) return DEFAULT_LAYOUT;
    try {
      const raw = this.storage.getItem(LAYOUT_STORAGE_KEY);
      if (raw === null) return DEFAULT_LAYOUT;
      stored = JSON.parse(raw);
    } catch {
      // Storage denied or the text is not JSON: an unreadable value gives the defaults.
      return DEFAULT_LAYOUT;
    }
    if (!isRecord(stored)) return DEFAULT_LAYOUT;
    return {
      menuOpen: flag(stored.menuOpen, DEFAULT_LAYOUT.menuOpen),
      mapShown: flag(stored.mapShown, DEFAULT_LAYOUT.mapShown),
      advancedView: flag(stored.advancedView, DEFAULT_LAYOUT.advancedView),
      largeText: flag(stored.largeText, DEFAULT_LAYOUT.largeText),
      mapShare: shares(stored.mapShare),
    };
  }

  save(value: LayoutPreferencesValue): void {
    try {
      this.storage?.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(value));
    } catch {
      // A full or blocked storage must not break the page: the choice then lasts until reload.
    }
  }
}
