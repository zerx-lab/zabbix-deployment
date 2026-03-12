import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { generateComposeYaml } from '../config/compose-generator.ts';
import { composeUp } from '../services/docker.ts';
import { checkDocker, checkDockerCompose } from '../services/docker.ts';
import type { LoadResult } from '../services/image.ts';
import { loadAllImages } from '../services/image.ts';
import type { DeployConfig, DeployOptions } from '../types/config.ts';
import { COMPOSE_FILE_NAME, COMPOSE_PROJECT_NAME } from '../types/constants.ts';

/** 部署步骤枚举 */
export type DeployStep =
  | 'preflight'
  | 'load-images'
  | 'generate-compose'
  | 'create-dir'
  | 'start-services'
  | 'health-check';

/** 部署进度回调 */
export interface DeployCallbacks {
  onStepStart?: (step: DeployStep, message: string) => void;
  onStepDone?: (step: DeployStep, message: string) => void;
  onStepError?: (step: DeployStep, error: string) => void;
  onImageProgress?: (result: LoadResult, index: number, total: number) => void;
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
 * 执行 Zabbix 完整部署流程
 */
export async function deploy(
  config: DeployConfig,
  options: DeployOptions,
  callbacks?: DeployCallbacks,
): Promise<boolean> {
  const { deployDir } = options;
  const packagesDir = options.packagesDir ?? resolve(import.meta.dir, '../../packages');
  const composeFilePath = resolve(deployDir, COMPOSE_FILE_NAME);

  // 1. 环境预检
  callbacks?.onStepStart?.('preflight', '检查 Docker 环境...');
  const ok = await preflightCheck();
  if (!ok) {
    callbacks?.onStepError?.('preflight', 'Docker 环境检查未通过');
    return false;
  }
  callbacks?.onStepDone?.('preflight', 'Docker 环境检查通过');

  // 2. 加载离线镜像
  callbacks?.onStepStart?.('load-images', '加载离线镜像...');
  const loadResults = await loadAllImages(
    packagesDir,
    options.skipExistingImages ?? true,
    callbacks?.onImageProgress,
  );
  const failedImages = loadResults.filter((r) => !r.success);
  if (failedImages.length > 0) {
    const names = failedImages.map((r) => r.label).join(', ');
    callbacks?.onStepError?.('load-images', `以下镜像加载失败: ${names}`);
    return false;
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
    return false;
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
    return false;
  }
  callbacks?.onStepDone?.('generate-compose', `已写入 ${composeFilePath}`);

  // 5. 启动服务
  callbacks?.onStepStart?.('start-services', '启动 Zabbix 服务...');
  const started = await composeUp(composeFilePath, COMPOSE_PROJECT_NAME);
  if (!started) {
    callbacks?.onStepError?.('start-services', '服务启动失败');
    return false;
  }
  callbacks?.onStepDone?.('start-services', '所有容器已启动');

  return true;
}
