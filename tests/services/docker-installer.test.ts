import { describe, expect, it } from 'bun:test';
import type {
  DockerCheckResult,
  DockerInstallCallbacks,
  DockerInstallResult,
  DockerInstallStepResult,
  DockerPackageScan,
} from '../../src/services/docker-installer.ts';
import {
  COMPOSE_VERSION,
  CONTAINERD_SERVICE_PATH,
  DOCKER_BINARIES,
  DOCKER_BIN_DIR,
  DOCKER_CLI_PLUGINS_DIR,
  DOCKER_INSTALL_STEP_LABELS,
  DOCKER_PACKAGES_DIR,
  DOCKER_SERVICE_PATH,
  DOCKER_SOCKET_PATH,
  DOCKER_VERSION,
} from '../../src/types/constants.ts';
import type { DockerInstallStep } from '../../src/types/constants.ts';

describe('docker-installer types', () => {
  describe('DockerCheckResult', () => {
    it('应正确表示未安装状态', () => {
      const result: DockerCheckResult = {
        dockerInstalled: false,
        dockerRunning: false,
        composeInstalled: false,
        isRoot: true,
        arch: 'x86_64',
      };
      expect(result.dockerInstalled).toBe(false);
      expect(result.dockerRunning).toBe(false);
      expect(result.composeInstalled).toBe(false);
      expect(result.dockerVersion).toBeUndefined();
      expect(result.composeVersion).toBeUndefined();
    });

    it('应正确表示已安装且运行中状态', () => {
      const result: DockerCheckResult = {
        dockerInstalled: true,
        dockerRunning: true,
        dockerVersion: '27.5.1',
        composeInstalled: true,
        composeVersion: '2.35.1',
        isRoot: false,
        arch: 'aarch64',
      };
      expect(result.dockerInstalled).toBe(true);
      expect(result.dockerRunning).toBe(true);
      expect(result.dockerVersion).toBe('27.5.1');
      expect(result.composeVersion).toBe('2.35.1');
      expect(result.arch).toBe('aarch64');
    });
  });

  describe('DockerPackageScan', () => {
    it('应正确表示空目录扫描结果', () => {
      const scan: DockerPackageScan = {
        hasDockerTgz: false,
        hasComposeBin: false,
        dirExists: false,
      };
      expect(scan.dirExists).toBe(false);
      expect(scan.hasDockerTgz).toBe(false);
      expect(scan.hasComposeBin).toBe(false);
      expect(scan.dockerTgzPath).toBeUndefined();
      expect(scan.composeBinPath).toBeUndefined();
    });

    it('应正确表示完整安装包扫描结果', () => {
      const scan: DockerPackageScan = {
        hasDockerTgz: true,
        dockerTgzPath: '/opt/packages/docker/docker-27.5.1-x86_64.tgz',
        dockerTgzName: 'docker-27.5.1-x86_64.tgz',
        hasComposeBin: true,
        composeBinPath: '/opt/packages/docker/docker-compose-v2.35.1-linux-x86_64',
        composeBinName: 'docker-compose-v2.35.1-linux-x86_64',
        dirExists: true,
      };
      expect(scan.dirExists).toBe(true);
      expect(scan.hasDockerTgz).toBe(true);
      expect(scan.dockerTgzPath).toContain('.tgz');
      expect(scan.hasComposeBin).toBe(true);
      expect(scan.composeBinName).toContain('docker-compose');
    });
  });

  describe('DockerInstallStepResult', () => {
    it('应正确表示成功步骤', () => {
      const result: DockerInstallStepResult = {
        step: 'extract-binaries',
        success: true,
        message: '已安装到 /usr/local/bin',
      };
      expect(result.step).toBe('extract-binaries');
      expect(result.success).toBe(true);
      expect(result.skipped).toBeUndefined();
    });

    it('应正确表示跳过的步骤', () => {
      const result: DockerInstallStepResult = {
        step: 'check-existing',
        success: true,
        message: 'Docker 已安装',
        skipped: true,
      };
      expect(result.skipped).toBe(true);
    });

    it('应正确表示失败步骤', () => {
      const result: DockerInstallStepResult = {
        step: 'start-docker',
        success: false,
        message: '启动失败: permission denied',
      };
      expect(result.success).toBe(false);
      expect(result.message).toContain('启动失败');
    });
  });

  describe('DockerInstallResult', () => {
    it('应正确表示安装成功结果', () => {
      const result: DockerInstallResult = {
        success: true,
        steps: [
          { step: 'check-existing', success: true, message: '检查完成' },
          { step: 'extract-binaries', success: true, message: '已解压' },
          { step: 'verify', success: true, message: '验证通过' },
        ],
        needsRelogin: true,
      };
      expect(result.success).toBe(true);
      expect(result.steps).toHaveLength(3);
      expect(result.needsRelogin).toBe(true);
    });

    it('应正确表示安装失败结果', () => {
      const result: DockerInstallResult = {
        success: false,
        steps: [{ step: 'check-existing', success: false, message: '需要 root 权限' }],
        needsRelogin: false,
      };
      expect(result.success).toBe(false);
      expect(result.steps[0]?.message).toContain('root');
    });
  });
});

