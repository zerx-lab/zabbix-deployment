import { resolve } from 'node:path';
import { IMAGE_LABELS, ZABBIX_IMAGES, imageToTarName } from '../types/constants.ts';
import { imageExists, loadImage } from './docker.ts';

/** 单个镜像的状态 */
export interface ImageStatus {
  /** 镜像全名 */
  image: string;
  /** 友好名称 */
  label: string;
  /** 对应的 tar 文件名 */
  tarName: string;
  /** tar 文件是否存在于 packages 目录 */
  tarExists: boolean;
  /** 镜像是否已加载到 Docker */
  loaded: boolean;
}

/**
 * 扫描所有必需镜像的状态
 */
export async function scanImageStatus(packagesDir: string): Promise<ImageStatus[]> {
  const results: ImageStatus[] = [];

  for (const image of ZABBIX_IMAGES) {
    const tarName = imageToTarName(image);
    const tarPath = resolve(packagesDir, tarName);
    const tarFileExists = await Bun.file(tarPath).exists();
    const loaded = await imageExists(image);

    results.push({
      image,
      label: IMAGE_LABELS[image] ?? image,
      tarName,
      tarExists: tarFileExists,
      loaded,
    });
  }

  return results;
}

/** 镜像加载结果 */
export interface LoadResult {
  image: string;
  label: string;
  success: boolean;
  skipped: boolean;
  error?: string;
}

/**
 * 批量加载离线镜像
 * @param packagesDir 离线包目录
 * @param skipExisting 是否跳过已加载的镜像
 * @param onProgress 每加载完一个镜像时的回调
 */
export async function loadAllImages(
  packagesDir: string,
  skipExisting: boolean,
  onProgress?: (result: LoadResult, index: number, total: number) => void,
): Promise<LoadResult[]> {
  const statuses = await scanImageStatus(packagesDir);
  const results: LoadResult[] = [];

  for (let i = 0; i < statuses.length; i++) {
    const entry = statuses[i];
    if (!entry) continue;
    const tarPath = resolve(packagesDir, entry.tarName);

    // 已加载且配置跳过
    if (entry.loaded && skipExisting) {
      const result: LoadResult = {
        image: entry.image,
        label: entry.label,
        success: true,
        skipped: true,
      };
      results.push(result);
      onProgress?.(result, i, statuses.length);
      continue;
    }

    // tar 文件不存在
    if (!entry.tarExists) {
      const result: LoadResult = {
        image: entry.image,
        label: entry.label,
        success: false,
        skipped: false,
        error: `离线包不存在: ${entry.tarName}`,
      };
      results.push(result);
      onProgress?.(result, i, statuses.length);
      continue;
    }

    // 加载镜像
    const ok = await loadImage(tarPath);
    const result: LoadResult = {
      image: entry.image,
      label: entry.label,
      success: ok,
      skipped: false,
      error: ok ? undefined : `加载失败: ${entry.tarName}`,
    };
    results.push(result);
    onProgress?.(result, i, statuses.length);
  }

  return results;
}

/**
 * 检查所有必需镜像是否就绪（已加载到 Docker）
 */
export async function checkAllImagesReady(): Promise<{
  ready: boolean;
  missing: string[];
}> {
  const missing: string[] = [];

  for (const image of ZABBIX_IMAGES) {
    const exists = await imageExists(image);
    if (!exists) {
      missing.push(image);
    }
  }

  return {
    ready: missing.length === 0,
    missing,
  };
}

/**
 * 获取 packages 目录下可用的 tar 文件数量摘要
 */
export async function getPackagesSummary(packagesDir: string): Promise<{
  total: number;
  available: number;
  missing: string[];
}> {
  const missing: string[] = [];
  let available = 0;

  for (const image of ZABBIX_IMAGES) {
    const tarName = imageToTarName(image);
    const tarPath = resolve(packagesDir, tarName);
    const exists = await Bun.file(tarPath).exists();
    if (exists) {
      available++;
    } else {
      missing.push(tarName);
    }
  }

  return {
    total: ZABBIX_IMAGES.length,
    available,
    missing,
  };
}
