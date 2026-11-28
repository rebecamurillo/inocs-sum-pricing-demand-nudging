import { describe, expect, it } from 'vitest';
import { DEFAULT_LAYOUT, type LayoutPreferencesValue } from '../../domain/layout';
import {
  LocalStorageLayoutPreferences,
  LAYOUT_STORAGE_KEY,
} from './local-storage-layout-preferences';

function memoryStorage(initial: Record<string, string> = {}): Storage {
  const data = new Map(Object.entries(initial));
  return {
    get length() {
      return data.size;
    },
    clear: () => {
      data.clear();
    },
    getItem: (key) => data.get(key) ?? null,
    key: (index) => [...data.keys()][index] ?? null,
    removeItem: (key) => {
      data.delete(key);
    },
    setItem: (key, value) => {
      data.set(key, value);
    },
  };
}

const chosen: LayoutPreferencesValue = {
  menuOpen: false,
  mapShown: false,
  advancedView: true,
  largeText: true,
  mapShare: { instance: 36, result: 44 },
};

describe('LocalStorageLayoutPreferences', () => {
  it('returns what it saved', () => {
    const adapter = new LocalStorageLayoutPreferences(memoryStorage());
    adapter.save(chosen);
    expect(adapter.load()).toEqual(chosen);
  });

  it('returns the defaults when nothing is stored', () => {
    expect(new LocalStorageLayoutPreferences(memoryStorage()).load()).toEqual(DEFAULT_LAYOUT);
  });

  it('returns the defaults for a value that is not JSON', () => {
    const storage = memoryStorage({ [LAYOUT_STORAGE_KEY]: '{not json' });
    expect(new LocalStorageLayoutPreferences(storage).load()).toEqual(DEFAULT_LAYOUT);
  });

  it('returns the defaults for a JSON value that is not an object', () => {
    for (const raw of ['null', '3', '"x"', '[]']) {
      const storage = memoryStorage({ [LAYOUT_STORAGE_KEY]: raw });
      expect(new LocalStorageLayoutPreferences(storage).load()).toEqual(DEFAULT_LAYOUT);
    }
  });

  it('replaces each field of the wrong type by its default and keeps the others', () => {
    const raw = JSON.stringify({
      menuOpen: 'yes',
      mapShown: false,
      advancedView: 1,
      largeText: true,
      mapShare: { instance: 'wide', result: 36, compare: 500 },
    });
    const storage = memoryStorage({ [LAYOUT_STORAGE_KEY]: raw });
    expect(new LocalStorageLayoutPreferences(storage).load()).toEqual({
      menuOpen: true,
      mapShown: false,
      advancedView: false,
      largeText: true,
      mapShare: { instance: 50, result: 36 },
    });
  });

  it('ignores a map share that is not an object', () => {
    const storage = memoryStorage({ [LAYOUT_STORAGE_KEY]: JSON.stringify({ mapShare: 40 }) });
    expect(new LocalStorageLayoutPreferences(storage).load()).toEqual(DEFAULT_LAYOUT);
  });

  it('returns the defaults when reading throws', () => {
    const storage = memoryStorage();
    storage.getItem = () => {
      throw new Error('denied');
    };
    expect(new LocalStorageLayoutPreferences(storage).load()).toEqual(DEFAULT_LAYOUT);
  });

  it('does not throw when writing fails', () => {
    const storage = memoryStorage();
    storage.setItem = () => {
      throw new Error('quota');
    };
    expect(() => {
      new LocalStorageLayoutPreferences(storage).save(chosen);
    }).not.toThrow();
  });

  it('gives the defaults and saves nothing when the browser refuses storage', () => {
    const adapter = new LocalStorageLayoutPreferences(null);
    expect(() => {
      adapter.save(chosen);
    }).not.toThrow();
    expect(adapter.load()).toEqual(DEFAULT_LAYOUT);
  });
});
