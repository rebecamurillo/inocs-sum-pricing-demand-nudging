import type { APIRequestContext } from '@playwright/test';

export type ComponentName = 'pricing_model' | 'solver' | 'trip_planner';

/** Client of `/api/test-control`, which the API mounts only with the fake adapters. */
export class TestControl {
  constructor(private readonly request: APIRequestContext) {}

  async reset(): Promise<void> {
    await this.expectNoContent(await this.request.post('/api/test-control/reset'));
  }

  async makeUnavailable(component: ComponentName, reason: string): Promise<void> {
    await this.setComponent(component, { available: false, reason });
  }

  private async setComponent(
    component: ComponentName,
    answer: { available: boolean; reason: string | null },
  ): Promise<void> {
    const response = await this.request.put(`/api/test-control/components/${component}`, {
      data: answer,
    });
    await this.expectNoContent(response);
  }

  private async expectNoContent(response: Awaited<ReturnType<APIRequestContext['post']>>) {
    if (response.status() !== 204) {
      throw new Error(
        `Test control answered HTTP ${String(response.status())} for ${response.url()}: ${await response.text()}`,
      );
    }
  }
}
