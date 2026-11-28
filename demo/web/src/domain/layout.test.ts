import { describe, expect, it } from 'vitest';
import {
  DEFAULT_LAYOUT,
  DEFAULT_MAP_SHARES,
  EMPTY_LAB_VIEW,
  RESULT_VIEW,
  clampMapShare,
  mapShareFor,
} from './layout';

describe('layout', () => {
  it('opens the menu and the map, with the empty Lab at 50 %', () => {
    expect(DEFAULT_LAYOUT).toMatchObject({
      menuOpen: true,
      mapShown: true,
      advancedView: false,
      largeText: false,
    });
    expect(mapShareFor(DEFAULT_LAYOUT, EMPTY_LAB_VIEW)).toBe(50);
  });

  it('keeps neither card nor map under 20 %', () => {
    expect(clampMapShare(5)).toBe(20);
    expect(clampMapShare(95)).toBe(80);
    expect(clampMapShare(44)).toBe(44);
  });

  it('reads a stored share and falls back to the default for another view', () => {
    const prefs = { ...DEFAULT_LAYOUT, mapShare: { result: 36 } };
    expect(mapShareFor(prefs, 'result')).toBe(36);
    expect(mapShareFor(prefs, 'other')).toBe(50);
    expect(mapShareFor(prefs, 'compare')).toBe(34);
  });

  it('gives a fresh layout 36 % for the result and 50 % for the instance', () => {
    expect(RESULT_VIEW).toBe('result');
    expect(DEFAULT_MAP_SHARES).toEqual({
      instance: 50,
      result: 36,
      compare: 34,
      traveller: 44,
    });
    expect(mapShareFor(DEFAULT_LAYOUT, 'traveller')).toBe(44);
    expect(mapShareFor(DEFAULT_LAYOUT, 'result')).toBe(36);
    expect(mapShareFor(DEFAULT_LAYOUT, 'instance')).toBe(50);
    expect(mapShareFor(DEFAULT_LAYOUT, 'other')).toBe(50);
    expect(mapShareFor({ ...DEFAULT_LAYOUT, mapShare: { result: 60 } }, 'result')).toBe(60);
  });
});
