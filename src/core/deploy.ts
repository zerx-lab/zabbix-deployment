import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { generateComposeYaml } from '../config/compose-generator.ts';
import { composeUp } from '../services/docker.ts';
import { checkDocker, checkDockerCompose } from '../services/docker.ts';
import type { LoadResult } from '../services/image.ts';
import { loadAllImages } from '../services/image.ts';
import { postInitZabbix, waitForZabbixApi } from '../services/zabbix-api.ts';
import type { PostInitResult } from '../services/zabbix-api.ts';
import type { DeployConfig, DeployOptions } from '../types/config.ts';
import { COMPOSE_FILE_NAME, COMPOSE_PROJECT_NAME, SNMP_TRAPS_IMAGE } from '../types/constants.ts';
import { getPackagesDir } from '../utils/paths.ts';
import type { HealthCheckResult, ServiceHealth } from './health.ts';
import { waitForHealthy } from './health.ts';

/** 部署步骤枚举 */
export type DeployStep =
  | 'preflight'
  | 'load-images'
  | 'generate-compose'
  | 'create-dir'
  | 'start-services'
  | 'health-check'
  | 'post-init';

/** 部署结果 */
export interface DeployResult {
  success: boolean;
  /** 健康检查结果（仅启动成功后有值） */
  healthCheck?: HealthCheckResult;
  /** 部署后初始化结果（仅健康检查通过后有值） */
  postInit?: PostInitResult;
}

/** 部署进度回调 */
export interface DeployCallbacks {
  onStepStart?: (step: DeployStep, message: string) => void;
  onStepDone?: (step: DeployStep, message: string) => void;
  onStepError?: (step: DeployStep, error: string) => void;
  onImageProgress?: (result: LoadResult, index: number, total: number) => void;
  /** 健康检查轮询回调 */
  onHealthTick?: (services: ServiceHealth[], elapsed: number) => void;
}

/**
 * 执行部署前的环境检查
 */
export async function preflightCheck(): Promise<boolean> {
  const dockerOk = await checkDocker();
  if (!dockerOk) return false;

  const composeOk = await checkDockerCompose();
  if (!composeOk) return false;

  return true;
}

/**
 * 执行健康检查步骤：等待所有容器就绪
 */
async function runHealthCheck(
  deployDir: string,
  callbacks?: DeployCallbacks,
): Promise<{ ok: boolean; result: HealthCheckResult }> {
  callbacks?.onStepStart?.('health-check', '等待服务就绪（最长 3 分钟）...');
  const healthResult = await waitForHealthy(deployDir, callbacks?.onHealthTick);

  if (!healthResult.allHealthy) {
    const failedServices = healthResult.services
      .filter((s) => !s.healthy)
      .map((s) => `${s.name}(${s.state})`)
      .join(', ');
    const reason = healthResult.timedOut ? '健康检查超时' : '部分服务异常';
    callbacks?.onStepError?.('health-check', `${reason}: ${failedServices}`);
    return { ok: false, result: healthResult };
  }

  const elapsedSec = Math.floor(healthResult.elapsed / 1000);
  callbacks?.onStepDone?.('health-check', `所有服务已就绪（耗时 ${elapsedSec} 秒）`);
  return { ok: true, result: healthResult };
}

/**
 * 执行部署后初始化：等待 Zabbix API 就绪，修正 Agent 接口地址
 */
async function runPostInit(
  webPort: number,
  callbacks?: DeployCallbacks,
): Promise<PostInitResult | undefined> {
  callbacks?.onStepStart?.('post-init', '等待 Zabbix API 就绪（首次部署可能需要 3-5 分钟）...');

  const apiUrl = await waitForZabbixApi(webPort);
  if (!apiUrl) {
    callbacks?.onStepError?.(
      'post-init',
      'Zabbix API 未就绪（超时 5 分钟），请稍后手动修改默认主机 Agent 接口地址为 "zabbix-agent"',
    );
    return undefined;
  }

  const result = await postInitZabbix(apiUrl);
  if (!result.success) {
    callbacks?.onStepError?.(
      'post-init',
      `自动配置失败: ${result.error}，请手动修改默认主机 Agent 接口地址`,
    );
    return result;
  }

  if (result.agentInterfaceFixed) {
    callbacks?.onStepDone?.('post-init', '已自动修正 Agent 接口地址为容器名 "zabbix-agent"');
  } else {
    callbacks?.onStepDone?.('post-init', 'Agent 接口配置正常，无需修正');
  }

  return result;
}

