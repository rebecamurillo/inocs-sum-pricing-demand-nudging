/** An instance version as a link writes it: `geneva-3km.v2`. */
export interface InstanceVersionRef {
  readonly instanceId: string;
  readonly version: number;
}

interface WithPeriod {
  readonly period: string | null;
}

export type LabRoute = WithPeriod &
  (
    | { readonly kind: 'lab' }
    | { readonly kind: 'instance'; readonly instance: InstanceVersionRef }
    | { readonly kind: 'pricing'; readonly instance: InstanceVersionRef; readonly letter: string }
    | { readonly kind: 'result'; readonly instance: InstanceVersionRef; readonly letter: string }
    | {
        readonly kind: 'compare';
        readonly instance: InstanceVersionRef;
        readonly letters: readonly string[];
      }
    | { readonly kind: 'traveller'; readonly instance: InstanceVersionRef; readonly letter: string }
  );

export type ParsedRoute = LabRoute | { readonly kind: 'unparsable' };

const unparsable: ParsedRoute = { kind: 'unparsable' };

// One canonical spelling per route, so that serialise(parse(x)) is x for every valid link.
const INSTANCE = /^([a-z0-9]+(?:-[a-z0-9]+)*)\.v([1-9][0-9]*)$/;
const LETTER = /^[A-Z]+$/;
const PERIOD = /^[A-Za-z0-9._:-]+$/;
const MIN_COMPARE = 2;
const MAX_COMPARE = 4;

function parseInstance(segment: string | undefined): InstanceVersionRef | null {
  const match = segment === undefined ? null : INSTANCE.exec(segment);
  const [, instanceId, version] = match ?? [];
  if (instanceId === undefined || version === undefined) return null;
  return { instanceId, version: Number(version) };
}

function parseLetters(segment: string | undefined): readonly string[] | null {
  if (segment === undefined) return null;
  const letters = segment.split(',');
  const ok =
    letters.length >= MIN_COMPARE &&
    letters.length <= MAX_COMPARE &&
    letters.every((letter) => LETTER.test(letter)) &&
    new Set(letters).size === letters.length;
  return ok ? letters : null;
}

function parsePath(segments: readonly string[], period: string | null): ParsedRoute {
  const [first, second, third, fourth, ...rest] = segments;
  if (first === undefined) return { kind: 'lab', period };
  if (rest.length > 0) return unparsable;

  if (first === 'traveller') {
    const instance = parseInstance(second);
    if (instance === null || third === undefined || !LETTER.test(third) || fourth !== undefined) {
      return unparsable;
    }
    return { kind: 'traveller', instance, letter: third, period };
  }

  const instance = parseInstance(first);
  if (instance === null || fourth !== undefined) return unparsable;
  if (second === undefined) return { kind: 'instance', instance, period };
  if (third === undefined) return unparsable;

  if (second === 'compare') {
    const letters = parseLetters(third);
    return letters === null ? unparsable : { kind: 'compare', instance, letters, period };
  }
  if ((second === 'pricing' || second === 'result') && LETTER.test(third)) {
    return { kind: second, instance, letter: third, period };
  }
  return unparsable;
}

export function parseRoute(hash: string): ParsedRoute {
  if (!hash.startsWith('#/lab')) return unparsable;
  const [path = '', query, ...extra] = hash.slice('#/lab'.length).split('?');
  if (extra.length > 0) return unparsable;

  let period: string | null = null;
  if (query !== undefined) {
    const value = query.startsWith('period=') ? query.slice('period='.length) : '';
    if (!PERIOD.test(value)) return unparsable;
    period = value;
  }

  if (path === '') return { kind: 'lab', period };
  if (!path.startsWith('/')) return unparsable;
  const segments = path.slice(1).split('/');
  return parsePath(segments, period);
}

/** The compare route with its letters in letter order, each once: the one spelling every link writes. */
export function compareRoute(
  instance: InstanceVersionRef,
  letters: readonly string[],
  period: string | null,
): LabRoute {
  return { kind: 'compare', instance, letters: [...new Set(letters)].sort(), period };
}

/** L-5 for one finished pricing version; `period` null leaves the choice to the version. */
export function travellerRoute(
  instance: InstanceVersionRef,
  letter: string,
  period: string | null,
): LabRoute {
  return { kind: 'traveller', instance, letter, period };
}

export function serialiseInstance(instance: InstanceVersionRef): string {
  return `${instance.instanceId}.v${String(instance.version)}`;
}

function serialisePath(route: LabRoute): string {
  switch (route.kind) {
    case 'lab':
      return '';
    case 'instance':
      return `/${serialiseInstance(route.instance)}`;
    case 'pricing':
      return `/${serialiseInstance(route.instance)}/pricing/${route.letter}`;
    case 'result':
      return `/${serialiseInstance(route.instance)}/result/${route.letter}`;
    case 'compare':
      return `/${serialiseInstance(route.instance)}/compare/${route.letters.join(',')}`;
    case 'traveller':
      return `/traveller/${serialiseInstance(route.instance)}/${route.letter}`;
  }
}

export function serialiseRoute(route: LabRoute): string {
  const query = route.period === null ? '' : `?period=${route.period}`;
  return `#/lab${serialisePath(route)}${query}`;
}
