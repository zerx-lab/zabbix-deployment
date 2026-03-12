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
import {
  checkDockerInstallation,
  installDocker,
  scanDockerPackages,
} from '../services/docker-installer.ts';
import type { DockerInstallStepResult } from '../services/docker-installer.ts';
import type { ContainerStatus } from '../services/docker.ts';
import { getPackagesSummary } from '../services/image.ts';
import type { DeployConfig, DeployOptions } from '../types/config.ts';
import {
  DEFAULT_DEPLOY_DIR,
  DOCKER_INSTALL_STEP_LABELS,
  IMAGE_LABELS,
  ZABBIX_IMAGES,
} from '../types/constants.ts';
import type { DockerInstallStep } from '../types/constants.ts';
import { getPackagesDir } from '../utils/paths.ts';
import type { DeployArgs } from './args.ts';

export type Action = 'install-docker' | 'deploy' | 'status' | 'stop' | 'uninstall' | 'quit';

/** CLI 模式上下文 */
export interface CliContext {
  /** 是否自动确认（跳过交互式 confirm） */
  autoConfirm: boolean;
  /** deploy 命令的 CLI 参数 */
  deployArgs: Partial<DeployArgs>;
}

const DEFAULT_CONTEXT: CliContext = {
  autoConfirm: false,
  deployArgs: {},
};

// ─── 通用工具 ──────────────────────────────────────────────

/**
 * 执行确认操作：
 * - autoConfirm=true 时直接返回 true
 * - 否则使用交互式 confirm
 */
async function doConfirm(ctx: CliContext, message: string, initialValue = true): Promise<boolean> {
  if (ctx.autoConfirm) {
    console.log(`${chalk.green('✓')} ${message} (自动确认)`);
    return true;
  }
  const answer = await confirm({ message, initialValue });
  if (isCancel(answer)) {
    cancel('操作已取消');
    return false;
  }
  return answer;
}

/**
 * 创建进度指示器：
 * - TTY 模式使用 spinner
 * - 非 TTY 模式使用 console.log
 */
function createProgress(): {
  start: (msg: string) => void;
  stop: (msg: string) => void;
  message: (msg: string) => void;
} {
  if (process.stdin.isTTY) {
    const s = spinner();
    return {
      start: (msg) => s.start(msg),
      stop: (msg) => s.stop(msg),
      message: (msg) => s.message(msg),
    };
  }
  return {
    start: (msg) => console.log(`... ${msg}`),
    stop: (msg) => console.log(msg),
    message: (_msg) => {}, // 非 TTY 下不更新进度消息
  };
}

/** 输出日志（兼容 TTY/非 TTY） */
function logInfo(msg: string): void {
  if (process.stdin.isTTY) {
    log.info(msg);
  } else {
    console.log(msg);
  }
}

function logSuccess(msg: string): void {
  if (process.stdin.isTTY) {
    log.success(msg);
  } else {
    console.log(chalk.green(msg));
  }
}

function logError(msg: string): void {
  if (process.stdin.isTTY) {
    log.error(msg);
  } else {
    console.error(chalk.red(msg));
  }
}

function logWarn(msg: string): void {
  if (process.stdin.isTTY) {
    log.warn(msg);
  } else {
    console.warn(chalk.yellow(msg));
  }
}

function logNote(msg: string, title: string): void {
  if (process.stdin.isTTY) {
    note(msg, title);
  } else {
    console.log(`\n── ${title} ──`);
    console.log(msg);
    console.log('');
  }
}

// ─── 交互式 TUI 入口 ──────────────────────────────────────

