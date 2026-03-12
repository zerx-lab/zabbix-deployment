import { describe, expect, it } from 'bun:test';
import { parse } from 'yaml';
import { generateComposeYaml } from '../../src/config/compose-generator.ts';
import type { DeployConfig } from '../../src/types/config.ts';

const defaultConfig: DeployConfig = {
  version: '7.0',
  database: {
    host: 'postgres',
    port: 5432,
    name: 'zabbix',
    user: 'zabbix',
    password: 'test_password_123',
  },
  server: {
    listenPort: 10051,
    cacheSize: '128M',
    startPollers: 5,
    enableSnmpTrapper: false,
    snmpTrapperPort: 162,
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

describe('generateComposeYaml', () => {
  it('应生成有效的 YAML', () => {
    const yaml = generateComposeYaml(defaultConfig);
    expect(yaml).toBeTruthy();

    const parsed = parse(yaml);
    expect(parsed).toBeDefined();
    expect(parsed.services).toBeDefined();
  });

  it('应包含 4 个服务', () => {
    const yaml = generateComposeYaml(defaultConfig);
    const parsed = parse(yaml);

    expect(Object.keys(parsed.services)).toHaveLength(4);
    expect(parsed.services.postgres).toBeDefined();
    expect(parsed.services['zabbix-server']).toBeDefined();
    expect(parsed.services['zabbix-web']).toBeDefined();
    expect(parsed.services['zabbix-agent']).toBeDefined();
  });

  it('应正确设置数据库密码', () => {
    const yaml = generateComposeYaml(defaultConfig);
    const parsed = parse(yaml);

    expect(parsed.services.postgres.environment.POSTGRES_PASSWORD).toBe('test_password_123');
    expect(parsed.services['zabbix-server'].environment.POSTGRES_PASSWORD).toBe(
      'test_password_123',
    );
  });

  it('应正确设置端口映射', () => {
    const config: DeployConfig = {
      ...defaultConfig,
      web: { ...defaultConfig.web, httpPort: 9090 },
      server: { ...defaultConfig.server, listenPort: 20051 },
    };

    const yaml = generateComposeYaml(config);
    const parsed = parse(yaml);

    expect(parsed.services['zabbix-web'].ports).toContain('9090:8080');
    expect(parsed.services['zabbix-server'].ports).toContain('20051:10051');
  });

  it('应正确设置时区', () => {
    const config: DeployConfig = {
      ...defaultConfig,
      web: { ...defaultConfig.web, timezone: 'America/New_York' },
    };

    const yaml = generateComposeYaml(config);
    const parsed = parse(yaml);

    expect(parsed.services['zabbix-web'].environment.PHP_TZ).toBe('America/New_York');
  });

  it('应包含 volumes 和 networks 定义', () => {
    const yaml = generateComposeYaml(defaultConfig);
    const parsed = parse(yaml);

    expect(parsed.volumes).toBeDefined();
    expect(parsed.networks).toBeDefined();
    expect(parsed.networks['zabbix-net']).toBeDefined();
  });

  it('应设置 restart 策略', () => {
    const yaml = generateComposeYaml(defaultConfig);
    const parsed = parse(yaml);

    for (const service of Object.values(parsed.services) as Array<Record<string, unknown>>) {
      expect(service.restart).toBe('unless-stopped');
    }
  });

  it('应设置 postgres 健康检查', () => {
    const yaml = generateComposeYaml(defaultConfig);
    const parsed = parse(yaml);

    const pg = parsed.services.postgres;
    expect(pg.healthcheck).toBeDefined();
    expect(pg.healthcheck.test).toContain('pg_isready -U zabbix');
  });

  it('应设置 zabbix-server 依赖 postgres 健康检查', () => {
    const yaml = generateComposeYaml(defaultConfig);
    const parsed = parse(yaml);

    const server = parsed.services['zabbix-server'];
    expect(server.depends_on.postgres.condition).toBe('service_healthy');
  });

  it('应设置 Agent hostname 为 Zabbix server', () => {
    const yaml = generateComposeYaml(defaultConfig);
    const parsed = parse(yaml);

    const agent = parsed.services['zabbix-agent'];
    expect(agent.environment.ZBX_HOSTNAME).toBe('Zabbix server');
  });

  it('默认不启用 SNMP Trapper 时不应包含 snmptraps 服务', () => {
    const yaml = generateComposeYaml(defaultConfig);
    const parsed = parse(yaml);

    expect(Object.keys(parsed.services)).toHaveLength(4);
    expect(parsed.services['zabbix-snmptraps']).toBeUndefined();
    expect(parsed.services['zabbix-server'].environment.ZBX_ENABLE_SNMP_TRAPPER).toBeUndefined();
  });

  it('启用 SNMP Trapper 时应包含 snmptraps 服务', () => {
    const snmpConfig: DeployConfig = {
      ...defaultConfig,
      server: {
        ...defaultConfig.server,
        enableSnmpTrapper: true,
        snmpTrapperPort: 162,
      },
    };

    const yaml = generateComposeYaml(snmpConfig);
    const parsed = parse(yaml);

    expect(Object.keys(parsed.services)).toHaveLength(5);
    expect(parsed.services['zabbix-snmptraps']).toBeDefined();
    expect(parsed.services['zabbix-snmptraps'].ports).toContain('162:1162/udp');
  });

  it('启用 SNMP Trapper 时 Server 应设置 ZBX_ENABLE_SNMP_TRAPPER', () => {
    const snmpConfig: DeployConfig = {
      ...defaultConfig,
      server: {
        ...defaultConfig.server,
        enableSnmpTrapper: true,
        snmpTrapperPort: 162,
      },
    };

    const yaml = generateComposeYaml(snmpConfig);
    const parsed = parse(yaml);

    expect(parsed.services['zabbix-server'].environment.ZBX_ENABLE_SNMP_TRAPPER).toBe('true');
  });

  it('启用 SNMP Trapper 时应添加 snmptraps 和 snmp-mibs 卷', () => {
    const snmpConfig: DeployConfig = {
      ...defaultConfig,
      server: {
        ...defaultConfig.server,
        enableSnmpTrapper: true,
        snmpTrapperPort: 162,
      },
    };

    const yaml = generateComposeYaml(snmpConfig);
    const parsed = parse(yaml);

    expect(parsed.volumes.snmptraps).toBeDefined();
    expect(parsed.volumes['snmp-mibs']).toBeDefined();
  });
});
