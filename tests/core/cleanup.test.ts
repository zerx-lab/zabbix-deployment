import { describe, expect, it } from 'bun:test';
import { formatImageLabel } from '../../src/core/cleanup.ts';
import type { CleanupOptions, CleanupStep, EnvironmentSnapshot } from '../../src/core/cleanup.ts';

describe('cleanup', () => {
  describe('formatImageLabel', () => {
    it('应返回已知镜像的友好名称', () => {
      expect(formatImageLabel('postgres:16-alpine')).toBe('PostgreSQL 16');
      expect(formatImageLabel('zabbix/zabbix-server-pgsql:alpine-7.0-latest')).toBe(
        'Zabbix Server',
      );
    });

    it('未知镜像应返回原始名称', () => {
      expect(formatImageLabel('unknown:latest')).toBe('unknown:latest');
    });
  });

  describe('CleanupOptions', () => {
    it('容器级别清理应仅停止容器', () => {
      const options: CleanupOptions = {
        removeVolumes: false,
        removeImages: false,
        removeDeployDir: false,
      };
      expect(options.removeVolumes).toBe(false);
      expect(options.removeImages).toBe(false);
      expect(options.removeDeployDir).toBe(false);
    });

    it('数据级别清理应包含卷删除', () => {
      const options: CleanupOptions = {
        removeVolumes: true,
        removeImages: false,
        removeDeployDir: false,
      };
      expect(options.removeVolumes).toBe(true);
      expect(options.removeImages).toBe(false);
    });

    it('完全卸载应启用所有清理选项', () => {
      const options: CleanupOptions = {
        removeVolumes: true,
        removeImages: true,
        removeDeployDir: true,
      };
      expect(options.removeVolumes).toBe(true);
      expect(options.removeImages).toBe(true);
      expect(options.removeDeployDir).toBe(true);
    });
  });

  describe('CleanupStep', () => {
    it('应支持所有清理步骤类型', () => {
      const steps: CleanupStep[] = [
        'stop-services',
        'remove-volumes',
        'remove-images',
        'remove-deploy-dir',
      ];
      expect(steps).toHaveLength(4);
    });
  });

  describe('EnvironmentSnapshot 结构', () => {
    it('空环境快照应正确表示', () => {
      const snapshot: EnvironmentSnapshot = {
        containers: [],
        volumes: [],
        images: [],
        composeFileExists: false,
        deployDirExists: false,
        deployDir: '/opt/zabbix',
      };
      expect(snapshot.containers).toHaveLength(0);
      expect(snapshot.volumes).toHaveLength(0);
      expect(snapshot.images).toHaveLength(0);
      expect(snapshot.composeFileExists).toBe(false);
      expect(snapshot.deployDirExists).toBe(false);
    });

    it('有资源的快照应正确表示', () => {
      const snapshot: EnvironmentSnapshot = {
        containers: [
          { name: 'zabbix-server', state: 'running', status: 'Up 5 minutes', health: 'healthy' },
          { name: 'zabbix-postgres', state: 'running', status: 'Up 5 minutes', health: 'healthy' },
        ],
        volumes: ['zabbix_postgres-data', 'zabbix_zabbix-server-data'],
        images: [
          { name: 'postgres:16-alpine', id: 'abc123def456', size: '250.0 MB' },
          {
            name: 'zabbix/zabbix-server-pgsql:alpine-7.0-latest',
            id: 'def456abc789',
            size: '180.0 MB',
          },
        ],
        composeFileExists: true,
        deployDirExists: true,
        deployDir: '/opt/zabbix',
      };
      expect(snapshot.containers).toHaveLength(2);
      expect(snapshot.volumes).toHaveLength(2);
      expect(snapshot.images).toHaveLength(2);
      expect(snapshot.composeFileExists).toBe(true);
    });
  });
});
