import { describe, expect, it } from 'vitest';
import { DIVERGING, RADIUS, divergingScale } from './diverging-scale';

describe('the diverging scale', () => {
  it('maps minus m, 0 and plus m to the three anchors', () => {
    const scale = divergingScale([-0.4, 0.1, 0.2, 0]);
    expect(scale.m).toBe(0.4);
    expect(scale.colour(-0.4)).toBe('#b4530a');
    expect(scale.colour(0)).toBe('#c9cdc8');
    expect(scale.colour(0.4)).toBe('#00336e');
    expect(DIVERGING).toEqual({ lower: '#b4530a', none: '#c9cdc8', higher: '#00336e' });
  });

  it('is symmetric: the end is the largest absolute value on either side', () => {
    const scale = divergingScale([0.3, 0.1]);
    expect(scale.m).toBe(0.3);
    expect(scale.colour(-0.3)).toBe('#b4530a');
    expect(scale.colour(0.3)).toBe('#00336e');
  });

  it('interpolates linearly in RGB between the neighbouring anchors', () => {
    const scale = divergingScale([-2, 2]);
    // midpoint of #b4530a (180, 83, 10) and #c9cdc8 (201, 205, 200), each channel rounded
    expect(scale.colour(-1)).toBe('#bf9069');
    // midpoint of #c9cdc8 (201, 205, 200) and #00336e (0, 51, 110)
    expect(scale.colour(1)).toBe('#65809b');
  });

  it('grows the radius linearly with the absolute value, 10 px at 0 and 28 px at m', () => {
    const scale = divergingScale([-4, 2]);
    expect(RADIUS).toEqual({ min: 10, max: 28 });
    expect(scale.radius(0)).toBe(10);
    expect(scale.radius(4)).toBe(28);
    expect(scale.radius(-4)).toBe(28);
    expect(scale.radius(2)).toBe(19);
    expect(scale.radius(-2)).toBe(19);
  });

  it('draws every value as no change at 10 px when every difference is 0 or there is none', () => {
    for (const values of [[0, 0, 0], []]) {
      const scale = divergingScale(values);
      expect(scale.m).toBe(0);
      expect(scale.colour(0)).toBe('#c9cdc8');
      expect(scale.radius(0)).toBe(10);
    }
  });

  it('keeps a value beyond m at the end of the scale', () => {
    const scale = divergingScale([1]);
    expect(scale.colour(5)).toBe('#00336e');
    expect(scale.radius(-5)).toBe(28);
  });
});
