import { useQuery } from '@tanstack/react-query';
import { loadMapBasis } from '../../application/use-cases/load-map-basis';
import { useGateways } from './gateways';

/** The data set the map shows and its basemap file, read once through the use case. */
export function useMapBasis(datasetId: string | null) {
  const { cityDatasets, basemap } = useGateways();
  return useQuery({
    queryKey: ['map-basis', datasetId],
    queryFn: () => loadMapBasis({ cityDatasets, basemap }, datasetId),
    staleTime: Infinity,
    retry: false,
  });
}
