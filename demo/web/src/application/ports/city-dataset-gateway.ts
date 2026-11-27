import type { CityDataset } from '../../domain/map';

export interface CityDatasetGateway {
  /** Every imported data set, oldest first. */
  list(): Promise<CityDataset[]>;
}
