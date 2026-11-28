import type { LayoutPreferencesValue } from '../../domain/layout';

/** The visitor's layout choices, kept between visits. */
export interface LayoutPreferences {
  load(): LayoutPreferencesValue;
  save(value: LayoutPreferencesValue): void;
}
