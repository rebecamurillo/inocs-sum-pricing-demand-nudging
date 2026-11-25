import type { SystemStatus } from '../../domain/system-status';

export interface SystemStatusGateway {
  load(): Promise<SystemStatus>;
}
