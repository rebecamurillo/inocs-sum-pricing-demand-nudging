/** The colour ramp and the width range of the lines of Home's map. */
export const HOME_RAMP = { low: '#e3ebf5', high: '#00336e' } as const;
export const LINE_WIDTH_PX = { min: 1, max: 7 } as const;

/** Where `value` lies between `min` and `max`, 0 to 1; the midpoint when they are equal. */
function position(value: number, min: number, max: number): number {
  return max === min ? 0.5 : (value - min) / (max - min);
}

const channels = (hex: string): readonly number[] =>
  [1, 3, 5].map((at) => Number.parseInt(hex.slice(at, at + 2), 16));

/** The colour of `value` on the ramp, interpolated linearly in RGB from the lowest to the highest. */
export function linearColour(value: number, min: number, max: number): string {
  const t = position(value, min, max);
  const low = channels(HOME_RAMP.low);
  const high = channels(HOME_RAMP.high);
  const mixed = low.map((from, at) => Math.round(from + t * ((high[at] ?? from) - from)));
  return `#${mixed.map((channel) => channel.toString(16).padStart(2, '0')).join('')}`;
}

/** The width in pixels of `value`, linear from 1 to 7. */
export function lineWidth(value: number, min: number, max: number): number {
  return LINE_WIDTH_PX.min + position(value, min, max) * (LINE_WIDTH_PX.max - LINE_WIDTH_PX.min);
}
