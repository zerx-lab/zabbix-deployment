import { existsSync } from 'node:fs';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import type { DockerInstallStep } from '../types/constants.ts';
import {
  CONTAINERD_SERVICE_PATH,
  DOCKER_BIN_DIR,
  DOCKER_CLI_PLUGINS_DIR,
  DOCKER_PACKAGES_DIR,
  DOCKER_SERVICE_PATH,
  DOCKER_SOCKET_PATH,
} from '../types/constants.ts';
import { exec } from '../utils/exec.ts';

// ─── 类型定义 ─────────────────────────────────────────────

/** Docker 安装检查结果 */
export interface DockerCheckResult {
  /** Docker CLI 是否已安装 */
  dockerInstalled: boolean;
  /** Docker 守护进程是否正在运行 */
  dockerRunning: boolean;
  /** Docker 版本（已安装时有值） */
  dockerVersion?: string;
  /** Docker Compose 是否已安装 */
  composeInstalled: boolean;
  /** Docker Compose 版本（已安装时有值） */
  composeVersion?: string;
  /** 是否以 root 用户运行 */
  isRoot: boolean;
  /** 当前系统架构 */
  arch: string;
}

/** Docker 安装步骤结果 */
export interface DockerInstallStepResult {
  step: DockerInstallStep;
  success: boolean;
  message: string;
  skipped?: boolean;
}

/** Docker 安装回调 */
export interface DockerInstallCallbacks {
  onStepStart?: (step: DockerInstallStep, message: string) => void;
  onStepDone?: (step: DockerInstallStep, result: DockerInstallStepResult) => void;
  onStepError?: (step: DockerInstallStep, error: string) => void;
}

/** Docker 安装结果 */
export interface DockerInstallResult {
  success: boolean;
  steps: DockerInstallStepResult[];
  /** 安装后是否需要重新登录以使 docker group 生效 */
  needsRelogin: boolean;
}

/** 离线包扫描结果 */
export interface DockerPackageScan {
  /** 是否找到 Docker 二进制包 */
  hasDockerTgz: boolean;
  /** Docker 二进制包路径 */
  dockerTgzPath?: string;
  /** Docker 二进制包文件名 */
  dockerTgzName?: string;
  /** 是否找到 Docker Compose 二进制 */
  hasComposeBin: boolean;
  /** Docker Compose 二进制路径 */
  composeBinPath?: string;
  /** Docker Compose 二进制文件名 */
  composeBinName?: string;
  /** packages/docker/ 目录是否存在 */
  dirExists: boolean;
}

// ─── systemd 服务文件模板 ─────────────────────────────────

const DOCKER_SERVICE_CONTENT = `[Unit]
Description=Docker Application Container Engine
Documentation=https://docs.docker.com
After=network-online.target containerd.service
Wants=network-online.target
Requires=containerd.service

[Service]
Type=notify
ExecStart=/usr/local/bin/dockerd --host=unix:///var/run/docker.sock
ExecReload=/bin/kill -s HUP $MAINPID
TimeoutStartSec=0
RestartSec=2
Restart=always
LimitNOFILE=infinity
LimitNPROC=infinity
LimitCORE=infinity
TasksMax=infinity
Delegate=yes
KillMode=process
OOMScoreAdjust=-500

[Install]
WantedBy=multi-user.target
`;

const CONTAINERD_SERVICE_CONTENT = `[Unit]
Description=containerd container runtime
Documentation=https://containerd.io
After=network.target

[Service]
ExecStart=/usr/local/bin/containerd
ExecStartPre=-/sbin/modprobe overlay
Type=notify
Delegate=yes
KillMode=process
Restart=always
RestartSec=5
LimitNPROC=infinity
LimitCORE=infinity
LimitNOFILE=infinity
TasksMax=infinity
OOMScoreAdjust=-999

[Install]
WantedBy=multi-user.target
`;

// ─── 检查函数 ─────────────────────────────────────────────

/** 检查当前 Docker 和 Docker Compose 安装状态 */
export async function checkDockerInstallation(): Promise<DockerCheckResult> {
  const isRoot = process.getuid?.() === 0;
  const arch = await getSystemArch();

  // 检查 Docker CLI
  const dockerResult = await exec(['docker', 'version', '--format', '{{.Client.Version}}']);
  const dockerInstalled = dockerResult.exitCode === 0 && dockerResult.stdout.trim().length > 0;
  const dockerVersion = dockerInstalled ? dockerResult.stdout.trim() : undefined;

  // 检查 Docker 守护进程
  const dockerInfoResult = await exec(['docker', 'info']);
  const dockerRunning = dockerInfoResult.exitCode === 0;

  // 检查 Docker Compose
  const composeResult = await exec(['docker', 'compose', 'version', '--short']);
  const composeInstalled = composeResult.exitCode === 0 && composeResult.stdout.trim().length > 0;
  const composeVersion = composeInstalled ? composeResult.stdout.trim() : undefined;

  return {
    dockerInstalled,
    dockerRunning,
    dockerVersion,
    composeInstalled,
    composeVersion,
    isRoot,
    arch,
  };
}

