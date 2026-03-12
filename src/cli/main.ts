import { resolve } from 'node:path';
import { cancel, confirm, isCancel, log, note, select, spinner } from '@clack/prompts';
import chalk from 'chalk';
import { collectDeployConfig } from '../config/collector.ts';
import { cleanupAll, getEnvironmentSnapshot, stopServices } from '../core/cleanup.ts';
import type { CleanupOptions, CleanupStep, EnvironmentSnapshot } from '../core/cleanup.ts';
import { deploy } from '../core/deploy.ts';
import type { DeployResult, DeployStep } from '../core/deploy.ts';
import type { HealthCheckResult } from '../core/health.ts';
import { getEnvironmentStatus } from '../core/status.ts';
import type { EnvironmentStatus } from '../core/status.ts';
import type { ContainerStatus } from '../services/docker.ts';
import { getPackagesSummary } from '../services/image.ts';
import type { DeployConfig, DeployOptions } from '../types/config.ts';
import { DEFAULT_DEPLOY_DIR, IMAGE_LABELS, ZABBIX_IMAGES } from '../types/constants.ts';

export type Action = 'deploy' | 'status' | 'stop' | 'uninstall' | 'quit';

export async function runCli(): Promise<void> {
  const action = await select<Action>({
    message: '请选择操作:',
    options: [
      { value: 'deploy', label: '部署 Zabbix', hint: '全新安装或更新' },
      { value: 'status', label: '检查状态', hint: '查看服务运行状态与镜像' },
      { value: 'stop', label: '停止服务', hint: '停止所有容器，保留数据和镜像' },
      { value: 'uninstall', label: '彻底清理', hint: '停止服务并删除所有数据、镜像、部署文件' },
      { value: 'quit', label: '退出' },
    ],
  });

  if (isCancel(action)) {
    cancel('操作已取消');
    process.exit(0);
  }

  switch (action) {
    case 'deploy':
      await handleDeploy();
      break;
    case 'status':
      await handleStatus();
      break;
    case 'stop':
      await handleStop();
      break;
    case 'uninstall':
      await handleUninstall();
      break;
    case 'quit':
      break;
  }
}

// ─── Deploy ───────────────────────────────────────────────

/** 检查离线包状态，返回 false 表示用户取消 */
async function checkPackages(packagesDir: string): Promise<boolean> {
  const s = spinner();
  s.start('检查离线镜像包...');
  const summary = await getPackagesSummary(packagesDir);
  s.stop('离线镜像包检查完成');

  if (summary.available === 0) {
    log.warn(
      chalk.yellow(
        'packages/ 目录中没有找到任何离线镜像包。\n' +
          '请先在有网络的机器上运行 scripts/save-images.sh 下载镜像，\n' +
          '然后将 tar 文件拷贝到 packages/ 目录。',
      ),
    );
    log.info('所需镜像文件:');
    for (const name of summary.missing) {
      log.info(`  - ${name}`);
    }
    return await askContinue('是否仍然继续？（如果 Docker 中已有镜像可以跳过加载）');
  }

  if (summary.missing.length > 0) {
    log.warn(
      chalk.yellow(
        `找到 ${summary.available}/${summary.total} 个镜像包，缺少 ${summary.missing.length} 个:`,
      ),
    );
    for (const name of summary.missing) {
      log.warn(`  - ${name}`);
    }
    return await askContinue('部分镜像缺失，是否继续？');
  }

  log.success(`所有 ${summary.total} 个离线镜像包已就绪`);
  return true;
}

/** 确认是否继续，返回 false 表示取消 */
async function askContinue(message: string): Promise<boolean> {
  const answer = await confirm({ message, initialValue: false });
  if (isCancel(answer) || !answer) {
    cancel('部署已取消');
    return false;
  }
  return true;
}

/** 展示配置摘要并确认 */
async function confirmConfig(config: DeployConfig, options: DeployOptions): Promise<boolean> {
  const configSummary = [
    `部署目录:     ${options.deployDir}`,
    `数据库密码:   ${'*'.repeat(config.database.password.length)}`,
    `Web 端口:     ${config.web.httpPort}`,
    `Server 端口:  ${config.server.listenPort}`,
    `时区:         ${config.web.timezone}`,
    `缓存大小:     ${config.server.cacheSize}`,
    `Poller 数量:  ${config.server.startPollers}`,
  ].join('\n');

  note(configSummary, '部署配置确认');

  const confirmed = await confirm({
    message: '确认以上配置并开始部署？',
    initialValue: true,
  });
  if (isCancel(confirmed) || !confirmed) {
    cancel('部署已取消');
    return false;
  }
  return true;
}