/**
 * 执行 Zabbix 完整部署流程
 *
 * 包含 7 个步骤：
 * 1. preflight — 环境预检（Docker/Compose 可用性）
 * 2. load-images — 加载离线镜像
 * 3. create-dir — 创建部署目录
 * 4. generate-compose — 生成 docker-compose.yml
 * 5. start-services — 启动所有容器
 * 6. health-check — 等待所有服务就绪
 * 7. post-init — 部署后初始化（修正 Agent 接口地址等）
 */
export async function deploy(
  config: DeployConfig,
  options: DeployOptions,
  callbacks?: DeployCallbacks,
): Promise<DeployResult> {
  const { deployDir } = options;
  const packagesDir = options.packagesDir ?? getPackagesDir();
  const composeFilePath = resolve(deployDir, COMPOSE_FILE_NAME);

  // 1. 环境预检
  callbacks?.onStepStart?.('preflight', '检查 Docker 环境...');
  const ok = await preflightCheck();
  if (!ok) {
    callbacks?.onStepError?.('preflight', 'Docker 环境检查未通过');
    return { success: false };
  }
  callbacks?.onStepDone?.('preflight', 'Docker 环境检查通过');

  // 2. 加载离线镜像
  callbacks?.onStepStart?.('load-images', '加载离线镜像...');
  const extraImages = config.server.enableSnmpTrapper ? [SNMP_TRAPS_IMAGE] : [];
  const loadResults = await loadAllImages(
    packagesDir,
    options.skipExistingImages ?? true,
    callbacks?.onImageProgress,
    extraImages,
  );
  const failedImages = loadResults.filter((r) => !r.success);
  if (failedImages.length > 0) {
    const names = failedImages.map((r) => r.label).join(', ');
    callbacks?.onStepError?.('load-images', `以下镜像加载失败: ${names}`);
    return { success: false };
  }
  const skippedCount = loadResults.filter((r) => r.skipped).length;
  const loadedCount = loadResults.filter((r) => r.success && !r.skipped).length;
  callbacks?.onStepDone?.(
    'load-images',
    `镜像就绪（加载 ${loadedCount} 个，跳过 ${skippedCount} 个已存在）`,
  );

  // 3. 创建部署目录
  callbacks?.onStepStart?.('create-dir', `创建部署目录: ${deployDir}`);
  try {
    await mkdir(deployDir, { recursive: true });
  } catch (error: unknown) {
    const msg = error instanceof Error ? error.message : String(error);
    callbacks?.onStepError?.('create-dir', `创建目录失败: ${msg}`);
    return { success: false };
  }
  callbacks?.onStepDone?.('create-dir', '部署目录已就绪');

  // 4. 生成 docker-compose.yml
  callbacks?.onStepStart?.('generate-compose', '生成 docker-compose.yml...');
  try {
    const yamlContent = generateComposeYaml(config);
    await Bun.write(composeFilePath, yamlContent);
  } catch (error: unknown) {
    const msg = error instanceof Error ? error.message : String(error);
    callbacks?.onStepError?.('generate-compose', `生成配置失败: ${msg}`);
    return { success: false };
  }
  callbacks?.onStepDone?.('generate-compose', `已写入 ${composeFilePath}`);

  // 5. 启动服务
  callbacks?.onStepStart?.('start-services', '启动 Zabbix 服务...');
  const started = await composeUp(composeFilePath, COMPOSE_PROJECT_NAME);
  if (!started) {
    callbacks?.onStepError?.('start-services', '服务启动失败');
    return { success: false };
  }
  callbacks?.onStepDone?.('start-services', '所有容器已启动');

  // 6. 健康检查
  const health = await runHealthCheck(deployDir, callbacks);
  if (!health.ok) {
    return { success: false, healthCheck: health.result };
  }

  // 7. 部署后初始化
  const postInitResult = await runPostInit(config.web.httpPort, callbacks);

  return { success: true, healthCheck: health.result, postInit: postInitResult };
}
