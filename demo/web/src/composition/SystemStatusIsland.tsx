import { useState } from 'react';
import { SystemStatusPanel } from '../presentation/components/SystemStatusPanel';
import { GatewaysProvider } from '../presentation/hooks/gateways';
import { createGateways } from './gateways';

// One island holds the provider and the panel: React context does not cross the boundary
// between two Astro islands, so the provider cannot wrap the panel from the page.
export default function SystemStatusIsland() {
  const [gateways] = useState(createGateways);

  return (
    <GatewaysProvider gateways={gateways}>
      <SystemStatusPanel />
    </GatewaysProvider>
  );
}
