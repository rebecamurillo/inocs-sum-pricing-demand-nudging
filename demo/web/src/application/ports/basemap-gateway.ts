export interface BasemapGateway {
  /** Whether the basemap file of this data set is served. A network error is "no". */
  exists(datasetId: string): Promise<boolean>;
  /** Where the basemap file of this data set is served, on the page's own origin. */
  url(datasetId: string): string;
}
