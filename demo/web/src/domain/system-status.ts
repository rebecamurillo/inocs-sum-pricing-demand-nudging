export type ComponentName = 'storage' | 'pricingModel' | 'solver' | 'tripPlanner';

export interface ComponentStatus {
  readonly name: ComponentName;
  readonly available: boolean;
  /** Why the component is unavailable; null when it is available. */
  readonly reason: string | null;
}

export interface SystemStatus {
  readonly apiVersion: string;
  readonly components: readonly ComponentStatus[];
  readonly canReadStoredResults: boolean;
  readonly canStartRuns: boolean;
}

const labels: Readonly<Record<ComponentName, string>> = {
  storage: 'Storage',
  pricingModel: 'Pricing model',
  solver: 'Solver',
  tripPlanner: 'Trip planner',
};

export function componentLabel(name: ComponentName): string {
  return labels[name];
}

/** The unavailable components, in report order: what prevents new runs from starting. */
export function blockingComponents(status: SystemStatus): readonly ComponentStatus[] {
  return status.components.filter((component) => !component.available);
}
