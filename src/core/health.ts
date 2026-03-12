import { resolve } from 'node:path';
import { getComposeStatus } from '../services/docker.ts';
import {
  COMPOSE_FILE_NAME,
  COMPOSE_PROJECT_NAME,
  HEALTH_CHECK_INTERVAL_MS,
  HEALTH_CHECK_TIMEOUT_MS,
} from '../types/constants.ts';

/** 健康检查结果 */
export interface HealthCheckResult {
  allHealthy: boolean;
  services: ServiceHealth[];
  elapsed: number;
  timedOut: boolean;
}

export interface ServiceHealth {
  name: string;
  state: string;
  healthy: boolean;
}

/**
 * 轮询等待所有服务就绪
 * @param deployDir 部署目录
 * @param onTick 每次轮询的回调，返回当前状态
 */
export async function waitForHealthy(
  deployDir: string,
  onTick?: (services: ServiceHealth[], elapsed: number) => void,
): Promise<HealthCheckResult> {
  const composeFile = resolve(deployDir, COMPOSE_FILE_NAME);
  const startTime = Date.now();

  while (true) {
    const elapsed = Date.now() - startTime;

    // 超时检查
    if (elapsed >= HEALTH_CHECK_TIMEOUT_MS) {
      const statuses = await getComposeStatus(composeFile, COMPOSE_PROJECT_NAME);
      return {
        allHealthy: false,
        services: statuses.map((s) => ({
          name: s.name,
          state: s.state,
          healthy: s.state === 'running' && (s.health === 'healthy' || s.health === ''),
        })),
        elapsed,
        timedOut: true,
      };
    }

    const statuses = await getComposeStatus(composeFile, COMPOSE_PROJECT_NAME);

    const services: ServiceHealth[] = statuses.map((s) => ({
      name: s.name,
      state: s.state,
      // 容器 running 且健康（或无健康检查定义时 health 为空）视为就绪
      healthy: s.state === 'running' && (s.health === 'healthy' || s.health === ''),
    }));

    onTick?.(services, elapsed);

    // 所有服务就绪（且至少有一个服务）
    if (services.length > 0 && services.every((s) => s.healthy)) {
      return {
        allHealthy: true,
        services,
        elapsed,
        timedOut: false,
      };
    }

    // 检查是否有容器退出
    const exited = services.filter((s) => s.state === 'exited' || s.state === 'dead');
    if (exited.length > 0) {
      return {
        allHealthy: false,
        services,
        elapsed,
        timedOut: false,
      };
    }

    // 等待下一次轮询
    await Bun.sleep(HEALTH_CHECK_INTERVAL_MS);
  }
}
