import { describe, expect, it } from 'bun:test';
import { DeployConfigSchema } from '../../src/types/config.ts';

describe('DeployConfigSchema', () => {
  it('should validate a complete config', () => {
    const config = {
      version: '7.0',
      database: {
        host: 'localhost',
        port: 5432,
        name: 'zabbix',
        user: 'zabbix',
        password: 'secure_password_123',
      },
      server: {
        listenPort: 10051,
        cacheSize: '128M',
        startPollers: 5,
      },
      web: {
        httpPort: 8080,
        httpsPort: 8443,
        timezone: 'Asia/Shanghai',
      },
      agent: {
        hostname: 'zabbix-agent-01',
        serverHost: 'zabbix-server',
        listenPort: 10050,
      },
    };

    const result = DeployConfigSchema.safeParse(config);
    expect(result.success).toBe(true);
  });

  it('should reject config with short password', () => {
    const config = {
      version: '7.0',
      database: {
        host: 'localhost',
        port: 5432,
        name: 'zabbix',
        user: 'zabbix',
        password: 'short',
      },
      server: {
        listenPort: 10051,
        cacheSize: '128M',
        startPollers: 5,
      },
      web: {
        httpPort: 8080,
        httpsPort: 8443,
        timezone: 'Asia/Shanghai',
      },
      agent: {
        hostname: 'agent-01',
        serverHost: 'zabbix-server',
        listenPort: 10050,
      },
    };

    const result = DeployConfigSchema.safeParse(config);
    expect(result.success).toBe(false);
  });
});
