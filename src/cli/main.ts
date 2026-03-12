import { resolve } from 'node:path';
import { cancel, confirm, isCancel, log, note, select, spinner } from '@clack/prompts';
import chalk from 'chalk';
import { collectDeployConfig } from '../config/collector.ts';
import { deploy } from '../core/deploy.ts';
import type { DeployStep } from '../core/deploy.ts';
import { waitForHealthy } from '../core/health.ts';
import type { HealthCheckResult } from '../core/health.ts';
import { getEnvironmentStatus } from '../core/status.ts';
import type { EnvironmentStatus } from '../core/status.ts';
import type { ContainerStatus } from '../services/docker.ts';
import { composeDown } from '../services/docker.ts';
import { getPackagesSummary } from '../services/image.ts';
import type { DeployConfig, DeployOptions } from '../types/config.ts';
import {
  COMPOSE_FILE_NAME,
  COMPOSE_PROJECT_NAME,
  DEFAULT_DEPLOY_DIR,
  IMAGE_LABELS,
  ZABBIX_IMAGES,
} from '../types/constants.ts';

export type Action = 'deploy' | 'status' | 'stop' | 'quit';

export async function runCli(): Promise<void> {
  const action = await select<Action>({
    message: '请选择操作:',
    options: [
      { value: 'deploy', label: '部署 Zabbix', hint: '全新安装或更新' },
      { value: 'status', label: '检查状态', hint: '查看服务运行状态与镜像' },
      { value: 'stop', label: '停止服务', hint: '停止并清理所有容器' },
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

/** 执行部署并返回是否成功 */
async function executeDeploy(
  config: DeployConfig,
  options: DeployOptions,
  packagesDir: string,
): Promise<boolean> {
  const deploySpinner = spinner();

  const stepMessages: Record<DeployStep, string> = {
    preflight: '检查 Docker 环境',
    'load-images': '加载离线镜像',
    'create-dir': '创建部署目录',
    'generate-compose': '生成 docker-compose.yml',
    'start-services': '启动服务',
    'health-check': '健康检查',
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

  const success = await executeDeploy(config, options, packagesDir);
  if (!success) {
    log.error(chalk.red('部署失败，请检查上方错误信息'));
    return;
  }

  const deploySpinner = spinner();
  deploySpinner.start('等待服务就绪（最长 3 分钟）...');
  const healthResult = await waitForHealthy(options.deployDir, (services, elapsed) => {
    const readyCount = services.filter((s) => s.healthy).length;
    const elapsedSec = Math.floor(elapsed / 1000);
    deploySpinner.message(`等待服务就绪... ${readyCount}/${services.length} (${elapsedSec}s)`);
  });

  const stopMsg = healthResult.allHealthy
    ? chalk.green('所有服务已就绪')
    : chalk.yellow('健康检查完成');
  deploySpinner.stop(stopMsg);

  showHealthResult(healthResult, config, options);
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

/** 处理停止服务 */
async function handleStop(): Promise<void> {
  const composeFile = resolve(DEFAULT_DEPLOY_DIR, COMPOSE_FILE_NAME);
  const exists = await Bun.file(composeFile).exists();

  if (!exists) {
    log.warn('未找到部署的 compose 文件，没有可停止的服务');
    return;
  }

  const removeVolumes = await confirm({
    message: '是否同时删除数据卷？（将丢失所有数据）',
    initialValue: false,
  });
  if (isCancel(removeVolumes)) {
    cancel('操作已取消');
    return;
  }

  const s = spinner();
  s.start('正在停止服务...');
  const ok = await composeDown(composeFile, COMPOSE_PROJECT_NAME, removeVolumes);
  if (ok) {
    s.stop(chalk.green('服务已停止'));
  } else {
    s.stop(chalk.red('停止服务失败'));
  }
}
