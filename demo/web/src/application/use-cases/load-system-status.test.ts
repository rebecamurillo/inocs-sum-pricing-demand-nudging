import { describe, expect, it } from 'vitest';
import type { SystemStatus } from '../../domain/system-status';
import { ApiProblemError } from '../errors';
import type { SystemStatusGateway } from '../ports/system-status-gateway';
import { loadSystemStatus } from './load-system-status';

const status: SystemStatus = {
  apiVersion: '0.1.0',
  components: [{ name: 'storage', available: true, reason: null }],
  canReadStoredResults: true,
  canStartRuns: true,
};

describe('loadSystemStatus', () => {
  it('returns the status the gateway loads', async () => {
    const gateway: SystemStatusGateway = { load: () => Promise.resolve(status) };

    await expect(loadSystemStatus(gateway)).resolves.toBe(status);
  });

  it('lets the gateway failure reach the caller unchanged', async () => {
    const failure = new ApiProblemError({
      code: 'api_unreachable',
      title: 'The API could not be reached',
      detail: 'Failed to fetch',
    });
    const gateway: SystemStatusGateway = { load: () => Promise.reject(failure) };

    await expect(loadSystemStatus(gateway)).rejects.toBe(failure);
  });
});
