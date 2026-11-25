import { createContext, useContext, type ReactNode } from 'react';
import type { Gateways } from '../../application/ports/gateways';

const GatewaysContext = createContext<Gateways | null>(null);

interface GatewaysProviderProps {
  gateways: Gateways;
  children: ReactNode;
}

/**
 * Hands the gateways to the components below. The composition root builds the real ones;
 * tests pass fakes. The context lives here because `presentation` may not import `composition`.
 */
export function GatewaysProvider({ gateways, children }: GatewaysProviderProps) {
  return <GatewaysContext.Provider value={gateways}>{children}</GatewaysContext.Provider>;
}

export function useGateways(): Gateways {
  const gateways = useContext(GatewaysContext);
  if (gateways === null) {
    throw new Error('useGateways must be called below a GatewaysProvider.');
  }
  return gateways;
}
