import { exec } from '../utils/exec.ts';
import { logger } from '../utils/logger.ts';

/**
 * 检查 Docker 是否可用
 */
export async function checkDocker(): Promise<boolean> {
  const result = await exec(['docker', 'info']);
  if (result.exitCode !== 0) {
    logger.error('Docker 不可用，请确认 Docker 已安装并正在运行');
    return false;
  }
  return true;
}

/**
 * 检查 Docker Compose 是否可用
 */
export async function checkDockerCompose(): Promise<boolean> {
  const result = await exec(['docker', 'compose', 'version']);
  if (result.exitCode !== 0) {
    logger.error('Docker Compose 不可用');
    return false;
  }
  return true;
}

/**
 * 检查本地是否已存在指定镜像
 */
export async function imageExists(imageName: string): Promise<boolean> {
  const result = await exec(['docker', 'image', 'inspect', imageName]);
  return result.exitCode === 0;
}

/**
 * 加载离线 Docker 镜像
 */
export async function loadImage(tarPath: string): Promise<boolean> {
  const result = await exec(['docker', 'load', '-i', tarPath]);
  if (result.exitCode !== 0) {
    logger.error(`加载镜像失败: ${result.stderr}`);
    return false;
  }
  return true;
}

/**
 * 保存 Docker 镜像为 tar 文件
 */
export async function saveImage(imageName: string, outputPath: string): Promise<boolean> {
  const result = await exec(['docker', 'save', '-o', outputPath, imageName]);
  if (result.exitCode !== 0) {
    logger.error(`保存镜像失败: ${result.stderr}`);
    return false;
  }
  return true;
}

/** 容器状态信息 */
export interface ContainerStatus {
  name: string;
  state: string;
  status: string;
  health: string;
}

/**
 * 获取 compose 项目中所有容器的状态
 */
export async function getComposeStatus(
  composeFile: string,
  projectName: string,
): Promise<ContainerStatus[]> {
  const result = await exec([
    'docker',
    'compose',
    '-f',
    composeFile,
    '-p',
    projectName,
    'ps',
    '--format',
    'json',
  ]);

  if (result.exitCode !== 0) {
    return [];
  }

  const containers: ContainerStatus[] = [];

  // docker compose ps --format json 每行输出一个 JSON 对象
  for (const line of result.stdout.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      const obj = JSON.parse(trimmed) as Record<string, unknown>;
      containers.push({
        name: String(obj.Name ?? ''),
        state: String(obj.State ?? 'unknown'),
        status: String(obj.Status ?? ''),
        health: String(obj.Health ?? ''),
      });
    } catch {
      // 忽略非 JSON 行
    }
  }

  return containers;
}

/**
 * 启动 compose 服务（后台模式）
 */
export async function composeUp(composeFile: string, projectName: string): Promise<boolean> {
  const result = await exec([
    'docker',
    'compose',
    '-f',
    composeFile,
    '-p',
    projectName,
    'up',
    '-d',
    '--pull',
    'never',
    '--remove-orphans',
  ]);

  if (result.exitCode !== 0) {
    logger.error(`启动服务失败: ${result.stderr}`);
    return false;
  }
  return true;
}

/** compose down 选项 */
export interface ComposeDownOptions {
  removeVolumes?: boolean;
  removeImages?: boolean;
}

/**
 * 停止并清理 compose 服务
 */
export async function composeDown(
  composeFile: string,
  projectName: string,
  options: ComposeDownOptions = {},
): Promise<boolean> {
  const args = ['docker', 'compose', '-f', composeFile, '-p', projectName, 'down'];
  if (options.removeVolumes) {
    args.push('-v');
  }
  if (options.removeImages) {
    args.push('--rmi', 'all');
  }
  // 清理孤立容器
  args.push('--remove-orphans');

  const result = await exec(args);
  if (result.exitCode !== 0) {
    logger.error(`停止服务失败: ${result.stderr}`);
    return false;
  }
  return true;
}

/**
 * 列出 compose 项目关联的 Docker 数据卷
 */
export async function listProjectVolumes(projectName: string): Promise<string[]> {
  const result = await exec([
    'docker',
    'volume',
    'ls',
    '--filter',
    `label=com.docker.compose.project=${projectName}`,
    '--format',
    '{{.Name}}',
  ]);

  if (result.exitCode !== 0 || !result.stdout) {
    return [];
  }

  return result.stdout
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean);
}

/**
 * 删除指定的 Docker 数据卷
 * @returns 成功删除的卷名列表
 */
export async function removeVolumes(volumeNames: string[]): Promise<string[]> {
  if (volumeNames.length === 0) return [];

  const removed: string[] = [];
  for (const name of volumeNames) {
    const result = await exec(['docker', 'volume', 'rm', '-f', name]);
    if (result.exitCode === 0) {
      removed.push(name);
    }
  }
  return removed;
}

/** 镜像信息 */
export interface ImageInfo {
  name: string;
  id: string;
  size: string;
}

/**
 * 获取已加载的项目相关镜像信息
 */
export async function listProjectImages(imageNames: string[]): Promise<ImageInfo[]> {
  const images: ImageInfo[] = [];
  for (const name of imageNames) {
    const result = await exec([
      'docker',
      'image',
      'inspect',
      name,
      '--format',
      '{{.ID}}\t{{.Size}}',
    ]);
    if (result.exitCode === 0 && result.stdout) {
      const [id, sizeBytes] = result.stdout.split('\t');
      images.push({
        name,
        id: id?.slice(7, 19) ?? '', // 取短 ID
        size: formatBytes(Number(sizeBytes) || 0),
      });
    }
  }
  return images;
}

/**
 * 删除指定的 Docker 镜像
 * @returns 成功删除的镜像名列表
 */
export async function removeImages(imageNames: string[]): Promise<string[]> {
  if (imageNames.length === 0) return [];

  const removed: string[] = [];
  for (const name of imageNames) {
    const result = await exec(['docker', 'rmi', '-f', name]);
    if (result.exitCode === 0) {
      removed.push(name);
    }
  }
  return removed;
}

/** 字节数格式化为可读字符串 */
function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  const size = bytes / 1024 ** i;
  return `${size.toFixed(1)} ${units[i]}`;
}