/** 获取系统架构 */
export async function getSystemArch(): Promise<string> {
  const result = await exec(['uname', '-m']);
  return result.stdout.trim();
}

/** 扫描离线安装包目录 */
export async function scanDockerPackages(packagesBaseDir: string): Promise<DockerPackageScan> {
  const dockerDir = resolve(packagesBaseDir, DOCKER_PACKAGES_DIR);
  const dirExists = existsSync(dockerDir);

  if (!dirExists) {
    return {
      hasDockerTgz: false,
      hasComposeBin: false,
      dirExists: false,
    };
  }

  // 扫描 docker-*.tgz 文件
  let dockerTgzPath: string | undefined;
  let dockerTgzName: string | undefined;

  // 扫描 docker-compose-* 文件
  let composeBinPath: string | undefined;
  let composeBinName: string | undefined;

  // 使用 ls 列出目录内容
  const lsResult = await exec(['ls', '-1', dockerDir]);
  if (lsResult.exitCode === 0) {
    const files = lsResult.stdout.split('\n').filter(Boolean);
    for (const file of files) {
      if (file.startsWith('docker-') && file.endsWith('.tgz')) {
        dockerTgzPath = resolve(dockerDir, file);
        dockerTgzName = file;
      }
      if (file.startsWith('docker-compose-')) {
        composeBinPath = resolve(dockerDir, file);
        composeBinName = file;
      }
    }
  }

  return {
    hasDockerTgz: dockerTgzPath !== undefined,
    dockerTgzPath,
    dockerTgzName,
    hasComposeBin: composeBinPath !== undefined,
    composeBinPath,
    composeBinName,
    dirExists: true,
  };
}

// ─── 安装函数 ─────────────────────────────────────────────

/** 当 Docker 已安装运行时，处理仅安装 Compose 的快速路径 */
async function handleExistingDocker(
  check: DockerCheckResult,
  packagesBaseDir: string,
  callbacks?: DockerInstallCallbacks,
): Promise<DockerInstallResult> {
  const steps: DockerInstallStepResult[] = [];

  const stepResult: DockerInstallStepResult = {
    step: 'check-existing',
    success: true,
    message: `Docker ${check.dockerVersion} 已安装且正在运行`,
    skipped: true,
  };
  steps.push(stepResult);
  callbacks?.onStepDone?.('check-existing', stepResult);

  if (!check.composeInstalled) {
    const composeResult = await installComposePlugin(packagesBaseDir, callbacks);
    steps.push(composeResult);
    if (!composeResult.success) {
      return { success: false, steps, needsRelogin: false };
    }
    const verifyResult = await verifyInstallation(callbacks);
    steps.push(verifyResult);
  } else {
    const composeResult: DockerInstallStepResult = {
      step: 'install-compose',
      success: true,
      message: `Docker Compose ${check.composeVersion} 已安装`,
      skipped: true,
    };
    steps.push(composeResult);
    callbacks?.onStepDone?.('install-compose', composeResult);
  }

  return { success: true, steps, needsRelogin: false };
}

/** 预检查：验证 root 权限和离线安装包就绪状态 */
async function preInstallCheck(
  check: DockerCheckResult,
  packagesBaseDir: string,
  callbacks?: DockerInstallCallbacks,
): Promise<{ ok: true; scan: DockerPackageScan } | { ok: false; result: DockerInstallResult }> {
  if (!check.isRoot) {
    const stepResult: DockerInstallStepResult = {
      step: 'check-existing',
      success: false,
      message: '安装 Docker 需要 root 权限，请使用 sudo 运行',
    };
    callbacks?.onStepError?.('check-existing', stepResult.message);
    return { ok: false, result: { success: false, steps: [stepResult], needsRelogin: false } };
  }

  const scan = await scanDockerPackages(packagesBaseDir);
  if (!scan.dirExists) {
    const stepResult: DockerInstallStepResult = {
      step: 'check-existing',
      success: false,
      message: `离线安装包目录不存在: ${resolve(packagesBaseDir, DOCKER_PACKAGES_DIR)}`,
    };
    callbacks?.onStepError?.('check-existing', stepResult.message);
    return { ok: false, result: { success: false, steps: [stepResult], needsRelogin: false } };
  }

  if (!scan.hasDockerTgz) {
    const stepResult: DockerInstallStepResult = {
      step: 'check-existing',
      success: false,
      message: '未找到 Docker 离线安装包 (docker-*.tgz)，请先运行 scripts/download-docker.sh',
    };
    callbacks?.onStepError?.('check-existing', stepResult.message);
    return { ok: false, result: { success: false, steps: [stepResult], needsRelogin: false } };
  }

  return { ok: true, scan };
}

