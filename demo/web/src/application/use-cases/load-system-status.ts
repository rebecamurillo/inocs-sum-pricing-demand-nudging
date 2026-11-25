import type { SystemStatus } from '../../domain/system-status';
import type { SystemStatusGateway } from '../ports/system-status-gateway';

export function loadSystemStatus(gateway: SystemStatusGateway): Promise<SystemStatus> {
  return gateway.load();
}