/** 执行部署并返回部署结果 */
async function executeDeploy(
  config: DeployConfig,
  options: DeployOptions,
  packagesDir: string,
): Promise<DeployResult> {
  const deploySpinner = spinner();

  const stepMessages: Record<DeployStep, string> = {
    preflight: '检查 Docker 环境',
    'load-images': '加载离线镜像',
    'create-dir': '创建部署目录',
    'generate-compose': '生成 docker-compose.yml',
    'start-services': '启动服务',
    'health-check': '健康检查',
    'post-init': '部署后初始化',
  };

  return await deploy(
    config,
    { ...options, packagesDir },
    {
      onStepStart(_step, msg) {
        deploySpinner.start(msg);
      },
      onStepDone(step, msg) {
        deploySpinner.stop(chalk.green(`✓ ${stepMessages[step]}: ${msg}`));
      },
      onStepError(step, error) {
        deploySpinner.stop(chalk.red(`✗ ${stepMessages[step]}: ${error}`));
      },
      onImageProgress(result, index, total) {
        if (result.skipped) {
          log.info(chalk.dim(`  [${index + 1}/${total}] ${result.label} - 已存在，跳过`));
        } else if (result.success) {
          log.success(`  [${index + 1}/${total}] ${result.label} - 加载成功`);
        } else {
          log.error(`  [${index + 1}/${total}] ${result.label} - ${result.error}`);
        }
      },
      onHealthTick(services, elapsed) {
        const readyCount = services.filter((s) => s.healthy).length;
        const elapsedSec = Math.floor(elapsed / 1000);
        deploySpinner.message(`等待服务就绪... ${readyCount}/${services.length} (${elapsedSec}s)`);
      },
    },
  );
}

/** 展示健康检查结果 */
function showHealthResult(
  result: HealthCheckResult,
  config: DeployConfig,
  options: DeployOptions,
): void {
  if (result.allHealthy) {
    const elapsedSec = Math.floor(result.elapsed / 1000);
    note(
      [
        `Zabbix Web:    http://localhost:${config.web.httpPort}`,
        '默认用户名:    Admin',
        '默认密码:      zabbix',
        '',
        `启动耗时:      ${elapsedSec} 秒`,
        `部署目录:      ${options.deployDir}`,
      ].join('\n'),
      '部署成功',
    );
    return;
  }

  if (result.timedOut) {
    log.warn('服务可能仍在启动中，请稍后使用「检查状态」功能确认');
  } else {
    log.error('请检查容器日志: docker compose -f <compose-file> logs');
  }

  for (const svc of result.services) {
    const icon = svc.healthy ? chalk.green('✓') : chalk.red('✗');
    log.info(`  ${icon} ${svc.name}: ${svc.state}`);
  }
}

/** 处理部署流程 */
async function handleDeploy(): Promise<void> {
  const collected = await collectDeployConfig();
  if (!collected) return;

  const { config, options } = collected;
  const packagesDir = resolve(import.meta.dir, '../../packages');

  const packagesOk = await checkPackages(packagesDir);
  if (!packagesOk) return;

  const configOk = await confirmConfig(config, options);
  if (!configOk) return;

  const result = await executeDeploy(config, options, packagesDir);
  if (!result.success) {
    log.error(chalk.red('部署失败，请检查上方错误信息'));
    return;
  }

  // 展示部署成功信息
  if (result.healthCheck) {
    showHealthResult(result.healthCheck, config, options);
  }
}

// ─── Status ───────────────────────────────────────────────

/** 展示镜像状态 */
function showImageStatus(status: EnvironmentStatus): void {
  log.info(chalk.bold('--- Docker 镜像 ---'));
  for (const image of ZABBIX_IMAGES) {
    const label = IMAGE_LABELS[image] ?? image;
    const loaded = !status.images.missing.includes(image);
    const icon = loaded ? chalk.green('✓') : chalk.red('✗');
    log.info(`  ${icon} ${label}`);
  }
  log.info('');
}

