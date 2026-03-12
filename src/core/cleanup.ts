import { resolve } from 'node:path';
import { rm } from 'node:fs/promises';
import {
  composeDown,
  getComposeStatus,
  listProjectImages,
  listProjectVolumes,
  removeImages,
  removeVolumes,
} from '../services/docker.ts';
import type { ComposeDownOptions, ContainerStatus, ImageInfo } from '../services/docker.ts';
import {
  COMPOSE_FILE_NAME,
  COMPOSE_PROJECT_NAME,
  IMAGE_LABELS,
  SNMP_TRAPS_IMAGE,
  ZABBIX_IMAGES,
} from '../types/constants.ts';

// ─── 类型定义 ─────────────────────────────────────────────

/** 清理步骤 */
export type CleanupStep =
  | 'stop-services'
  | 'remove-volumes'
  | 'remove-images'
  | 'remove-deploy-dir';

/** 单步清理结果 */
export interface CleanupStepResult {
  step: CleanupStep;
  success: boolean;
  message: string;
  details?: string[];
}

/** 完整清理结果 */
export interface CleanupResult {
  steps: CleanupStepResult[];
  /** 是否所有执行的步骤都成功 */
  allSuccess: boolean;
}

/** 清理选项（用户在 TUI 中选择的清理级别） */
export interface CleanupOptions {
  /** 删除数据卷（数据库数据等） */
  removeVolumes: boolean;
  /** 删除 Docker 镜像 */
  removeImages: boolean;
  /** 删除部署目录（compose 文件等） */
  removeDeployDir: boolean;
}

/** 清理进度回调 */
export interface CleanupCallbacks {
  onStepStart?: (step: CleanupStep, message: string) => void;
  onStepDone?: (step: CleanupStep, result: CleanupStepResult) => void;
}

/** 环境资源快照（用于清理前展示给用户确认） */
export interface EnvironmentSnapshot {
  containers: ContainerStatus[];
  volumes: string[];
  images: ImageInfo[];
  composeFileExists: boolean;
  deployDirExists: boolean;
  deployDir: string;
}

// ─── 资源探测 ─────────────────────────────────────────────

/** 所有项目相关的镜像名称（含可选的 SNMP Traps 镜像） */
function getAllImageNames(): string[] {
  return [...ZABBIX_IMAGES, SNMP_TRAPS_IMAGE];
}

/**
 * 获取当前环境的资源快照，用于在清理前展示给用户
 */
export async function getEnvironmentSnapshot(deployDir: string): Promise<EnvironmentSnapshot> {
  const composeFilePath = resolve(deployDir, COMPOSE_FILE_NAME);
  const composeFileExists = await Bun.file(composeFilePath).exists();

  let containers: ContainerStatus[] = [];
  if (composeFileExists) {
    containers = await getComposeStatus(composeFilePath, COMPOSE_PROJECT_NAME);
  }

  const volumes = await listProjectVolumes(COMPOSE_PROJECT_NAME);
  const images = await listProjectImages(getAllImageNames());

  let deployDirExists = false;
  try {
    const { stat } = await import('node:fs/promises');
    const s = await stat(deployDir);
    deployDirExists = s.isDirectory();
  } catch {
    deployDirExists = false;
  }

  return {
    containers,
    volumes,
    images,
    composeFileExists,
    deployDirExists,
    deployDir,
  };
}

/**
 * 格式化镜像名称为友好名称
 */
export function formatImageLabel(imageName: string): string {
  return IMAGE_LABELS[imageName] ?? imageName;
}

// ─── 停止服务 ─────────────────────────────────────────────

/**
 * 仅停止服务（不删除卷和镜像）
 */
export async function stopServices(deployDir: string): Promise<CleanupStepResult> {
  const composeFilePath = resolve(deployDir, COMPOSE_FILE_NAME);
  const exists = await Bun.file(composeFilePath).exists();

  if (!exists) {
    return {
      step: 'stop-services',
      success: true,
      message: '未找到 compose 文件，无需停止',
    };
  }

  const ok = await composeDown(composeFilePath, COMPOSE_PROJECT_NAME);
  return {
    step: 'stop-services',
    success: ok,
    message: ok ? '所有容器已停止并移除' : '停止服务失败',
  };
}

// ─── 完整清理 ─────────────────────────────────────────────

