import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ApiProblemError } from '../../application/errors';
import type { SystemStatusGateway } from '../../application/ports/system-status-gateway';
import type { ComponentStatus, SystemStatus, Verdict } from '../../domain/system-status';
import { GatewaysProvider } from '../hooks/gateways';
import { SystemStatusPanel } from './SystemStatusPanel';

const allowed: Verdict = { allowed: true, reasons: [] };

const everythingAvailable: SystemStatus = {
  components: [
    { name: 'storage', state: 'available', reason: null },
    { name: 'runner', state: 'available', reason: null },
    { name: 'solver', state: 'available', reason: null },
    { name: 'package', state: 'available', reason: null },
    { name: 'tripPlanner', state: 'available', reason: null },
  ],
  canBuildInstances: allowed,
  canRunPricing: allowed,
  canSimulate: allowed,
};

function withComponent(component: ComponentStatus): SystemStatus['components'] {
  return everythingAvailable.components.map((item) =>
    item.name === component.name ? component : item,
  );
}

const solverLimited: SystemStatus = {
  ...everythingAvailable,
  components: withComponent({
    name: 'solver',
    state: 'limited',
    reason: 'Size-limited Gurobi licence.',
  }),
  canRunPricing: {
    allowed: false,
    reasons: [{ component: 'solver', reason: 'Size-limited Gurobi licence.' }],
  },
};

const tripPlannerDown: SystemStatus = {
  ...everythingAvailable,
  components: withComponent({
    name: 'tripPlanner',
    state: 'unavailable',
    reason: 'No answer from OpenTripPlanner.',
  }),
  canBuildInstances: {
    allowed: false,
    reasons: [{ component: 'tripPlanner', reason: 'No answer from OpenTripPlanner.' }],
  },
};

const runnerDown: SystemStatus = {
  ...everythingAvailable,
  components: withComponent({
    name: 'runner',
    state: 'unavailable',
    reason: 'No runner has reported in the last 30 s.',
  }),
  canBuildInstances: {
    allowed: false,
    reasons: [{ component: 'runner', reason: 'No runner has reported in the last 30 s.' }],
  },
  canRunPricing: {
    allowed: false,
    reasons: [{ component: 'runner', reason: 'No runner has reported in the last 30 s.' }],
  },
  canSimulate: {
    allowed: false,
    reasons: [{ component: 'runner', reason: 'No runner has reported in the last 30 s.' }],
  },
};

const unreachable = new ApiProblemError({
  code: 'api_unreachable',
  title: 'The API could not be reached',
  detail: 'Failed to fetch',
});

function renderPanel(gateway: SystemStatusGateway) {
  return render(
    <GatewaysProvider gateways={{ systemStatus: gateway }}>
      <SystemStatusPanel />
    </GatewaysProvider>,
  );
}

describe('SystemStatusPanel', () => {
  it('says it is reading the status while the API has not answered', () => {
    renderPanel({ load: () => new Promise<SystemStatus>(() => undefined) });

    expect(screen.getByRole('status')).toHaveTextContent('Reading the system status.');
  });

  it('shows five rows with their state and reason', async () => {
    renderPanel({ load: () => Promise.resolve(solverLimited) });

    const rows = await screen.findAllByRole('listitem');
    const rowOf = (label: string) => rows.find((row) => within(row).queryByText(label) !== null);

    for (const label of ['Storage', 'Runner', 'Solver', 'Pricing package', 'Trip planner']) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getAllByText('Available')).toHaveLength(4);
    expect(rowOf('Solver')).toHaveTextContent('Limited');
    expect(rowOf('Solver')).toHaveTextContent('Size-limited Gurobi licence.');
  });

  it('says each action can start when nothing blocks it', async () => {
    renderPanel({ load: () => Promise.resolve(everythingAvailable) });

    expect(await screen.findByText('Instance builds can start.')).toBeInTheDocument();
    expect(screen.getByText('Pricing runs can start.')).toBeInTheDocument();
    expect(screen.getByText('Simulations can start.')).toBeInTheDocument();
    expect(screen.queryByText(/cannot/)).not.toBeInTheDocument();
  });

  it('refuses builds only, with the trip planner and its reason', async () => {
    renderPanel({ load: () => Promise.resolve(tripPlannerDown) });

    expect(await screen.findByText('Instance builds cannot start:')).toBeInTheDocument();
    expect(screen.getByText('Trip planner: No answer from OpenTripPlanner.')).toBeInTheDocument();
    expect(screen.getByText('Pricing runs can start.')).toBeInTheDocument();
    expect(screen.getByText('Simulations can start.')).toBeInTheDocument();
  });

  it('refuses pricing runs only when the solver is limited', async () => {
    renderPanel({ load: () => Promise.resolve(solverLimited) });

    expect(await screen.findByText('Pricing runs cannot start:')).toBeInTheDocument();
    expect(screen.getByText('Solver: Size-limited Gurobi licence.')).toBeInTheDocument();
    expect(screen.getByText('Instance builds can start.')).toBeInTheDocument();
    expect(screen.getByText('Simulations can start.')).toBeInTheDocument();
  });

  it('lists the blocking component under each refused action and shows no identifier', async () => {
    renderPanel({ load: () => Promise.resolve(runnerDown) });

    const blocking = await screen.findAllByText('Runner: No runner has reported in the last 30 s.');

    expect(blocking).toHaveLength(3);
    expect(screen.getByText('Simulations cannot start:')).toBeInTheDocument();
    expect(screen.queryByText(/trip_planner|tripPlanner/)).toBeNull();
  });

  it('does not mention stored results', async () => {
    renderPanel({ load: () => Promise.resolve(everythingAvailable) });

    await screen.findByText('Simulations can start.');

    expect(screen.queryByText(/Stored results/)).not.toBeInTheDocument();
  });

  it('states what failed and the reason, with a way to try again', async () => {
    renderPanel({ load: () => Promise.reject(unreachable) });

    const alert = await screen.findByRole('alert');

    expect(alert).toHaveTextContent('The system status could not be read.');
    expect(alert).toHaveTextContent('The API could not be reached.');
    expect(alert).toHaveTextContent('Failed to fetch');
    expect(within(alert).getByRole('button', { name: 'Try again' })).toBeEnabled();
  });

  it('states the reason of a failure that is not an API problem', async () => {
    renderPanel({ load: () => Promise.reject(new Error('Something broke')) });

    const alert = await screen.findByRole('alert');

    expect(alert).toHaveTextContent('Something broke');
  });

  it('loads again when "Try again" is pressed and shows the new answer', async () => {
    const load = vi
      .fn<SystemStatusGateway['load']>()
      .mockRejectedValueOnce(unreachable)
      .mockResolvedValueOnce(everythingAvailable);
    renderPanel({ load });

    await userEvent.click(await screen.findByRole('button', { name: 'Try again' }));

    expect(await screen.findByText('Simulations can start.')).toBeInTheDocument();
    expect(load).toHaveBeenCalledTimes(2);
  });
});
