import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';
import { LabShell } from '../presentation/components/LabShell';
import { GatewaysProvider } from '../presentation/hooks/gateways';
import { createGateways } from './gateways';

// One island holds the providers and the shell: React context does not cross the boundary
// between two Astro islands, so a provider cannot wrap the shell from the page.
export default function LabIsland() {
  const [gateways] = useState(createGateways);
  const [queryClient] = useState(() => new QueryClient());

  return (
    <QueryClientProvider client={queryClient}>
      <GatewaysProvider gateways={gateways}>
        <LabShell />
      </GatewaysProvider>
    </QueryClientProvider>
  );
}
