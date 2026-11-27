import { describe, expect, it, vi } from 'vitest';
import { HttpBasemapGateway } from './http-basemap-gateway';

describe('HttpBasemapGateway', () => {
  it('names the file by data set, on the page origin', () => {
    expect(new HttpBasemapGateway(vi.fn()).url('d1')).toBe('/basemap/d1.pmtiles');
  });

  it('sends HEAD and is true on 200', async () => {
    const fetchFake = vi.fn<typeof fetch>(() => Promise.resolve(new Response(null)));

    expect(await new HttpBasemapGateway(fetchFake).exists('d1')).toBe(true);
    expect(fetchFake).toHaveBeenCalledWith('/basemap/d1.pmtiles', { method: 'HEAD' });
  });

  it('is false on 404', async () => {
    const fetchFake = vi.fn<typeof fetch>(() =>
      Promise.resolve(new Response(null, { status: 404 })),
    );

    expect(await new HttpBasemapGateway(fetchFake).exists('d1')).toBe(false);
  });

  it('is false on a network error', async () => {
    const fetchFake = vi.fn<typeof fetch>(() => Promise.reject(new Error('offline')));

    expect(await new HttpBasemapGateway(fetchFake).exists('d1')).toBe(false);
  });
});
