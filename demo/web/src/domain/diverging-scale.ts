/** The diverging scale of the L-4 map: lower, no change and higher, and the disc size of a difference. */

export const DIVERGING = { lower: '#b4530a', none: '#c9cdc8', higher: '#00336e' } as const;
export const RADIUS = { min: 10, max: 28 } as const;

export interface DivergingScale {
  /** The largest absolute value: the scale runs from minus m to plus m. */
  readonly m: number;
  readonly colour: (value: number) => string;
  /** The disc radius in px. */
  readonly radius: (value: number) => number;
}

const channels = (hex: string): readonly [number, number, number] => [
  parseInt(hex.slice(1, 3), 16),
  parseInt(hex.slice(3, 5), 16),
  parseInt(hex.slice(5, 7), 16),
];

function mix(from: string, to: string, t: number): string {
  const a = channels(from);
  const b = channels(to);
  return `#${a
    .map((start, at) => {
      const end = b[at] ?? start;
      return Math.round(start + (end - start) * t)
        .toString(16)
        .padStart(2, '0');
    })
    .join('')}`;
}

/** Symmetric around 0, its ends at minus and plus the largest absolute value of `values`. */
export function divergingScale(values: readonly number[]): DivergingScale {
  const m = Math.max(0, ...values.map((value) => Math.abs(value)));
  const share = (value: number): number => (m === 0 ? 0 : Math.min(1, Math.abs(value) / m));
  return {
    m,
    colour: (value) =>
      value < 0
        ? mix(DIVERGING.none, DIVERGING.lower, share(value))
        : mix(DIVERGING.none, DIVERGING.higher, share(value)),
    radius: (value) => RADIUS.min + (RADIUS.max - RADIUS.min) * share(value),
  };
}
