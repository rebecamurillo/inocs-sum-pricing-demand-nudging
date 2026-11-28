import { describe, expect, it } from 'vitest';
import { HOME_RAMP, lineWidth, linearColour } from './home-map';

describe('linearColour', () => {
  it('is the low colour at the lowest value and the high colour at the highest', () => {
    expect(linearColour(0.5, 0.5, 1.5)).toBe(HOME_RAMP.low);
    expect(linearColour(1.5, 0.5, 1.5)).toBe(HOME_RAMP.high);
  });

  it('mixes the channels linearly in between', () => {
    // (0xe3 + 0x00) / 2 = 113.5, (0xeb + 0x33) / 2 = 143, (0xf5 + 0x6e) / 2 = 177.5
    expect(linearColour(1, 0.5, 1.5)).toBe('#728fb2');
  });

  it('is the midpoint when every drawn pair has one value', () => {
    expect(linearColour(0.8, 0.8, 0.8)).toBe('#728fb2');
  });
});

describe('lineWidth', () => {
  it('runs from 1 to 7 pixels', () => {
    expect(lineWidth(3, 3, 11)).toBe(1);
    expect(lineWidth(11, 3, 11)).toBe(7);
    expect(lineWidth(7, 3, 11)).toBe(4);
  });

  it('is the midpoint when every drawn pair has one value', () => {
    expect(lineWidth(5, 5, 5)).toBe(4);
  });
});
