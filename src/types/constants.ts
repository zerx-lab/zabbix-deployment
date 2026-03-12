/** Zabbix 离线部署所需的基础 Docker 镜像清单（与官方 zabbix-docker 7.0 分支对齐） */
export const ZABBIX_IMAGES = [
  'postgres:16-alpine',
  'zabbix/zabbix-server-pgsql:alpine-7.0-latest',
  'zabbix/zabbix-web-nginx-pgsql:alpine-7.0-latest',
  'zabbix/zabbix-agent2:alpine-7.0-latest',
] as const;

/** SNMP Trapper 镜像（SNMP 功能启用时需要） */
export const SNMP_TRAPS_IMAGE = 'zabbix/zabbix-snmptraps:alpine-7.0-latest' as const;

/** 镜像名称到友好名称的映射 */
export const IMAGE_LABELS: Record<string, string> = {
  'postgres:16-alpine': 'PostgreSQL 16',
  'zabbix/zabbix-server-pgsql:alpine-7.0-latest': 'Zabbix Server',
  'zabbix/zabbix-web-nginx-pgsql:alpine-7.0-latest': 'Zabbix Web (Nginx)',
  'zabbix/zabbix-agent2:alpine-7.0-latest': 'Zabbix Agent2',
  'zabbix/zabbix-snmptraps:alpine-7.0-latest': 'Zabbix SNMP Traps',
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
  snmptraps: 'zabbix-snmptraps',
} as const;

/** 健康检查轮询间隔（毫秒） */
export const HEALTH_CHECK_INTERVAL_MS = 3000;

/** 健康检查最大等待时间（毫秒） */
export const HEALTH_CHECK_TIMEOUT_MS = 180_000;

/** 应用版本 */
export const APP_VERSION = '0.1.0';

// ─── Docker 离线安装相关常量 ──────────────────────────────

/** Docker 静态二进制版本（与 download-docker.sh 保持一致） */
export const DOCKER_VERSION = '27.5.1';

/** Docker Compose 插件版本（与 download-docker.sh 保持一致） */
export const COMPOSE_VERSION = 'v2.35.1';

/** Docker 离线安装包目录名 */
export const DOCKER_PACKAGES_DIR = 'docker';

/** Docker 二进制文件安装目标目录 */
export const DOCKER_BIN_DIR = '/usr/local/bin';

/** Docker Compose 插件安装目标目录 */
export const DOCKER_CLI_PLUGINS_DIR = '/usr/local/lib/docker/cli-plugins';

/** dockerd systemd 服务文件路径 */
export const DOCKER_SERVICE_PATH = '/etc/systemd/system/docker.service';

/** Docker socket 文件路径 */
export const DOCKER_SOCKET_PATH = '/var/run/docker.sock';

/** containerd systemd 服务文件路径 */
export const CONTAINERD_SERVICE_PATH = '/etc/systemd/system/containerd.service';

/** Docker 安装步骤 */
export type DockerInstallStep =
  | 'check-existing'
  | 'extract-binaries'
  | 'create-group'
  | 'create-service'
  | 'start-docker'
  | 'install-compose'
  | 'verify';

/** Docker 安装步骤名称映射 */
export const DOCKER_INSTALL_STEP_LABELS: Record<DockerInstallStep, string> = {
  'check-existing': '检查现有安装',
  'extract-binaries': '安装 Docker 二进制文件',
  'create-group': '创建 docker 用户组',
  'create-service': '创建 systemd 服务',
  'start-docker': '启动 Docker 服务',
  'install-compose': '安装 Docker Compose',
  verify: '验证安装',
};

/**
 * Docker 二进制包中包含的文件列表
 * 解压 docker-VERSION.tgz 后的 docker/ 目录中的文件
 */
export const DOCKER_BINARIES = [
  'containerd',
  'containerd-shim-runc-v2',
  'ctr',
  'docker',
  'docker-init',
  'docker-proxy',
  'dockerd',
  'runc',
] as const;
