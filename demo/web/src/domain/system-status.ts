export type ComponentName =
  'storage' | 'runner' | 'solver' | 'package' | 'tripPlanner' | 'cityData';

export type ComponentState = 'available' | 'limited' | 'unavailable';

export interface ComponentStatus {
  readonly name: ComponentName;
  readonly state: ComponentState;
  /** Why the component is limited or unavailable; null when it is available. */
  readonly reason: string | null;
}

/** An action the Lab can start or refuse, with the components that refuse it. */
export interface Verdict {
  readonly allowed: boolean;
  readonly reasons: readonly { readonly component: ComponentName; readonly reason: string }[];
}

export interface SystemStatus {
  readonly components: readonly ComponentStatus[];
  readonly canBuildInstances: Verdict;
  readonly canRunPricing: Verdict;
  readonly canSimulate: Verdict;
}

const labels: Readonly<Record<ComponentName, string>> = {
  storage: 'Storage',
  runner: 'Runner',
  solver: 'Solver',
  package: 'Pricing package',
  tripPlanner: 'Trip planner',
  cityData: 'City data',
};

const stateLabels: Readonly<Record<ComponentState, string>> = {
  available: 'Available',
  limited: 'Limited',
  unavailable: 'Unavailable',
};

export function componentLabel(name: ComponentName): string {
  return labels[name];
}

export function stateLabel(state: ComponentState): string {
  return stateLabels[state];
}
