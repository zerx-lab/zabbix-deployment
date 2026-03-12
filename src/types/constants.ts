/** Zabbix 离线部署所需的 Docker 镜像清单（与官方 zabbix-docker 7.0 分支对齐） */
export const ZABBIX_IMAGES = [
  'postgres:16-alpine',
  'zabbix/zabbix-server-pgsql:alpine-7.0-latest',
  'zabbix/zabbix-web-nginx-pgsql:alpine-7.0-latest',
  'zabbix/zabbix-agent2:alpine-7.0-latest',
] as const;

/** 镜像名称到友好名称的映射 */
export const IMAGE_LABELS: Record<string, string> = {
  'postgres:16-alpine': 'PostgreSQL 16',
  'zabbix/zabbix-server-pgsql:alpine-7.0-latest': 'Zabbix Server',
  'zabbix/zabbix-web-nginx-pgsql:alpine-7.0-latest': 'Zabbix Web (Nginx)',
  'zabbix/zabbix-agent2:alpine-7.0-latest': 'Zabbix Agent2',
};

/**
 * 将镜像名称转换为 tar 文件名
 * 规则：将 `/` 替换为 `-`，将 `:` 替换为 `-`，追加 `.tar`
 */
export function imageToTarName(image: string): string {
  return `${image.replace(/\//g, '-').replace(/:/g, '-')}.tar`;
}

/** 镜像名称到 tar 文件名的映射（由 imageToTarName 生成） */
export const IMAGE_TAR_NAMES: Record<string, string> = Object.fromEntries(
  ZABBIX_IMAGES.map((img) => [img, imageToTarName(img)]),
);

/** 默认部署目录 */
export const DEFAULT_DEPLOY_DIR = '/opt/zabbix';

/** Docker Compose 项目名称 */
export const COMPOSE_PROJECT_NAME = 'zabbix';

/** 生成的 docker-compose.yml 文件名 */
export const COMPOSE_FILE_NAME = 'docker-compose.yml';

/** 服务容器名称 */
export const CONTAINER_NAMES = {
  postgres: 'zabbix-postgres',
  server: 'zabbix-server',
  web: 'zabbix-web',
  agent: 'zabbix-agent',
} as const;

/** 健康检查轮询间隔（毫秒） */
export const HEALTH_CHECK_INTERVAL_MS = 3000;

/** 健康检查最大等待时间（毫秒） */
export const HEALTH_CHECK_TIMEOUT_MS = 180_000;

/** 应用版本 */
export const APP_VERSION = '0.1.0';