/** 获取容器状态图标 */
function containerIcon(c: ContainerStatus): string {
  if (c.state === 'running') {
    return c.health === 'healthy' || c.health === '' ? chalk.green('✓') : chalk.yellow('⏳');
  }
  return chalk.red('✗');
}

/** 展示容器状态 */
function showContainerStatus(containers: ContainerStatus[]): void {
  log.info(chalk.bold('--- 容器状态 ---'));
  if (containers.length === 0) {
    log.info('  没有运行中的容器');
  } else {
    for (const c of containers) {
      const icon = containerIcon(c);
      const healthTag = c.health ? ` [${c.health}]` : '';
      log.info(`  ${icon} ${c.name}: ${c.state}${healthTag}`);
    }
  }
  log.info('');
}

/** 处理状态查看 */
async function handleStatus(): Promise<void> {
  const s = spinner();
  s.start('正在获取环境状态...');
  const status = await getEnvironmentStatus(DEFAULT_DEPLOY_DIR);
  s.stop('状态获取完成');

  showImageStatus(status);
  showContainerStatus(status.containers);

  log.info(chalk.bold('--- 部署信息 ---'));
  log.info(
    `  部署目录: ${status.deployDirExists ? chalk.green(DEFAULT_DEPLOY_DIR) : chalk.red('未创建')}`,
  );
  log.info(
    `  Compose 文件: ${status.composeFileExists ? chalk.green('已生成') : chalk.red('未生成')}`,
  );
}

// ─── Stop ─────────────────────────────────────────────────

/** 展示快照中的容器列表 */
function showSnapshotContainers(containers: ContainerStatus[]): void {
  log.info(chalk.bold('--- 容器 ---'));
  if (containers.length === 0) {
    log.info('  没有运行中的容器');
    return;
  }
  for (const c of containers) {
    const icon = c.state === 'running' ? chalk.green('●') : chalk.red('●');
    const healthTag = c.health ? ` [${c.health}]` : '';
    log.info(`  ${icon} ${c.name}: ${c.state}${healthTag}`);
  }
}

/** 展示快照中的数据卷列表 */
function showSnapshotVolumes(volumes: string[]): void {
  log.info(chalk.bold('--- 数据卷 ---'));
  if (volumes.length === 0) {
    log.info('  没有关联的数据卷');
    return;
  }
  for (const v of volumes) {
    log.info(`  - ${v}`);
  }
}

/** 展示快照中的镜像列表 */
function showSnapshotImages(images: EnvironmentSnapshot['images']): void {
  log.info(chalk.bold('--- 镜像 ---'));
  if (images.length === 0) {
    log.info('  没有已加载的镜像');
    return;
  }
  for (const img of images) {
    const label = IMAGE_LABELS[img.name] ?? img.name;
    log.info(`  - ${label} (${img.size})`);
  }
}

/** 展示环境资源快照 */
function showSnapshot(snapshot: EnvironmentSnapshot): void {
  showSnapshotContainers(snapshot.containers);
  showSnapshotVolumes(snapshot.volumes);
  showSnapshotImages(snapshot.images);

  log.info(chalk.bold('--- 部署目录 ---'));
  const dirStatus = snapshot.deployDirExists ? chalk.green('存在') : chalk.dim('不存在');
  const fileStatus = snapshot.composeFileExists ? chalk.green('存在') : chalk.dim('不存在');
  log.info(`  ${snapshot.deployDir}: ${dirStatus}`);
  log.info(`  compose 文件: ${fileStatus}`);
  log.info('');
}

