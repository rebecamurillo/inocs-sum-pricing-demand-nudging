import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ApiProblemError } from '../../application/errors';
import type { SystemStatusGateway } from '../../application/ports/system-status-gateway';
import type { SystemStatus } from '../../domain/system-status';
import { GatewaysProvider } from '../hooks/gateways';
import { SystemStatusPanel } from './SystemStatusPanel';

const everythingAvailable: SystemStatus = {
  apiVersion: '0.1.0',
  components: [
    { name: 'storage', available: true, reason: null },
    { name: 'pricingModel', available: true, reason: null },
    { name: 'solver', available: true, reason: null },
    { name: 'tripPlanner', available: true, reason: null },
  ],
  canReadStoredResults: true,
  canStartRuns: true,
};

const solverMissing: SystemStatus = {
  ...everythingAvailable,
  components: [
    { name: 'storage', available: true, reason: null },
    { name: 'pricingModel', available: true, reason: null },
    { name: 'solver', available: false, reason: 'No Gurobi licence was found.' },
    { name: 'tripPlanner', available: true, reason: null },
  ],
  canStartRuns: false,
};

const twoMissing: SystemStatus = {
  ...everythingAvailable,
  components: [
    { name: 'storage', available: true, reason: null },
    { name: 'pricingModel', available: false, reason: 'Not installed.' },
    { name: 'solver', available: true, reason: null },
    { name: 'tripPlanner', available: false, reason: 'No answer from OpenTripPlanner.' },
  ],
  canStartRuns: false,
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

  it('shows one row per component with its availability', async () => {
    renderPanel({ load: () => Promise.resolve(solverMissing) });

    const rows = await screen.findAllByRole('listitem');
    const solverRow = rows.find((row) => within(row).queryByText('Solver') !== null);

    expect(screen.getByText('Storage')).toBeInTheDocument();
    expect(screen.getByText('Pricing model')).toBeInTheDocument();
    expect(screen.getByText('Trip planner')).toBeInTheDocument();
    expect(screen.getAllByText('Available')).toHaveLength(3);
    expect(solverRow).toBeDefined();
    expect(solverRow).toHaveTextContent('Unavailable');
    expect(solverRow).toHaveTextContent('No Gurobi licence was found.');
  });

  it('says that new runs can start when nothing blocks them', async () => {
    renderPanel({ load: () => Promise.resolve(everythingAvailable) });

    expect(await screen.findByText('New runs can start.')).toBeInTheDocument();
    expect(screen.queryByText(/cannot/)).not.toBeInTheDocument();
  });

  it('lists each blocking component by its label with its reason when new runs cannot start', async () => {
    renderPanel({ load: () => Promise.resolve(solverMissing) });

    expect(await screen.findByText('New runs cannot start:')).toBeInTheDocument();
    expect(screen.getAllByText('Solver: No Gurobi licence was found.')).toHaveLength(1);
    expect(screen.queryByText('New runs can start.')).not.toBeInTheDocument();
  });

  it('lists every blocking component in order and shows no identifier from the API', async () => {
    renderPanel({ load: () => Promise.resolve(twoMissing) });

    const blocking = await screen.findAllByText(/^(Pricing model|Trip planner): /);

    expect(blocking.map((item) => item.textContent)).toEqual([
      'Pricing model: Not installed.',
      'Trip planner: No answer from OpenTripPlanner.',
    ]);
    expect(screen.queryByText(/pricing_model|trip_planner|pricingModel|tripPlanner/)).toBeNull();
  });

  it('says that stored results cannot be read when the API reports so', async () => {
    renderPanel({
      load: () => Promise.resolve({ ...solverMissing, canReadStoredResults: false }),
    });

    expect(await screen.findByText('Stored results cannot be read.')).toBeInTheDocument();
  });

  it('does not mention stored results when they can be read', async () => {
    renderPanel({ load: () => Promise.resolve(everythingAvailable) });

    await screen.findByText('New runs can start.');

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

    expect(await screen.findByText('New runs can start.')).toBeInTheDocument();
    expect(load).toHaveBeenCalledTimes(2);
  });
});