/**
 * 执行 Docker 离线安装的完整流程
 *
 * 步骤：
 * 1. check-existing — 检查现有安装
 * 2. extract-binaries — 解压 Docker 静态二进制到 /usr/local/bin/
 * 3. create-group — 创建 docker 用户组并将当前用户加入
 * 4. create-service — 创建 systemd 服务文件
 * 5. start-docker — 启动并设置开机自启
 * 6. install-compose — 安装 Docker Compose 插件
 * 7. verify — 验证安装结果
 */
export async function installDocker(
  packagesBaseDir: string,
  options: {
    /** 是否跳过已存在的 Docker 安装 */
    skipExisting?: boolean;
    /** 是否将当前用户加入 docker 组 */
    addUserToGroup?: boolean;
  } = {},
  callbacks?: DockerInstallCallbacks,
): Promise<DockerInstallResult> {
  const { skipExisting = true, addUserToGroup = true } = options;

  // ── 1. 检查现有安装 ────────────────────────────────────
  callbacks?.onStepStart?.('check-existing', '检查现有 Docker 安装...');
  const check = await checkDockerInstallation();

  // 快速路径：Docker 已安装运行中
  if (check.dockerInstalled && check.dockerRunning && skipExisting) {
    return handleExistingDocker(check, packagesBaseDir, callbacks);
  }

  // 预检查
  const preCheck = await preInstallCheck(check, packagesBaseDir, callbacks);
  if (!preCheck.ok) return preCheck.result;

  const { scan } = preCheck;
  const steps: DockerInstallStepResult[] = [];
  let needsRelogin = false;

  const checkStepResult: DockerInstallStepResult = {
    step: 'check-existing',
    success: true,
    message: check.dockerInstalled
      ? `检测到 Docker ${check.dockerVersion}（未运行），将重新配置`
      : '未检测到 Docker，准备全新安装',
  };
  steps.push(checkStepResult);
  callbacks?.onStepDone?.('check-existing', checkStepResult);

  // ── 2. 解压 Docker 二进制文件 ──────────────────────────
  callbacks?.onStepStart?.('extract-binaries', '解压 Docker 二进制文件...');
  const dockerTgzPath = scan.dockerTgzPath ?? '';
  const extractResult = await extractDockerBinaries(dockerTgzPath);
  steps.push(extractResult);
  if (!extractResult.success) {
    callbacks?.onStepError?.('extract-binaries', extractResult.message);
    return { success: false, steps, needsRelogin };
  }
  callbacks?.onStepDone?.('extract-binaries', extractResult);

  // ── 3. 创建 docker 用户组 ──────────────────────────────
  callbacks?.onStepStart?.('create-group', '配置 docker 用户组...');
  const groupResult = await createDockerGroup(addUserToGroup);
  steps.push(groupResult);
  if (groupResult.message.includes('需要重新登录')) {
    needsRelogin = true;
  }
  callbacks?.onStepDone?.('create-group', groupResult);

  // ── 4. 创建 systemd 服务文件 ──────────────────────────
  callbacks?.onStepStart?.('create-service', '创建 systemd 服务...');
  const serviceResult = await createSystemdServices();
  steps.push(serviceResult);
  if (!serviceResult.success) {
    callbacks?.onStepError?.('create-service', serviceResult.message);
    return { success: false, steps, needsRelogin };
  }
  callbacks?.onStepDone?.('create-service', serviceResult);

  // ── 5. 启动 Docker 服务 ────────────────────────────────
  callbacks?.onStepStart?.('start-docker', '启动 Docker 服务...');
  const startResult = await startDockerService();
  steps.push(startResult);
  if (!startResult.success) {
    callbacks?.onStepError?.('start-docker', startResult.message);
    return { success: false, steps, needsRelogin };
  }
  callbacks?.onStepDone?.('start-docker', startResult);

  // ── 6. 安装 Docker Compose ─────────────────────────────
  const composeResult = await installComposePlugin(packagesBaseDir, callbacks);
  steps.push(composeResult);

  // ── 7. 验证安装 ────────────────────────────────────────
  const verifyResult = await verifyInstallation(callbacks);
  steps.push(verifyResult);

  const allCriticalSuccess = steps
    .filter((s) => s.step !== 'install-compose')
    .every((s) => s.success);

  return { success: allCriticalSuccess, steps, needsRelogin };
}

