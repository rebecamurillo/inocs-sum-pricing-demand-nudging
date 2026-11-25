import { afterEach, describe, expect, it, vi } from 'vitest';
import { browserFetch } from './browser-fetch';

describe('browserFetch', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('hands its arguments to the global fetch and returns its answer', async () => {
    const answer = new Response('ok');
    const globalFetch = vi.fn<typeof fetch>(() => Promise.resolve(answer));
    vi.stubGlobal('fetch', globalFetch);

    const result = await browserFetch('/api/v1/system-status', { method: 'GET' });

    expect(result).toBe(answer);
    expect(globalFetch).toHaveBeenCalledWith('/api/v1/system-status', { method: 'GET' });
  });
});
