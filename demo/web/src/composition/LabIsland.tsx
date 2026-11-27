import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';
import { App } from '../presentation/components/App';
import { GatewaysProvider } from '../presentation/hooks/gateways';
import { MapFactoryProvider } from '../presentation/map/MapContext';
import { createGateways } from './gateways';
import { createMapLibreMap } from './map-factory';

// One island holds the providers and the app (Home or the Lab): React context does not cross the boundary
// between two Astro islands, so a provider cannot wrap the shell from the page.
export default function LabIsland() {
  const [gateways] = useState(createGateways);
  const [queryClient] = useState(() => new QueryClient());

  return (
    <QueryClientProvider client={queryClient}>
      <GatewaysProvider gateways={gateways}>
        <MapFactoryProvider factory={createMapLibreMap}>
          <App />
        </MapFactoryProvider>
      </GatewaysProvider>
    </QueryClientProvider>
  );
}