export async function runCli(): Promise<void> {
  const action = await select<Action>({
    message: '请选择操作:',
    options: [
      {
        value: 'install-docker',
        label: '安装 Docker',
        hint: '从离线包安装 Docker 和 Docker Compose',
      },
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

  if (action === 'quit') return;

  await runAction(action, DEFAULT_CONTEXT);
}

// ─── CLI 模式入口 ──────────────────────────────────────────

/** 直接执行指定操作（CLI 模式） */
export async function runAction(action: Action, ctx: CliContext): Promise<void> {
  switch (action) {
    case 'install-docker':
      await handleInstallDocker(ctx);
      break;
    case 'deploy':
      await handleDeploy(ctx);
      break;
    case 'status':
      await handleStatus();
      break;
    case 'stop':
      await handleStop(ctx);
      break;
    case 'uninstall':
      await handleUninstall(ctx);
      break;
    case 'quit':
      break;
  }
}

// ─── Install Docker ───────────────────────────────────────

/** 格式化 Docker 状态文本 */
function formatDockerStatus(installed: boolean, running: boolean, version?: string): string {
  if (!installed) return chalk.red('未安装');
  if (running) return chalk.green(`${version} (运行中)`);
  return chalk.yellow(`${version} (未运行)`);
}

/** 展示当前 Docker 环境状态 */
function showDockerCheckStatus(check: Awaited<ReturnType<typeof checkDockerInstallation>>): void {
  logInfo(chalk.bold('--- 当前环境 ---'));
  logInfo(
    `  Docker:         ${formatDockerStatus(check.dockerInstalled, check.dockerRunning, check.dockerVersion)}`,
  );
  logInfo(
    `  Docker Compose: ${check.composeInstalled ? chalk.green(check.composeVersion ?? '已安装') : chalk.red('未安装')}`,
  );
  logInfo(`  系统架构:       ${check.arch}`);
  logInfo(`  Root 权限:      ${check.isRoot ? chalk.green('是') : chalk.yellow('否')}`);
  logInfo('');
}

/** 展示离线安装包扫描结果 */
function showDockerPackageScan(scan: Awaited<ReturnType<typeof scanDockerPackages>>): void {
  logInfo(chalk.bold('--- 离线安装包 ---'));
  logInfo(
    `  Docker 安装包:   ${scan.hasDockerTgz ? chalk.green(scan.dockerTgzName ?? '已找到') : chalk.red('未找到 (docker-*.tgz)')}`,
  );
  logInfo(
    `  Compose 插件:    ${scan.hasComposeBin ? chalk.green(scan.composeBinName ?? '已找到') : chalk.red('未找到 (docker-compose-*)')}`,
  );
  logInfo('');
}

/** 构建安装计划列表 */
function buildInstallPlan(
  check: Awaited<ReturnType<typeof checkDockerInstallation>>,
  scan: Awaited<ReturnType<typeof scanDockerPackages>>,
): string[] {
  const items: string[] = [];
  if (!check.dockerInstalled || !check.dockerRunning) {
    items.push('解压 Docker 二进制文件到 /usr/local/bin/');
    items.push('创建 docker 用户组');
    items.push('创建 systemd 服务（containerd + docker）');
    items.push('启动 Docker 服务并设置开机自启');
  }
  if (!check.composeInstalled && scan.hasComposeBin) {
    items.push('安装 Docker Compose 插件');
  }
  items.push('验证安装结果');
  return items.map((item, i) => `${i + 1}. ${item}`);
}

/** 提示用户如何让 docker 组权限立即生效 */
function showDockerGroupHint(needsRelogin: boolean): void {
  if (needsRelogin) {
    const sudoUser = process.env.SUDO_USER;
    if (sudoUser) {
      logWarn(
        chalk.yellow(
          `提示: 用户 ${sudoUser} 已加入 docker 组，需要刷新组权限后才能免 sudo 使用 docker 命令。\n请在当前终端执行以下命令立即生效:\n\n${chalk.cyan('  newgrp docker')}\n\n或者重新登录当前用户。`,
        ),
      );
    } else {
      logWarn(
        chalk.yellow(
          '提示: 当前用户已加入 docker 组，需要重新登录后才能免 sudo 使用 docker 命令。',
        ),
      );
    }
    return;
  }

  // 非 root 用户未通过 sudo 运行时，提示手动加入 docker 组
  if (process.getuid?.() !== 0) {
    const currentUser = process.env.USER ?? process.env.LOGNAME;
    if (currentUser && currentUser !== 'root') {
      logWarn(
        chalk.yellow(
          `提示: 当前用户不在 docker 组中，若需免 sudo 使用 docker，请执行:\n\n${chalk.cyan(`  sudo usermod -aG docker ${currentUser} && newgrp docker`)}`,
        ),
      );
    }
  }
}

/** 展示 Docker 安装结果 */
function showDockerInstallResult(result: Awaited<ReturnType<typeof installDocker>>): void {
  logInfo('');
  if (result.success) {
    logSuccess(chalk.green('Docker 安装完成！'));
    showDockerGroupHint(result.needsRelogin);
    for (const step of result.steps) {
      if (!step.success && step.step === 'install-compose') {
        logWarn(`Docker Compose 未安装: ${step.message}`);
      }
    }
  } else {
    logError(chalk.red('Docker 安装失败，请检查上方错误信息'));
    for (const step of result.steps) {
      if (!step.success) {
        logError(`  ${DOCKER_INSTALL_STEP_LABELS[step.step]}: ${step.message}`);
      }
    }
  }
}

/** 处理 Docker 离线安装流程 */
async function handleInstallDocker(ctx: CliContext): Promise<void> {
  const packagesDir = getPackagesDir();

  // 1. 检查当前 Docker 状态
  const s = createProgress();
  s.start('检查 Docker 安装状态...');
  const check = await checkDockerInstallation();
  s.stop('检查完成');

  showDockerCheckStatus(check);

  // 如果 Docker 和 Compose 都已安装且运行中
  if (check.dockerInstalled && check.dockerRunning && check.composeInstalled) {
    logSuccess('Docker 和 Docker Compose 已安装且正常运行，无需额外操作');
    const continueAnyway = await doConfirm(ctx, '是否仍要重新安装/覆盖？', false);
    if (!continueAnyway) return;
  }

  // 2. 检查离线安装包
  s.start('扫描离线安装包...');
  const scan = await scanDockerPackages(packagesDir);
  s.stop('扫描完成');

  if (!scan.dirExists) {
    logError(
      chalk.red(
        'packages/docker/ 目录不存在。\n' +
          '请先在有网络的机器上运行:\n' +
          '  bash scripts/download-docker.sh\n' +
          '然后将 packages/docker/ 目录拷贝到离线机器。',
      ),
    );
    return;
  }

  showDockerPackageScan(scan);

  if (!scan.hasDockerTgz) {
    logError('缺少 Docker 安装包，请先运行 scripts/download-docker.sh 下载');
    return;
  }

  if (!check.isRoot && !(check.dockerInstalled && check.dockerRunning)) {
    logError(
      chalk.red(
        '安装 Docker 需要 root 权限。\n' +
          '请使用 sudo 运行本工具:\n' +
          '  sudo ./build/zabbix-deploy',
      ),
    );
    return;
  }

  // 3. 展示安装计划并确认
  logNote(buildInstallPlan(check, scan).join('\n'), '安装计划');

  const confirmed = await doConfirm(ctx, '确认开始安装？');
  if (!confirmed) return;

  // 4. 执行安装
  const installProgress = createProgress();

  const result = await installDocker(
    packagesDir,
    { skipExisting: true, addUserToGroup: true },
    {
      onStepStart(_step: DockerInstallStep, msg: string) {
        installProgress.start(msg);
      },
      onStepDone(step: DockerInstallStep, stepResult: DockerInstallStepResult) {
        const label = DOCKER_INSTALL_STEP_LABELS[step];
        if (stepResult.skipped) {
          installProgress.stop(chalk.dim(`⊘ ${label}: ${stepResult.message}`));
        } else {
          installProgress.stop(chalk.green(`✓ ${label}: ${stepResult.message}`));
        }
      },
      onStepError(step: DockerInstallStep, error: string) {
        installProgress.stop(chalk.red(`✗ ${DOCKER_INSTALL_STEP_LABELS[step]}: ${error}`));
      },
    },
  );

  // 5. 展示结果
  showDockerInstallResult(result);
}

// ─── Deploy ───────────────────────────────────────────────

/** 检查离线包状态，返回 false 表示用户取消 */
async function checkPackages(packagesDir: string, ctx: CliContext): Promise<boolean> {
  const s = createProgress();
  s.start('检查离线镜像包...');
  const summary = await getPackagesSummary(packagesDir);
  s.stop('离线镜像包检查完成');

  if (summary.available === 0) {
    logWarn(
      chalk.yellow(
        'packages/ 目录中没有找到任何离线镜像包。\n' +
          '请先在有网络的机器上运行 scripts/save-images.sh 下载镜像，\n' +
          '然后将 tar 文件拷贝到 packages/ 目录。',
      ),
    );
    logInfo('所需镜像文件:');
    for (const name of summary.missing) {
      logInfo(`  - ${name}`);
    }
    return await doConfirm(ctx, '是否仍然继续？（如果 Docker 中已有镜像可以跳过加载）', false);
  }

  if (summary.missing.length > 0) {
    logWarn(
      chalk.yellow(
        `找到 ${summary.available}/${summary.total} 个镜像包，缺少 ${summary.missing.length} 个:`,
      ),
    );
    for (const name of summary.missing) {
      logWarn(`  - ${name}`);
    }
    return await doConfirm(ctx, '部分镜像缺失，是否继续？', false);
  }

  logSuccess(`所有 ${summary.total} 个离线镜像包已就绪`);
  return true;
}

/** 展示配置摘要并确认 */
async function confirmConfig(
  config: DeployConfig,
  options: DeployOptions,
  ctx: CliContext,
): Promise<boolean> {
  const configSummary = [
    `部署目录:     ${options.deployDir}`,
    `数据库密码:   ${'*'.repeat(config.database.password.length)}`,
    `Web 端口:     ${config.web.httpPort}`,
    `Server 端口:  ${config.server.listenPort}`,
    `时区:         ${config.web.timezone}`,
    `缓存大小:     ${config.server.cacheSize}`,
    `Poller 数量:  ${config.server.startPollers}`,
  ].join('\n');

  logNote(configSummary, '部署配置确认');

  return await doConfirm(ctx, '确认以上配置并开始部署？');
}

/** 执行部署并返回部署结果 */
async function executeDeploy(
  config: DeployConfig,
  options: DeployOptions,
  packagesDir: string,
): Promise<DeployResult> {
  const deployProgress = createProgress();

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
        deployProgress.start(msg);
      },
      onStepDone(step, msg) {
        deployProgress.stop(chalk.green(`✓ ${stepMessages[step]}: ${msg}`));
      },
      onStepError(step, error) {
        deployProgress.stop(chalk.red(`✗ ${stepMessages[step]}: ${error}`));
      },
      onImageProgress(result, index, total) {
        if (result.skipped) {
          logInfo(chalk.dim(`  [${index + 1}/${total}] ${result.label} - 已存在，跳过`));
        } else if (result.success) {
          logSuccess(`  [${index + 1}/${total}] ${result.label} - 加载成功`);
        } else {
          logError(`  [${index + 1}/${total}] ${result.label} - ${result.error}`);
        }
      },
      onHealthTick(services, elapsed) {
        const readyCount = services.filter((s) => s.healthy).length;
        const elapsedSec = Math.floor(elapsed / 1000);
        deployProgress.message(`等待服务就绪... ${readyCount}/${services.length} (${elapsedSec}s)`);
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
    logNote(
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
    logWarn('服务可能仍在启动中，请稍后使用「检查状态」功能确认');
  } else {
    logError('请检查容器日志: docker compose -f <compose-file> logs');
  }

  for (const svc of result.services) {
    const icon = svc.healthy ? chalk.green('✓') : chalk.red('✗');
    logInfo(`  ${icon} ${svc.name}: ${svc.state}`);
  }
}

/** 从 CLI 参数构建部署配置 */
function buildConfigFromArgs(args: Partial<DeployArgs>): {
  config: DeployConfig;
  options: DeployOptions;
} | null {
  if (!args.dbPassword) {
    logError('CLI 模式下 deploy 命令需要 --db-password 参数');
    logError('示例: ./zabbix-deploy deploy -y --db-password mypassword123');
    return null;
  }

  if (args.dbPassword.length < 8) {
    logError('数据库密码至少 8 位');
    return null;
  }

  const config: DeployConfig = {
    version: '7.0',
    database: {
      host: 'postgres',
      port: 5432,
      name: 'zabbix',
      user: 'zabbix',
      password: args.dbPassword,
    },
    server: {
      listenPort: args.serverPort ?? 10051,
      cacheSize: args.cacheSize ?? '128M',
      startPollers: args.startPollers ?? 5,
      enableSnmpTrapper: args.enableSnmpTrapper ?? false,
      snmpTrapperPort: args.snmpTrapperPort ?? 162,
    },
    web: {
      httpPort: args.webPort ?? 8080,
      httpsPort: 8443,
      timezone: args.timezone ?? 'Asia/Shanghai',
    },
    agent: {
      hostname: 'Zabbix server',
      serverHost: 'zabbix-server',
      listenPort: 10050,
    },
  };

  const options: DeployOptions = {
    deployDir: args.deployDir ?? DEFAULT_DEPLOY_DIR,
    skipExistingImages: true,
  };

  return { config, options };
}

/** 处理部署流程 */
async function handleDeploy(ctx: CliContext): Promise<void> {
  let collected: { config: DeployConfig; options: DeployOptions } | null;

  // CLI 模式：从参数构建配置；TUI 模式：交互式收集
  if (ctx.autoConfirm || Object.keys(ctx.deployArgs).length > 0) {
    collected = buildConfigFromArgs(ctx.deployArgs);
  } else {
    collected = await collectDeployConfig();
  }
  if (!collected) return;

  const { config, options } = collected;
  const packagesDir = getPackagesDir();

  const packagesOk = await checkPackages(packagesDir, ctx);
  if (!packagesOk) return;

  const configOk = await confirmConfig(config, options, ctx);
  if (!configOk) return;

  const result = await executeDeploy(config, options, packagesDir);
  if (!result.success) {
    logError(chalk.red('部署失败，请检查上方错误信息'));
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
  logInfo(chalk.bold('--- Docker 镜像 ---'));
  for (const image of ZABBIX_IMAGES) {
    const label = IMAGE_LABELS[image] ?? image;
    const loaded = !status.images.missing.includes(image);
    const icon = loaded ? chalk.green('✓') : chalk.red('✗');
    logInfo(`  ${icon} ${label}`);
  }
  logInfo('');
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
  logInfo(chalk.bold('--- 容器状态 ---'));
  if (containers.length === 0) {
    logInfo('  没有运行中的容器');
  } else {
    for (const c of containers) {
      const icon = containerIcon(c);
      const healthTag = c.health ? ` [${c.health}]` : '';
      logInfo(`  ${icon} ${c.name}: ${c.state}${healthTag}`);
    }
  }
  logInfo('');
}

/** 处理状态查看 */
async function handleStatus(): Promise<void> {
  const s = createProgress();
  s.start('正在获取环境状态...');
  const status = await getEnvironmentStatus(DEFAULT_DEPLOY_DIR);
  s.stop('状态获取完成');

  showImageStatus(status);
  showContainerStatus(status.containers);

  logInfo(chalk.bold('--- 部署信息 ---'));
  logInfo(
    `  部署目录: ${status.deployDirExists ? chalk.green(DEFAULT_DEPLOY_DIR) : chalk.red('未创建')}`,
  );
  logInfo(
    `  Compose 文件: ${status.composeFileExists ? chalk.green('已生成') : chalk.red('未生成')}`,
  );
}

// ─── Stop ─────────────────────────────────────────────────

/** 展示快照中的容器列表 */
function showSnapshotContainers(containers: ContainerStatus[]): void {
  logInfo(chalk.bold('--- 容器 ---'));
  if (containers.length === 0) {
    logInfo('  没有运行中的容器');
    return;
  }
  for (const c of containers) {
    const icon = c.state === 'running' ? chalk.green('●') : chalk.red('●');
    const healthTag = c.health ? ` [${c.health}]` : '';
    logInfo(`  ${icon} ${c.name}: ${c.state}${healthTag}`);
  }
}

/** 展示快照中的数据卷列表 */
function showSnapshotVolumes(volumes: string[]): void {
  logInfo(chalk.bold('--- 数据卷 ---'));
  if (volumes.length === 0) {
    logInfo('  没有关联的数据卷');
    return;
  }
  for (const v of volumes) {
    logInfo(`  - ${v}`);
  }
}

/** 展示快照中的镜像列表 */
function showSnapshotImages(images: EnvironmentSnapshot['images']): void {
  logInfo(chalk.bold('--- 镜像 ---'));
  if (images.length === 0) {
    logInfo('  没有已加载的镜像');
    return;
  }
  for (const img of images) {
    const label = IMAGE_LABELS[img.name] ?? img.name;
    logInfo(`  - ${label} (${img.size})`);
  }
}

/** 展示环境资源快照 */
function showSnapshot(snapshot: EnvironmentSnapshot): void {
  showSnapshotContainers(snapshot.containers);
  showSnapshotVolumes(snapshot.volumes);
  showSnapshotImages(snapshot.images);

  logInfo(chalk.bold('--- 部署目录 ---'));
  const dirStatus = snapshot.deployDirExists ? chalk.green('存在') : chalk.dim('不存在');
  const fileStatus = snapshot.composeFileExists ? chalk.green('存在') : chalk.dim('不存在');
  logInfo(`  ${snapshot.deployDir}: ${dirStatus}`);
  logInfo(`  compose 文件: ${fileStatus}`);
  logInfo('');
}

/** 处理停止服务（仅停止容器，保留数据和镜像） */
async function handleStop(ctx: CliContext): Promise<void> {
  // 1. 先获取并展示当前状态
  const s = createProgress();
  s.start('正在获取服务状态...');
  const snapshot = await getEnvironmentSnapshot(DEFAULT_DEPLOY_DIR);
  s.stop('状态获取完成');

  const runningContainers = snapshot.containers.filter((c) => c.state === 'running');
  if (runningContainers.length === 0 && !snapshot.composeFileExists) {
    logInfo('当前没有运行中的 Zabbix 服务');
    return;
  }

  // 展示容器列表
  if (runningContainers.length > 0) {
    logInfo(chalk.bold('当前运行中的容器:'));
    for (const c of runningContainers) {
      const healthTag = c.health ? ` [${c.health}]` : '';
      logInfo(`  ${chalk.green('●')} ${c.name}${healthTag}`);
    }
    logInfo('');
  }

  // 2. 确认停止
  const confirmed = await doConfirm(
    ctx,
    '确认停止所有 Zabbix 服务？（数据和镜像将保留，可随时重新启动）',
  );
  if (!confirmed) return;

  // 3. 执行停止
  s.start('正在停止服务...');
  const result = await stopServices(DEFAULT_DEPLOY_DIR);
  if (result.success) {
    s.stop(chalk.green(`✓ ${result.message}`));
    logInfo(chalk.dim('数据卷和镜像已保留，使用「部署 Zabbix」可重新启动服务'));
  } else {
    s.stop(chalk.red(`✗ ${result.message}`));
    logError('请手动检查: docker compose -f /opt/zabbix/docker-compose.yml down');
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
async function handleUninstall(ctx: CliContext): Promise<void> {
  // 1. 扫描环境资源
  const s = createProgress();
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
    logInfo('环境已是干净状态，无需清理');
    return;
  }

  // 2. 展示将要清理的资源
  showSnapshot(snapshot);

  logNote(
    [
      '1. 停止并移除所有容器和网络',
      chalk.yellow('2. 删除所有数据卷（数据库数据将丢失！）'),
      '3. 删除所有 Docker 镜像',
      `4. 删除部署目录 ${DEFAULT_DEPLOY_DIR}`,
    ].join('\n'),
    '即将执行的操作',
  );

  // 3. 确认（破坏性操作）
  const confirmed = await doConfirm(
    ctx,
    chalk.red('此操作不可逆，将删除所有 Zabbix 相关资源，确认继续？'),
    false,
  );
  if (!confirmed) return;

  // 4. 执行全量清理
  const cleanupProgress = createProgress();
  const options: CleanupOptions = {
    removeVolumes: true,
    removeImages: true,
    removeDeployDir: true,
  };

  const result = await cleanupAll(DEFAULT_DEPLOY_DIR, options, {
    onStepStart(_step, msg) {
      cleanupProgress.start(msg);
    },
    onStepDone(step, stepResult) {
      const label = CLEANUP_STEP_LABELS[step];
      if (stepResult.success) {
        cleanupProgress.stop(chalk.green(`✓ ${label}: ${stepResult.message}`));
        if (stepResult.details) {
          for (const detail of stepResult.details) {
            logInfo(chalk.dim(`    ${detail}`));
          }
        }
      } else {
        cleanupProgress.stop(chalk.red(`✗ ${label}: ${stepResult.message}`));
      }
    },
  });

  // 5. 结果
  logInfo('');
  if (result.allSuccess) {
    logSuccess(chalk.green('环境已完全卸载'));
  } else {
    logWarn('部分清理步骤未完成，请手动检查残留资源');
    for (const st of result.steps) {
      if (!st.success) {
        logError(`  ${CLEANUP_STEP_LABELS[st.step]}: ${st.message}`);
      }
    }
  }
}