// ─── 各步骤实现 ───────────────────────────────────────────

/** 解压 Docker 静态二进制到 /usr/local/bin/ */
async function extractDockerBinaries(tgzPath: string): Promise<DockerInstallStepResult> {
  try {
    // 解压到 /usr/local/bin/，--strip-components=1 去掉 docker/ 前缀
    const result = await exec([
      'tar',
      'xzf',
      tgzPath,
      '-C',
      DOCKER_BIN_DIR,
      '--strip-components=1',
    ]);

    if (result.exitCode !== 0) {
      return {
        step: 'extract-binaries',
        success: false,
        message: `解压失败: ${result.stderr}`,
      };
    }

    return {
      step: 'extract-binaries',
      success: true,
      message: `已安装到 ${DOCKER_BIN_DIR}`,
    };
  } catch (error: unknown) {
    const msg = error instanceof Error ? error.message : String(error);
    return {
      step: 'extract-binaries',
      success: false,
      message: `解压异常: ${msg}`,
    };
  }
}

/** 创建 docker 用户组并将当前用户加入 */
async function createDockerGroup(addUser: boolean): Promise<DockerInstallStepResult> {
  // 创建 docker 组（如果不存在）
  const groupResult = await exec(['groupadd', '-f', 'docker']);
  if (groupResult.exitCode !== 0) {
    return {
      step: 'create-group',
      success: false,
      message: `创建 docker 组失败: ${groupResult.stderr}`,
    };
  }

  if (!addUser) {
    return {
      step: 'create-group',
      success: true,
      message: 'docker 用户组已创建',
    };
  }

  // 获取 SUDO_USER（如果通过 sudo 运行）
  const sudoUser = process.env.SUDO_USER;
  if (sudoUser) {
    const usermodResult = await exec(['usermod', '-aG', 'docker', sudoUser]);
    if (usermodResult.exitCode !== 0) {
      return {
        step: 'create-group',
        success: true,
        message: `docker 组已创建，但将用户 ${sudoUser} 加入组失败: ${usermodResult.stderr}`,
      };
    }
    return {
      step: 'create-group',
      success: true,
      message: `用户 ${sudoUser} 已加入 docker 组（需要重新登录生效）`,
    };
  }

  return {
    step: 'create-group',
    success: true,
    message: 'docker 用户组已创建',
  };
}

/** 创建 containerd 和 docker 的 systemd 服务文件 */
async function createSystemdServices(): Promise<DockerInstallStepResult> {
  try {
    // 写入 containerd 服务文件
    await Bun.write(CONTAINERD_SERVICE_PATH, CONTAINERD_SERVICE_CONTENT);

    // 写入 docker 服务文件
    await Bun.write(DOCKER_SERVICE_PATH, DOCKER_SERVICE_CONTENT);

    // 重新加载 systemd
    const reloadResult = await exec(['systemctl', 'daemon-reload']);
    if (reloadResult.exitCode !== 0) {
      return {
        step: 'create-service',
        success: false,
        message: `systemctl daemon-reload 失败: ${reloadResult.stderr}`,
      };
    }

    return {
      step: 'create-service',
      success: true,
      message: 'containerd 和 docker 服务已创建',
    };
  } catch (error: unknown) {
    const msg = error instanceof Error ? error.message : String(error);
    return {
      step: 'create-service',
      success: false,
      message: `创建服务文件失败: ${msg}`,
    };
  }
}

