/** Every wording of the Advanced view of L-3 (UX-SPEC § L-3 item 7) and the formatting behind it. */
import { formatDate, groupThousands, longDate } from './l1-text';
import {
  BALANCE_FIELD,
  COST_FIELD,
  KEPT_FIELDS,
  LOWEST_FIELD,
  RIDERSHIP_FIELD,
  type GoalField,
} from './pricing-goals-text';
import type {
  ResultNumber,
  ResultProvenance,
  SimulationOutcome,
  StoredSimulation,
} from './pricing-result';
import { COMPUTED_LABEL } from './result-text';

interface Advanced {
  readonly solverStatusName: string;
  readonly numbers: Readonly<Record<string, ResultNumber>>;
}

export const ADVANCED_TITLE = 'Advanced view';
export const OBJECTIVE_HEADING = 'What the solver maximised';
export const SOLVER_HEADING = 'Solver';
export const SIMULATION_HEADING = 'Traveller simulation';
export const PACKAGE_SUMMARY_HEADING = "The package's own summary (optimizer/metrics.py)";
export const PARAMETERS_HEADING = 'Parameters used';
export const COEFFICIENTS_HEADING = 'Choice-model coefficients';
export const ABOUT_HEADING = 'About this result';
export const EARLIER_HEADING = 'Earlier simulations of this version';
export const BIKE_RIDE_SENTENCE =
  'A bike ride is one bike leg; an option with two bike legs counts two rides';
export const COMPUTED_FROM_FLOWS = COMPUTED_LABEL;
export const NOT_RECORDED = 'not recorded';
const DASH = '—';

export interface AdvancedRow {
  readonly label: string;
  readonly value: string;
  /** The label is a package name, shown in monospace. */
  readonly code?: boolean;
  /** The blue tag of the pricing model's own result. */
  readonly tag?: 'model';
}

/** The solver's status in plain words; a status that is a limit is never worded with that word. */
export function solverStatusText(name: string): string {
  if (name === 'OPTIMAL') return 'optimal';
  if (name === 'SUBOPTIMAL') return 'suboptimal';
  if (name === 'TIME_LIMIT') return 'stopped with a solution';
  return name.toLowerCase().replaceAll('_', ' ');
}

export function licenceText(kind: string): string {
  return kind === 'full' ? 'full licence' : 'size-limited licence';
}

const whole = (value: number): string => groupThousands(Math.round(value));
const value = (advanced: Advanced, name: string): number | null =>
  advanced.numbers[name]?.value ?? null;

const TERMS: readonly (readonly [string, string])[] = [
  ['objective_term_ridership', 'Ridership term'],
  ['objective_term_revenue', '+ Revenue'],
  ['objective_term_cost', '− Cost'],
  ['objective_term_station_balance', '+ Station balance term'],
];

/** The terms the solver's objective is made of, each present only when the residual check passed. */
export function objectiveRows(advanced: Advanced): AdvancedRow[] {
  const terms = TERMS.flatMap(([name, label]) => {
    const found = value(advanced, name);
    return found === null ? [] : [{ label, value: whole(found) }];
  });
  const total = value(advanced, 'objective_value');
  return [
    ...terms,
    {
      label: '= Objective value',
      value: total === null ? DASH : whole(total),
      tag: 'model' as const,
    },
  ];
}

/** True when the rows carry the four terms (so the "computed from the model's flows" label applies). */
export const hasObjectiveTerms = (rows: readonly AdvancedRow[]): boolean => rows.length > 1;

export function solverRows(
  advanced: Advanced,
  hubPairs: number | null,
  bikeOptions: number | null,
): AdvancedRow[] {
  const time = value(advanced, 'solution_time_s');
  const gap = value(advanced, 'gap_pct');
  const stopped = value(advanced, 'time_limit_reached');
  return [
    { label: 'Solution time', value: time === null ? DASH : `${time.toFixed(1)} s` },
    { label: 'Optimality gap', value: gap === null ? DASH : `${gap.toFixed(2)} %` },
    { label: 'Status', value: solverStatusText(advanced.solverStatusName) },
    {
      label: 'Hub pairs · bike options offered',
      value:
        hubPairs === null || bikeOptions === null
          ? DASH
          : `${groupThousands(hubPairs)} · ${groupThousands(bikeOptions)}`,
    },
    {
      label: 'Stopped before the search ended',
      value: stopped === null ? DASH : stopped === 1 ? 'yes' : 'no',
    },
  ];
}

const weight = (parameters: Readonly<Record<string, number>>, name: string): string => {
  const found = parameters[name];
  return found === undefined ? DASH : String(found);
};

function ruleText(
  ruleId: string,
  ruleVersion: number,
  parameters: Readonly<Record<string, number>>,
): string {
  return `${ruleId} v${String(ruleVersion)} · price weight ${weight(parameters, 'price_weight')} · time weight ${weight(parameters, 'time_weight')} · placeholder`;
}

export const ruleLine = (simulation: SimulationOutcome): string =>
  `Rule: ${ruleText(simulation.ruleId, simulation.ruleVersion, simulation.ruleParameters)}`;

