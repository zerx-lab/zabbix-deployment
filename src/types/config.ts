import { z } from 'zod';
import { DEFAULT_DEPLOY_DIR } from './constants.ts';

/** Zabbix 部署配置 Schema */
export const DeployConfigSchema = z.object({
  /** Zabbix 版本 */
  version: z.string().default('7.0'),

  /** 数据库配置 */
  database: z.object({
    host: z.string().default('postgres'),
    port: z.number().default(5432),
    name: z.string().default('zabbix'),
    user: z.string().default('zabbix'),
    password: z.string().min(8),
  }),

  /** Zabbix Server 配置 */
  server: z.object({
    listenPort: z.number().default(10051),
    cacheSize: z.string().default('128M'),
    startPollers: z.number().default(5),
  }),

  /** Zabbix Web 前端配置 */
  web: z.object({
    httpPort: z.number().default(8080),
    httpsPort: z.number().default(8443),
    timezone: z.string().default('Asia/Shanghai'),
  }),

  /** Zabbix Agent 配置 */
  agent: z.object({
    hostname: z.string().default('zabbix-agent'),
    serverHost: z.string().default('zabbix-server'),
    listenPort: z.number().default(10050),
  }),
});

export type DeployConfig = z.infer<typeof DeployConfigSchema>;

/** 部署运行时选项 Schema */
export const DeployOptionsSchema = z.object({
  /** 部署目录（compose 文件和数据卷的存放位置） */
  deployDir: z.string().default(DEFAULT_DEPLOY_DIR),

  /** 离线镜像包目录 */
  packagesDir: z.string().optional(),

  /** 是否跳过已存在的镜像加载 */
  skipExistingImages: z.boolean().default(true),
});

export type DeployOptions = z.infer<typeof DeployOptionsSchema>;
