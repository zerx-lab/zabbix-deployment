import { stringify } from 'yaml';
import type { DeployConfig } from '../types/config.ts';
import { CONTAINER_NAMES } from '../types/constants.ts';

/** Docker Compose 文件结构类型 */
interface ComposeFile {
  services: Record<string, ComposeService>;
  volumes: Record<string, ComposeVolume | null>;
  networks: Record<string, ComposeNetwork>;
}

interface ComposeService {
  image: string;
  container_name: string;
  restart: string;
  environment: Record<string, string | number>;
  ports?: string[];
  volumes?: string[];
  networks: string[];
  depends_on?: Record<string, { condition: string }> | string[];
  healthcheck?: {
    test: string[];
    interval: string;
    timeout: string;
    retries: number;
  };
}

interface ComposeVolume {
  driver?: string;
}

interface ComposeNetwork {
  driver: string;
}

/**
 * 根据部署配置生成 docker-compose.yml 内容
 */
export function generateComposeYaml(config: DeployConfig): string {
  const compose: ComposeFile = {
    services: {
      postgres: buildPostgresService(config),
      'zabbix-server': buildServerService(config),
      'zabbix-web': buildWebService(config),
      'zabbix-agent': buildAgentService(config),
    },
    volumes: {
      'postgres-data': null,
      'zabbix-server-data': null,
    },
    networks: {
      'zabbix-net': {
        driver: 'bridge',
      },
    },
  };

  return stringify(compose, {
    lineWidth: 120,
    defaultStringType: 'PLAIN',
    defaultKeyType: 'PLAIN',
  });
}

function buildPostgresService(config: DeployConfig): ComposeService {
  return {
    image: 'postgres:16-alpine',
    container_name: CONTAINER_NAMES.postgres,
    restart: 'unless-stopped',
    environment: {
      POSTGRES_USER: config.database.user,
      POSTGRES_PASSWORD: config.database.password,
      POSTGRES_DB: config.database.name,
    },
    volumes: ['postgres-data:/var/lib/postgresql/data'],
    networks: ['zabbix-net'],
    healthcheck: {
      test: ['CMD-SHELL', `pg_isready -U ${config.database.user}`],
      interval: '10s',
      timeout: '5s',
      retries: 5,
    },
  };
}

function buildServerService(config: DeployConfig): ComposeService {
  return {
    image: 'zabbix/zabbix-server-pgsql:alpine-7.0-latest',
    container_name: CONTAINER_NAMES.server,
    restart: 'unless-stopped',
    environment: {
      DB_SERVER_HOST: 'postgres',
      POSTGRES_USER: config.database.user,
      POSTGRES_PASSWORD: config.database.password,
      POSTGRES_DB: config.database.name,
      ZBX_CACHESIZE: config.server.cacheSize,
      ZBX_STARTPOLLERS: config.server.startPollers,
    },
    ports: [`${config.server.listenPort}:10051`],
    volumes: ['zabbix-server-data:/var/lib/zabbix'],
    networks: ['zabbix-net'],
    depends_on: {
      postgres: { condition: 'service_healthy' },
    },
  };
}

function buildWebService(config: DeployConfig): ComposeService {
  return {
    image: 'zabbix/zabbix-web-nginx-pgsql:alpine-7.0-latest',
    container_name: CONTAINER_NAMES.web,
    restart: 'unless-stopped',
    environment: {
      ZBX_SERVER_HOST: 'zabbix-server',
      DB_SERVER_HOST: 'postgres',
      POSTGRES_USER: config.database.user,
      POSTGRES_PASSWORD: config.database.password,
      POSTGRES_DB: config.database.name,
      PHP_TZ: config.web.timezone,
    },
    ports: [`${config.web.httpPort}:8080`, `${config.web.httpsPort}:8443`],
    networks: ['zabbix-net'],
    depends_on: ['zabbix-server'],
  };
}

function buildAgentService(config: DeployConfig): ComposeService {
  return {
    image: 'zabbix/zabbix-agent2:alpine-7.0-latest',
    container_name: CONTAINER_NAMES.agent,
    restart: 'unless-stopped',
    environment: {
      ZBX_SERVER_HOST: 'zabbix-server',
      ZBX_HOSTNAME: config.agent.hostname,
    },
    ports: [`${config.agent.listenPort}:10050`],
    networks: ['zabbix-net'],
    depends_on: ['zabbix-server'],
  };
}