export function simulationRows(
  modelPrices: SimulationOutcome,
  flat: SimulationOutcome,
): AdvancedRow[] {
  const both = 'with these prices / with the flat price';
  const profit = (item: SimulationOutcome) => whole(item.revenue.value - item.cost.value);
  const left = (item: SimulationOutcome) => `${whole(item.displaced)} · ${whole(item.unserved)}`;
  return [
    {
      label: `Bike rides · ${both}`,
      value: `${whole(modelPrices.bikeRides.value)} / ${whole(flat.bikeRides.value)}`,
    },
    {
      label: `Revenue − cost · ${both}`,
      value: `${profit(modelPrices)} / ${profit(flat)}`,
    },
    {
      label: `Did not get their first choice · left with no option · ${both}`,
      value: `${left(modelPrices)} / ${left(flat)}`,
    },
  ];
}

const dayOf = (instant: string): string => formatDate(instant.slice(0, 10));

/** The stored simulations of a rule that is not the current one, one line each. */
export function earlierSimulations(stored: readonly StoredSimulation[]): string[] {
  return stored
    .filter((item) => !item.ruleCurrent)
    .map(
      (item) =>
        `${ruleText(item.ruleId, item.ruleVersion, item.ruleParameters)} · ${
          item.priceScheme === 'flat' ? 'with the flat price' : 'with these prices'
        } · ${dayOf(item.createdAt)}`,
    );
}

export function packageSummaryRows(advanced: Advanced): AdvancedRow[] {
  const price = (name: string) => {
    const found = value(advanced, name);
    return found === null ? DASH : `${found.toFixed(2)} CHF`;
  };
  return [
    {
      label: 'Avg Bike Price (Multimodal, Flow ≥ 1)',
      value: price('package_avg_bike_price_multimodal'),
    },
    {
      label: 'Avg Bike Price (for all offered arcs)',
      value: price('package_avg_bike_price_offered'),
    },
  ];
}

const PARAMETER_FIELDS: readonly GoalField[] = [
  COST_FIELD,
  LOWEST_FIELD,
  RIDERSHIP_FIELD,
  BALANCE_FIELD,
  ...KEPT_FIELDS.filter((field) => field.packageName !== null),
];

export function parameterRows(advanced: Advanced, flatPrice: number): AdvancedRow[] {
  return [
    ...PARAMETER_FIELDS.map((field) => {
      const name = field.packageName ?? '';
      const found = value(advanced, `parameter_${name}`);
      return {
        label: name,
        value: found === null ? DASH : found.toFixed(field.digits),
        code: true,
      };
    }),
    {
      label: 'Flat price for the comparison',
      value: `${flatPrice.toFixed(2)} CHF per ride · traveller simulation only`,
    },
  ];
}

export function coefficientsText(
  coefficients: Readonly<Record<string, ResultNumber | null>> | null,
): string {
  return coefficients === null
    ? 'Fixed inside the model, not exposed by the package.'
    : 'Read from the package source (optimizer/solver.py), fixed inside the model';
}

export function coefficientRows(
  coefficients: Readonly<Record<string, ResultNumber | null>>,
): AdvancedRow[] {
  return Object.entries(coefficients).map(([name, found]) => ({
    label: name,
    value: found === null ? 'not found' : String(found.value),
    code: true,
  }));
}

const or = (text: string | null): string => text ?? NOT_RECORDED;

function hostOf(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

export function aboutRows(provenance: ResultProvenance, solverStatusName: string): AdvancedRow[] {
  // Compared as instants: the API leaves out a zero fraction of a second, so the text does not sort.
  const latest = [...provenance.simulations].sort(
    (a, b) => Date.parse(b.createdAt) - Date.parse(a.createdAt),
  )[0];
  const routes =
    provenance.routingDate === null
      ? NOT_RECORDED
      : `${longDate(provenance.routingDate)}, arrive by ${(provenance.routingTime ?? '').slice(0, 5) || NOT_RECORDED}${
          provenance.routingDateProvisional === true ? ' · provisional' : ''
        }`;
  return [
    {
      label: 'Pricing model',
      value: `package ${or(provenance.packageVersion)} · commit ${
        provenance.packageCommit === null ? NOT_RECORDED : provenance.packageCommit.slice(0, 7)
      }`,
    },
    {
      label: 'Solver',
      value: `Gurobi ${provenance.gurobiVersion} · ${licenceText(provenance.licenceKind)} · status ${solverStatusText(solverStatusName)}`,
    },
    {
      label: 'Timetable',
      value: `${or(provenance.timetableOperator)} · valid ${
        provenance.timetableValidFrom === null
          ? NOT_RECORDED
          : formatDate(provenance.timetableValidFrom)
      } to ${
        provenance.timetableValidTo === null
          ? NOT_RECORDED
          : formatDate(provenance.timetableValidTo)
      } · routes planned for ${routes}`,
    },
    {
      label: 'Bike stations',
      value: `${provenance.bikeStationsSourceUrl === null ? NOT_RECORDED : hostOf(provenance.bikeStationsSourceUrl)} · fetched ${
        provenance.bikeStationsFetchedAt === null
          ? NOT_RECORDED
          : dayOf(provenance.bikeStationsFetchedAt)
      }`,
    },
    {
      label: 'Simulation',
      value:
        latest === undefined
          ? NOT_RECORDED
          : `${latest.ruleId} v${String(latest.ruleVersion)} · ${dayOf(latest.createdAt)}`,
    },
    { label: 'Demonstrator', value: provenance.demonstratorVersion },
  ];
}
