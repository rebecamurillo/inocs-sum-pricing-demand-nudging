import { expect, type APIRequestContext } from '@playwright/test';

export type ComponentName = 'solver' | 'package' | 'trip_planner';
export type ComponentState = 'available' | 'limited' | 'unavailable';

interface StatusAnswer {
  components: { name: string; state: string }[];
}

// The worker reports every second on the e2e stack and beats every 5 s: a change written to
// `fake_settings`, or a reset that truncated `workers` and `component_reports`, reaches the
// status within that time.
const STATUS_TIMEOUT_MS = 15_000;

/** Client of `/api/test-control`, which the API mounts only with the fake adapters. */
export class TestControl {
  constructor(private readonly request: APIRequestContext) {}

  /** Empty the database and set every fake to available; returns once the status shows it. */
  async reset(): Promise<void> {
    await this.expectNoContent(await this.request.post('/api/test-control/reset'));
    await this.waitForStates((states) =>
      Object.values(states).every((state) => state === 'available'),
    );
  }

  async makeUnavailable(component: ComponentName, reason: string): Promise<void> {
    await this.setComponent(component, { state: 'unavailable', reason });
  }

  async makeLimited(component: 'solver', reason: string): Promise<void> {
    await this.setComponent(component, { state: 'limited', reason });
  }

  /** Write the answer, then wait until the status shows the component in that state. */
  async setComponent(
    component: ComponentName,
    answer: { state: ComponentState; reason: string | null },
  ): Promise<void> {
    const response = await this.request.put(`/api/test-control/components/${component}`, {
      data: answer,
    });
    await this.expectNoContent(response);
    await this.waitForStates((states) => states[component] === answer.state);
  }

  private async waitForStates(done: (states: Record<string, string>) => boolean): Promise<void> {
    await expect
      .poll(
        async () => {
          const response = await this.request.get('/api/v1/system-status');
          if (!response.ok()) return false;
          const status = (await response.json()) as StatusAnswer;
          return done(Object.fromEntries(status.components.map((c) => [c.name, c.state])));
        },
        { timeout: STATUS_TIMEOUT_MS, message: 'the system status shows the change' },
      )
      .toBe(true);
  }

  private async expectNoContent(response: Awaited<ReturnType<APIRequestContext['post']>>) {
    if (response.status() !== 204) {
      throw new Error(
        `Test control answered HTTP ${String(response.status())} for ${response.url()}: ${await response.text()}`,
      );
    }
  }
}
