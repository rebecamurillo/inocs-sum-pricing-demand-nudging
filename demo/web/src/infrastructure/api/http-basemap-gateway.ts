import type { BasemapGateway } from '../../application/ports/basemap-gateway';

export class HttpBasemapGateway implements BasemapGateway {
  private readonly fetchImpl: typeof fetch;

  constructor(fetchImpl: typeof fetch) {
    this.fetchImpl = fetchImpl;
  }

  url(datasetId: string): string {
    return `/basemap/${datasetId}.pmtiles`;
  }

  async exists(datasetId: string): Promise<boolean> {
    try {
      const response = await this.fetchImpl(this.url(datasetId), { method: 'HEAD' });
      return response.status === 200;
    } catch {
      return false;
    }
  }
}
