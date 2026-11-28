import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { expect, type APIRequestContext } from '@playwright/test';

const run = promisify(execFile);

// A restarted worker reports its first cycle within a few seconds; the API answers once it is up.
const BACK_TIMEOUT_MS = 90_000;

interface StatusAnswer {
  components: { name: string; state: string }[];
}

/**
 * Restart the e2e stack's `api` and `worker` services with the compose command `make e2e` runs
 * (exported as `E2E_COMPOSE`, with an absolute file path), then wait until the API answers the
 * system status and the runner is available again. The database is not restarted: what the
 * services read afterwards is what PostgreSQL kept.
 */
export async function restartApiAndWorker(request: APIRequestContext): Promise<void> {
  const command = process.env.E2E_COMPOSE;
  if (!command) {
    throw new Error('E2E_COMPOSE is not set: run the scenarios through `make e2e`.');
  }
  const [program, ...args] = command.split(' ').filter((part) => part !== '');
  if (program === undefined) {
    throw new Error('E2E_COMPOSE is empty.');
  }
  await run(program, [...args, 'restart', 'api', 'worker']);
  await expect
    .poll(
      async () => {
        try {
          const response = await request.get('/api/v1/system-status');
          if (response.status() !== 200) return false;
          const status = (await response.json()) as StatusAnswer;
          return status.components.find((entry) => entry.name === 'runner')?.state === 'available';
        } catch {
          // The web server answers a connection error while the API container restarts.
          return false;
        }
      },
      { timeout: BACK_TIMEOUT_MS, message: 'the API and the worker are back' },
    )
    .toBe(true);
}
