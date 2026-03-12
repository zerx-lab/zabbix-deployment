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

  it('should apply default SNMP trapper settings', () => {
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
        hostname: 'Zabbix server',
        serverHost: 'zabbix-server',
        listenPort: 10050,
      },
    };

    const result = DeployConfigSchema.safeParse(config);
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.server.enableSnmpTrapper).toBe(false);
      expect(result.data.server.snmpTrapperPort).toBe(162);
    }
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