describe('docker-installer constants', () => {
  it('Docker 版本号应符合 semver 格式', () => {
    expect(DOCKER_VERSION).toMatch(/^\d+\.\d+\.\d+$/);
  });

  it('Compose 版本号应以 v 开头', () => {
    expect(COMPOSE_VERSION).toMatch(/^v\d+\.\d+\.\d+$/);
  });

  it('Docker 二进制文件列表不应为空', () => {
    expect(DOCKER_BINARIES.length).toBeGreaterThan(0);
    expect(DOCKER_BINARIES).toContain('docker');
    expect(DOCKER_BINARIES).toContain('dockerd');
    expect(DOCKER_BINARIES).toContain('containerd');
    expect(DOCKER_BINARIES).toContain('runc');
  });

  it('所有安装步骤都应有对应的标签', () => {
    const steps: DockerInstallStep[] = [
      'check-existing',
      'extract-binaries',
      'create-group',
      'create-service',
      'start-docker',
      'install-compose',
      'verify',
    ];
    for (const step of steps) {
      expect(DOCKER_INSTALL_STEP_LABELS[step]).toBeDefined();
      expect(DOCKER_INSTALL_STEP_LABELS[step].length).toBeGreaterThan(0);
    }
  });

  it('路径常量应使用绝对路径', () => {
    expect(DOCKER_BIN_DIR).toMatch(/^\//);
    expect(DOCKER_CLI_PLUGINS_DIR).toMatch(/^\//);
    expect(DOCKER_SERVICE_PATH).toMatch(/^\//);
    expect(DOCKER_SOCKET_PATH).toMatch(/^\//);
    expect(CONTAINERD_SERVICE_PATH).toMatch(/^\//);
  });

  it('Docker 包目录名不应包含路径分隔符', () => {
    expect(DOCKER_PACKAGES_DIR).not.toContain('/');
  });
});

describe('DockerInstallCallbacks', () => {
  it('回调接口的所有方法应为可选', () => {
    const callbacks: DockerInstallCallbacks = {};
    expect(callbacks.onStepStart).toBeUndefined();
    expect(callbacks.onStepDone).toBeUndefined();
    expect(callbacks.onStepError).toBeUndefined();
  });

  it('应支持设置所有回调', () => {
    const calls: string[] = [];
    const callbacks: DockerInstallCallbacks = {
      onStepStart(step, msg) {
        calls.push(`start:${step}:${msg}`);
      },
      onStepDone(step, _result) {
        calls.push(`done:${step}`);
      },
      onStepError(step, error) {
        calls.push(`error:${step}:${error}`);
      },
    };

    callbacks.onStepStart?.('verify', '验证中...');
    callbacks.onStepDone?.('verify', {
      step: 'verify',
      success: true,
      message: '通过',
    });
    callbacks.onStepError?.('verify', '失败');

    expect(calls).toEqual(['start:verify:验证中...', 'done:verify', 'error:verify:失败']);
  });
});