/** 启动 Docker 服务并设置开机自启 */
async function startDockerService(): Promise<DockerInstallStepResult> {
  // 先启动 containerd
  const containerdStart = await exec(['systemctl', 'start', 'containerd']);
  if (containerdStart.exitCode !== 0) {
    return {
      step: 'start-docker',
      success: false,
      message: `启动 containerd 失败: ${containerdStart.stderr}`,
    };
  }

  // 设置 containerd 开机自启
  await exec(['systemctl', 'enable', 'containerd']);

  // 启动 docker
  const dockerStart = await exec(['systemctl', 'start', 'docker']);
  if (dockerStart.exitCode !== 0) {
    return {
      step: 'start-docker',
      success: false,
      message: `启动 Docker 失败: ${dockerStart.stderr}`,
    };
  }

  // 设置 docker 开机自启
  await exec(['systemctl', 'enable', 'docker']);

  // 等待 Docker socket 就绪
  const maxWait = 15;
  for (let i = 0; i < maxWait; i++) {
    if (existsSync(DOCKER_SOCKET_PATH)) {
      // 尝试执行 docker info
      const infoResult = await exec(['docker', 'info']);
      if (infoResult.exitCode === 0) {
        return {
          step: 'start-docker',
          success: true,
          message: 'Docker 服务已启动并设置开机自启',
        };
      }
    }
    await Bun.sleep(1000);
  }

  return {
    step: 'start-docker',
    success: false,
    message: 'Docker 服务已启动但守护进程未就绪，请检查 journalctl -u docker',
  };
}

/** 安装 Docker Compose 插件 */
async function installComposePlugin(
  packagesBaseDir: string,
  callbacks?: DockerInstallCallbacks,
): Promise<DockerInstallStepResult> {
  callbacks?.onStepStart?.('install-compose', '安装 Docker Compose 插件...');

  const scan = await scanDockerPackages(packagesBaseDir);
  if (!scan.hasComposeBin) {
    const result: DockerInstallStepResult = {
      step: 'install-compose',
      success: false,
      message: '未找到 Docker Compose 离线包，跳过安装。可稍后手动安装',
    };
    callbacks?.onStepDone?.('install-compose', result);
    return result;
  }

  try {
    // 创建插件目录
    await mkdir(DOCKER_CLI_PLUGINS_DIR, { recursive: true });

    // 复制二进制文件（composeBinPath 在此处已由上方 scan.hasComposeBin 保证存在）
    const destPath = resolve(DOCKER_CLI_PLUGINS_DIR, 'docker-compose');
    const composeBinPath = scan.composeBinPath ?? '';
    const cpResult = await exec(['cp', composeBinPath, destPath]);
    if (cpResult.exitCode !== 0) {
      const result: DockerInstallStepResult = {
        step: 'install-compose',
        success: false,
        message: `复制 Docker Compose 失败: ${cpResult.stderr}`,
      };
      callbacks?.onStepError?.('install-compose', result.message);
      return result;
    }

    // 设置可执行权限
    const chmodResult = await exec(['chmod', '+x', destPath]);
    if (chmodResult.exitCode !== 0) {
      const result: DockerInstallStepResult = {
        step: 'install-compose',
        success: false,
        message: `设置权限失败: ${chmodResult.stderr}`,
      };
      callbacks?.onStepError?.('install-compose', result.message);
      return result;
    }

    const result: DockerInstallStepResult = {
      step: 'install-compose',
      success: true,
      message: `已安装到 ${destPath}`,
    };
    callbacks?.onStepDone?.('install-compose', result);
    return result;
  } catch (error: unknown) {
    const msg = error instanceof Error ? error.message : String(error);
    const result: DockerInstallStepResult = {
      step: 'install-compose',
      success: false,
      message: `安装异常: ${msg}`,
    };
    callbacks?.onStepError?.('install-compose', result.message);
    return result;
  }
}

/** 验证 Docker 和 Docker Compose 安装 */
async function verifyInstallation(
  callbacks?: DockerInstallCallbacks,
): Promise<DockerInstallStepResult> {
  callbacks?.onStepStart?.('verify', '验证安装...');

  const check = await checkDockerInstallation();

  const details: string[] = [];

  if (check.dockerInstalled) {
    details.push(`Docker: ${check.dockerVersion}`);
  } else {
    details.push('Docker: 未检测到');
  }

  if (check.dockerRunning) {
    details.push('Docker 守护进程: 运行中');
  } else {
    details.push('Docker 守护进程: 未运行');
  }

  if (check.composeInstalled) {
    details.push(`Docker Compose: ${check.composeVersion}`);
  } else {
    details.push('Docker Compose: 未安装');
  }

  const success = check.dockerInstalled && check.dockerRunning;
  const result: DockerInstallStepResult = {
    step: 'verify',
    success,
    message: success
      ? `Docker ${check.dockerVersion} + Compose ${check.composeVersion ?? '未安装'} 验证通过`
      : `验证失败: ${details.join(', ')}`,
  };
  callbacks?.onStepDone?.('verify', result);
  return result;
}