/** 处理停止服务（仅停止容器，保留数据和镜像） */
async function handleStop(): Promise<void> {
  // 1. 先获取并展示当前状态
  const s = spinner();
  s.start('正在获取服务状态...');
  const snapshot = await getEnvironmentSnapshot(DEFAULT_DEPLOY_DIR);
  s.stop('状态获取完成');

  const runningContainers = snapshot.containers.filter((c) => c.state === 'running');
  if (runningContainers.length === 0 && !snapshot.composeFileExists) {
    log.info('当前没有运行中的 Zabbix 服务');
    return;
  }

  // 展示容器列表
  if (runningContainers.length > 0) {
    log.info(chalk.bold('当前运行中的容器:'));
    for (const c of runningContainers) {
      const healthTag = c.health ? ` [${c.health}]` : '';
      log.info(`  ${chalk.green('●')} ${c.name}${healthTag}`);
    }
    log.info('');
  }

  // 2. 确认停止
  const confirmed = await confirm({
    message: '确认停止所有 Zabbix 服务？（数据和镜像将保留，可随时重新启动）',
    initialValue: true,
  });
  if (isCancel(confirmed) || !confirmed) {
    cancel('操作已取消');
    return;
  }

  // 3. 执行停止
  s.start('正在停止服务...');
  const result = await stopServices(DEFAULT_DEPLOY_DIR);
  if (result.success) {
    s.stop(chalk.green(`✓ ${result.message}`));
    log.info(chalk.dim('数据卷和镜像已保留，使用「部署 Zabbix」可重新启动服务'));
  } else {
    s.stop(chalk.red(`✗ ${result.message}`));
    log.error('请手动检查: docker compose -f /opt/zabbix/docker-compose.yml down');
  }
}

// ─── Uninstall ────────────────────────────────────────────

/** 清理步骤名称映射 */
const CLEANUP_STEP_LABELS: Record<CleanupStep, string> = {
  'stop-services': '停止容器',
  'remove-volumes': '清理数据卷',
  'remove-images': '清理镜像',
  'remove-deploy-dir': '删除部署目录',
};

/** 处理彻底清理环境：删除所有容器、数据卷、镜像和部署目录 */
async function handleUninstall(): Promise<void> {
  // 1. 扫描环境资源
  const s = spinner();
  s.start('正在扫描环境资源...');
  const snapshot = await getEnvironmentSnapshot(DEFAULT_DEPLOY_DIR);
  s.stop('扫描完成');

  const hasResource =
    snapshot.containers.length > 0 ||
    snapshot.volumes.length > 0 ||
    snapshot.images.length > 0 ||
    snapshot.composeFileExists ||
    snapshot.deployDirExists;

  if (!hasResource) {
    log.info('环境已是干净状态，无需清理');
    return;
  }

  // 2. 展示将要清理的资源
  showSnapshot(snapshot);

  note(
    [
      '1. 停止并移除所有容器和网络',
      chalk.yellow('2. 删除所有数据卷（数据库数据将丢失！）'),
      '3. 删除所有 Docker 镜像',
      `4. 删除部署目录 ${DEFAULT_DEPLOY_DIR}`,
    ].join('\n'),
    '即将执行的操作',
  );

  // 3. 确认（破坏性操作，默认 No）
  const confirmed = await confirm({
    message: chalk.red('此操作不可逆，将删除所有 Zabbix 相关资源，确认继续？'),
    initialValue: false,
  });

  if (isCancel(confirmed) || !confirmed) {
    cancel('操作已取消');
    return;
  }

  // 4. 执行全量清理
  const cleanupSpinner = spinner();
  const options: CleanupOptions = {
    removeVolumes: true,
    removeImages: true,
    removeDeployDir: true,
  };

  const result = await cleanupAll(DEFAULT_DEPLOY_DIR, options, {
    onStepStart(_step, msg) {
      cleanupSpinner.start(msg);
    },
    onStepDone(step, stepResult) {
      const label = CLEANUP_STEP_LABELS[step];
      if (stepResult.success) {
        cleanupSpinner.stop(chalk.green(`✓ ${label}: ${stepResult.message}`));
        if (stepResult.details) {
          for (const detail of stepResult.details) {
            log.info(chalk.dim(`    ${detail}`));
          }
        }
      } else {
        cleanupSpinner.stop(chalk.red(`✗ ${label}: ${stepResult.message}`));
      }
    },
  });

  // 5. 结果
  log.info('');
  if (result.allSuccess) {
    log.success(chalk.green('环境已完全卸载'));
  } else {
    log.warn('部分清理步骤未完成，请手动检查残留资源');
    for (const st of result.steps) {
      if (!st.success) {
        log.error(`  ${CLEANUP_STEP_LABELS[st.step]}: ${st.message}`);
      }
    }
  }
}
