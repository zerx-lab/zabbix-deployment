import { describe, expect, it } from 'bun:test';
import {
  IMAGE_LABELS,
  IMAGE_TAR_NAMES,
  ZABBIX_IMAGES,
  imageToTarName,
} from '../../src/types/constants.ts';

describe('constants', () => {
  describe('ZABBIX_IMAGES', () => {
    it('应包含 4 个镜像', () => {
      expect(ZABBIX_IMAGES).toHaveLength(4);
    });

    it('应包含 postgres 镜像', () => {
      expect(ZABBIX_IMAGES).toContain('postgres:16-alpine');
    });

    it('应包含 zabbix-server 镜像', () => {
      expect(ZABBIX_IMAGES).toContain('zabbix/zabbix-server-pgsql:alpine-7.0-latest');
    });
  });

  describe('imageToTarName', () => {
    it('应将简单镜像名转为 tar 文件名', () => {
      expect(imageToTarName('postgres:16-alpine')).toBe('postgres-16-alpine.tar');
    });

    it('应将含斜杠的镜像名转为 tar 文件名', () => {
      expect(imageToTarName('zabbix/zabbix-server-pgsql:alpine-7.0-latest')).toBe(
        'zabbix-zabbix-server-pgsql-alpine-7.0-latest.tar',
      );
    });

    it('应将多层斜杠的镜像名转为 tar 文件名', () => {
      expect(imageToTarName('registry.example.com/org/image:v1')).toBe(
        'registry.example.com-org-image-v1.tar',
      );
    });
  });

  describe('IMAGE_TAR_NAMES', () => {
    it('应为每个 ZABBIX_IMAGES 提供 tar 文件名', () => {
      for (const image of ZABBIX_IMAGES) {
        expect(IMAGE_TAR_NAMES[image]).toBeDefined();
        expect(IMAGE_TAR_NAMES[image]).toEndWith('.tar');
      }
    });
  });

  describe('IMAGE_LABELS', () => {
    it('应为每个 ZABBIX_IMAGES 提供友好名称', () => {
      for (const image of ZABBIX_IMAGES) {
        const label = IMAGE_LABELS[image];
        expect(label).toBeDefined();
        expect(label?.length).toBeGreaterThan(0);
      }
    });
  });
});
