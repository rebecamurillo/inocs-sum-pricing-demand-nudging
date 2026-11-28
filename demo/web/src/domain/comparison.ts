/** The comparison of two to four versions as L-4 reads it (`GET /api/v1/comparisons`). */
import type { ResultNumber } from './pricing-result';

export const MIN_COMPARED = 2;
export const MAX_COMPARED = 4;

export interface ComparedSimulation {
  readonly priceScheme: 'model_prices' | 'flat';
  readonly ruleCurrent: boolean;
  readonly ruleVersion: number;
}

export interface ComparedVersion {
  /** `{instance version}.{letter}`. */
  readonly id: string;
  readonly letter: string;
  readonly name: string;
  readonly goals: Readonly<Record<string, ResultNumber>>;
  /** The id of the flat column the version is simulated with. */
  readonly flatReference: string;
  /** The package commit the version's solve ran with; null when it was not recorded. */
  readonly packageCommit: string | null;
  readonly packageFingerprint: string;
  readonly simulations: readonly ComparedSimulation[];
  readonly solveKey: string;
}

export interface FlatReference {
  readonly id: string;
  /** The versions the column serves, in letter order. */
  readonly letters: readonly string[];
  readonly flatPrice: number;
  readonly fare: number;
  readonly parkingFee: number;
  readonly costBike: number;
  readonly ruleCurrent: boolean;
  readonly ruleVersion: number;
}

export type GroupName = 'simulated' | 'model' | 'derived' | 'goals_that_differ' | 'solver';

export interface ComparisonRow {
  readonly key: string;
  /** Per version letter; null when the version has no value. */
  readonly values: Readonly<Record<string, ResultNumber | null>>;
  /** Simulated group only: the model's prices minus the flat simulation. */
  readonly changes: Readonly<Record<string, ResultNumber | null>>;
  /** Simulated group only: the value per flat reference id. */
  readonly flats: Readonly<Record<string, ResultNumber | null>>;
  /** The letters holding the best value; empty when none. */
  readonly best: readonly string[];
}

export interface ComparisonGroup {
  readonly name: GroupName;
  readonly rows: readonly ComparisonRow[];
}

/** One hub pair's mean bike price and travellers in two versions (`a`, then `b`) and their difference. */
export interface PairDifference {
  readonly originHub: string;
  readonly destinationHub: string;
  readonly meanPriceA: ResultNumber;
  readonly meanPriceB: ResultNumber;
  /** `b` minus `a`. */
  readonly priceDifference: ResultNumber;
  readonly travellersA: ResultNumber;
  readonly travellersB: ResultNumber;
  readonly travellersDifference: ResultNumber;
}

/** One hub's figures in the last two versions (`a`, then `b`); null where the hub has no value. */
export interface HubDifference {
  readonly hubId: string;
  readonly meanPriceA: ResultNumber | null;
  readonly meanPriceB: ResultNumber | null;
  readonly priceDifference: ResultNumber | null;
  /** The mean bike price in `b` minus `b`'s flat price per ride. */
  readonly priceBMinusFlat: ResultNumber | null;
  readonly ridesStartingA: ResultNumber | null;
  readonly ridesStartingB: ResultNumber | null;
  readonly ridesStartingDifference: ResultNumber | null;
}

export interface Comparison {
  readonly instanceVersion: { readonly id: string; readonly name: string };
  readonly period: { readonly id: string; readonly name: string };
  readonly versions: readonly ComparedVersion[];
  readonly flatReferences: readonly FlatReference[];
  readonly groups: readonly ComparisonGroup[];
  readonly identicalSolves: readonly (readonly string[])[];
  /** The hub pairs, largest absolute price difference first, between the last two versions. */
  readonly pairDifferences: {
    readonly a: string;
    readonly b: string;
    readonly pairs: readonly PairDifference[];
  };
  readonly hubDifferences: readonly HubDifference[];
}

export type ComparisonColumn =
  | { readonly kind: 'flat'; readonly reference: FlatReference }
  | { readonly kind: 'version'; readonly version: ComparedVersion };

/** Each flat column first, then the versions it serves (letter order); columns in the order of their first version. */
export function comparisonColumns(comparison: Comparison): readonly ComparisonColumn[] {
  return comparison.flatReferences.flatMap((reference) => [
    { kind: 'flat' as const, reference },
    ...comparison.versions
      .filter((version) => version.flatReference === reference.id)
      .map((version) => ({ kind: 'version' as const, version })),
  ]);
}

/**
 * The letters ticked when L-4 opens: the first four finished letters in letter order; the letter open
 * on L-3 takes the fourth place when it is not among them.
 */
export function initialLetters(
  finished: readonly string[],
  open: string | null,
): readonly string[] {
  const sorted = [...finished].sort();
  const first = sorted.slice(0, MAX_COMPARED);
  if (open === null || first.includes(open) || !sorted.includes(open)) return first;
  return [...first.slice(0, MAX_COMPARED - 1), open].sort();
}

/** The older rule of a compared version: the rule version of its first simulation that is not current. */
export function olderRuleOf(version: ComparedVersion): number | null {
  const older = version.simulations.find((item) => !item.ruleCurrent);
  return older === undefined ? null : older.ruleVersion;
}

/** The distinct package commits of the compared versions, in letter order, seven characters each. */
export function packageCommits(comparison: Comparison): readonly string[] {
  const found: string[] = [];
  for (const version of comparison.versions) {
    const commit = version.packageCommit?.slice(0, 7);
    if (commit !== undefined && commit !== '' && !found.includes(commit)) found.push(commit);
  }
  return found;
}

export const TOP_PAIRS = 10;

/** The hub pairs the difference table lists: the first `n` in the API's order (largest first). */
export function topPairDifferences(
  comparison: Comparison,
  n = TOP_PAIRS,
): readonly PairDifference[] {
  return comparison.pairDifferences.pairs.slice(0, n);
}

/**
 * Two versions with the same solve: the group holding both compared versions `a` and `b`
 * (`coversAB`), else the first two letters of the first group; null when no versions share a solve.
 */
export function identicalPair(
  comparison: Comparison,
): { readonly letters: readonly [string, string]; readonly coversAB: boolean } | null {
  const { a, b } = comparison.pairDifferences;
  const both = comparison.identicalSolves.find((group) => group.includes(a) && group.includes(b));
  if (both !== undefined) return { letters: [a, b], coversAB: true };
  const first = comparison.identicalSolves.find((group) => group.length >= 2);
  const [x, y] = first ?? [];
  return x === undefined || y === undefined ? null : { letters: [x, y], coversAB: false };
}