/** 停止容器子步骤 */
async function stepStopContainers(
  deployDir: string,
  options: CleanupOptions,
): Promise<CleanupStepResult> {
  const composeFilePath = resolve(deployDir, COMPOSE_FILE_NAME);
  const composeExists = await Bun.file(composeFilePath).exists();

  if (!composeExists) {
    return { step: 'stop-services', success: true, message: '未找到 compose 文件，跳过' };
  }

  const downOptions: ComposeDownOptions = {
    removeVolumes: options.removeVolumes,
    removeImages: options.removeImages,
  };
  const ok = await composeDown(composeFilePath, COMPOSE_PROJECT_NAME, downOptions);
  return {
    step: 'stop-services',
    success: ok,
    message: ok ? '容器和网络已清理' : '停止服务失败',
  };
}

/** 清理残留数据卷子步骤 */
async function stepRemoveVolumes(): Promise<CleanupStepResult> {
  const remainingVolumes = await listProjectVolumes(COMPOSE_PROJECT_NAME);
  if (remainingVolumes.length === 0) {
    return { step: 'remove-volumes', success: true, message: '数据卷已全部清理' };
  }

  const removed = await removeVolumes(remainingVolumes);
  const allDone = removed.length === remainingVolumes.length;
  return {
    step: 'remove-volumes',
    success: allDone,
    message: allDone
      ? `已删除 ${removed.length} 个数据卷`
      : `已删除 ${removed.length}/${remainingVolumes.length} 个数据卷`,
    details: removed,
  };
}

/** 清理残留镜像子步骤 */
async function stepRemoveImages(): Promise<CleanupStepResult> {
  const existingImages = await listProjectImages(getAllImageNames());
  if (existingImages.length === 0) {
    return { step: 'remove-images', success: true, message: '镜像已全部清理' };
  }

  const imageNames = existingImages.map((img) => img.name);
  const removed = await removeImages(imageNames);
  const allDone = removed.length === existingImages.length;
  return {
    step: 'remove-images',
    success: allDone,
    message: allDone
      ? `已删除 ${removed.length} 个镜像`
      : `已删除 ${removed.length}/${existingImages.length} 个镜像`,
    details: removed.map((name) => formatImageLabel(name)),
  };
}

/** 删除部署目录子步骤 */
async function stepRemoveDeployDir(deployDir: string): Promise<CleanupStepResult> {
  try {
    await rm(deployDir, { recursive: true, force: true });
    return { step: 'remove-deploy-dir', success: true, message: `已删除 ${deployDir}` };
  } catch (error: unknown) {
    const msg = error instanceof Error ? error.message : String(error);
    return { step: 'remove-deploy-dir', success: false, message: `删除目录失败: ${msg}` };
  }
}

/** 执行单个清理步骤并通过回调上报进度 */
async function runStep(
  step: CleanupStep,
  label: string,
  fn: () => Promise<CleanupStepResult>,
  callbacks?: CleanupCallbacks,
): Promise<CleanupStepResult> {
  callbacks?.onStepStart?.(step, label);
  const result = await fn();
  callbacks?.onStepDone?.(step, result);
  return result;
}

/**
 * 执行完整的环境清理流程
 *
 * 按顺序执行：停止容器 → 删除数据卷 → 删除镜像 → 删除部署目录
 * 每一步都可通过 options 开关控制是否执行。
 */
export async function cleanupAll(
  deployDir: string,
  options: CleanupOptions,
  callbacks?: CleanupCallbacks,
): Promise<CleanupResult> {
  const steps: CleanupStepResult[] = [];

  // 1. 停止并移除容器（始终执行）
  const stopResult = await runStep(
    'stop-services',
    '停止并移除容器...',
    () => stepStopContainers(deployDir, options),
    callbacks,
  );
  steps.push(stopResult);

  if (!stopResult.success) {
    return { steps, allSuccess: false };
  }

  // 2. 清理残留数据卷
  if (options.removeVolumes) {
    steps.push(await runStep('remove-volumes', '清理数据卷...', stepRemoveVolumes, callbacks));
  }

  // 3. 清理残留镜像
  if (options.removeImages) {
    steps.push(await runStep('remove-images', '清理 Docker 镜像...', stepRemoveImages, callbacks));
  }

  // 4. 删除部署目录
  if (options.removeDeployDir) {
    steps.push(
      await runStep(
        'remove-deploy-dir',
        `删除部署目录: ${deployDir}`,
        () => stepRemoveDeployDir(deployDir),
        callbacks,
      ),
    );
  }

  return { steps, allSuccess: steps.every((s) => s.success) };
}
