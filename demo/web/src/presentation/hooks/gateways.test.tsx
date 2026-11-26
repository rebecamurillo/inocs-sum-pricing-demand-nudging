import { render, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { Gateways } from '../../application/ports/gateways';
import { GatewaysProvider, useGateways } from './gateways';

const gateways: Gateways = {
  systemStatus: { load: () => Promise.reject(new Error('not called')) },
  layoutPreferences: {
    load: () => {
      throw new Error('not called');
    },
    save: () => {
      throw new Error('not called');
    },
  },
};

describe('useGateways', () => {
  it('returns the gateways the provider holds', () => {
    const { result } = renderHook(() => useGateways(), {
      wrapper: ({ children }) => (
        <GatewaysProvider gateways={gateways}>{children}</GatewaysProvider>
      ),
    });

    expect(result.current).toBe(gateways);
  });

  it('fails with an explanation when no provider is above the component', () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    function Probe() {
      useGateways();
      return null;
    }

    expect(() => render(<Probe />)).toThrow('useGateways must be called below a GatewaysProvider.');
    error.mockRestore();
  });
});
