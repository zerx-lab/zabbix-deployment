import { resolve } from 'node:path';
import { getComposeStatus } from '../services/docker.ts';
import type { ContainerStatus } from '../services/docker.ts';
import { checkAllImagesReady } from '../services/image.ts';
import { COMPOSE_FILE_NAME, COMPOSE_PROJECT_NAME, IMAGE_LABELS } from '../types/constants.ts';

/** 完整的环境状态 */
export interface EnvironmentStatus {
  /** 部署目录是否存在 */
  deployDirExists: boolean;
  /** compose 文件是否存在 */
  composeFileExists: boolean;
  /** Docker 镜像状态 */
  images: {
    ready: boolean;
    missing: string[];
  };
  /** 容器运行状态 */
  containers: ContainerStatus[];
}

/**
 * 获取当前部署环境的完整状态
 */
export async function getEnvironmentStatus(deployDir: string): Promise<EnvironmentStatus> {
  const deployDirExists = await dirExists(deployDir);
  const composeFilePath = resolve(deployDir, COMPOSE_FILE_NAME);
  const composeFileExists = await Bun.file(composeFilePath).exists();

  const images = await checkAllImagesReady();

  let containers: ContainerStatus[] = [];
  if (composeFileExists) {
    containers = await getComposeStatus(composeFilePath, COMPOSE_PROJECT_NAME);
  }

  return {
    deployDirExists,
    composeFileExists,
    images,
    containers,
  };
}

/**
 * 格式化状态信息为可读字符串
 */
export function formatStatus(status: EnvironmentStatus): string {
  const lines: string[] = [];

  lines.push('=== Zabbix 部署状态 ===');
  lines.push('');

  // 部署目录
  lines.push(`部署目录: ${status.deployDirExists ? '已创建' : '未创建'}`);
  lines.push(`Compose 文件: ${status.composeFileExists ? '已生成' : '未生成'}`);
  lines.push('');

  // 镜像状态
  lines.push('--- Docker 镜像 ---');
  if (status.images.ready) {
    lines.push('所有镜像已就绪');
  } else {
    lines.push(`缺少 ${status.images.missing.length} 个镜像:`);
    for (const img of status.images.missing) {
      const label = IMAGE_LABELS[img] ?? img;
      lines.push(`  - ${label} (${img})`);
    }
  }
  lines.push('');

  // 容器状态
  lines.push('--- 容器状态 ---');
  if (status.containers.length === 0) {
    lines.push('没有运行中的容器');
  } else {
    for (const c of status.containers) {
      const healthTag = c.health ? ` [${c.health}]` : '';
      lines.push(`  ${c.name}: ${c.state}${healthTag} - ${c.status}`);
    }
  }

  return lines.join('\n');
}

async function dirExists(dirPath: string): Promise<boolean> {
  try {
    const { stat } = await import('node:fs/promises');
    const s = await stat(dirPath);
    return s.isDirectory();
  } catch {
    return false;
  }
}
