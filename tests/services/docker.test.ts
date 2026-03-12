import { describe, expect, it } from 'bun:test';
import type { ComposeDownOptions, ImageInfo } from '../../src/services/docker.ts';

describe('docker service types', () => {
  describe('ComposeDownOptions', () => {
    it('默认选项应不删除卷和镜像', () => {
      const options: ComposeDownOptions = {};
      expect(options.removeVolumes).toBeUndefined();
      expect(options.removeImages).toBeUndefined();
    });

    it('应支持仅删除卷', () => {
      const options: ComposeDownOptions = { removeVolumes: true };
      expect(options.removeVolumes).toBe(true);
      expect(options.removeImages).toBeUndefined();
    });

    it('应支持同时删除卷和镜像', () => {
      const options: ComposeDownOptions = { removeVolumes: true, removeImages: true };
      expect(options.removeVolumes).toBe(true);
      expect(options.removeImages).toBe(true);
    });
  });

  describe('ImageInfo', () => {
    it('应正确表示镜像信息', () => {
      const info: ImageInfo = {
        name: 'postgres:16-alpine',
        id: 'abc123def456',
        size: '250.0 MB',
      };
      expect(info.name).toBe('postgres:16-alpine');
      expect(info.id).toHaveLength(12);
      expect(info.size).toContain('MB');
    });
  });
});
